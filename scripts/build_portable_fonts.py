"""Refresh standard font metadata from our TeX Live image; no fonts are bundled.

Run from the project root with .venv/bin/python scripts/build_portable_fonts.py.
The JSON records encoding slots, relative advances and automatic spacing pairs.
"""
import base64
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fontTools.tfmLib import TFM
from font_reconstruction import load_type1

FONTS = '''cmr10 cmr6 cmr7 cmr9 cmbx10 cmbx7 cmbsy10 cmex9 cmmi10 cmmi5
cmmi6 cmmi7 cmmi9 cmmib10 cmsy10 cmsy6 cmsy7 cmsy9 msbm10 cmcsc10 cmti10
cmbx12 cmr12 cmss10 cmtt10 ptmr8r ptmb8r ptmri8r ptmbi8r ec-lmtt10
phvr8r phvb8r phvro8r phvbo8r pcrr8r pcrb8r pcrro8r pcrbo8r'''.split()

COLLECT = '''import subprocess,json,base64
out={}
for name in NAMES:
 for ext in ['tfm','pfb']:
  p=subprocess.run(['kpsewhich',name+'.'+ext],capture_output=True,text=True).stdout.strip()
  if p: out[name+'.'+ext]=base64.b64encode(open(p,'rb').read()).decode()
p=subprocess.run(['kpsewhich','8r.enc'],capture_output=True,text=True).stdout.strip()
out['8r.enc']=base64.b64encode(open(p,'rb').read()).decode()
print(json.dumps(out))
'''


def main():
    run = subprocess.run(['docker','run','--rm','-i','--network=none','--entrypoint','python',
                          'pdf3tex-pdflatex:local'], input='NAMES='+repr(FONTS)+'\n'+COLLECT,
                         text=True,capture_output=True,check=True,timeout=60)
    data = json.loads(run.stdout)
    enc = re.sub(r'%[^\n]*','',base64.b64decode(data['8r.enc']).decode()).split('[',1)[1].split(']',1)[0]
    enc = re.findall(r'/([^\s/]+)',enc)
    result = {}
    for name in FONTS:
        metrics = TFM(BytesIO(base64.b64decode(data[name+'.tfm'])))
        encoding = []
        if name+'.pfb' in data:
            encoding = load_type1(base64.b64decode(data[name+'.pfb']))[0].font['Encoding']
        elif name.endswith('8r'):
            encoding = enc
        result[name] = {
            'widths':{str(k):round(v['width'],8) for k,v in metrics.chars.items()},
            'encoding':{g:k for k,g in reversed(list(enumerate(encoding))) if g!='.notdef'},
            'space':metrics.fontdimens.get('SPACE',1/3),
            'pairs':[f'{a},{b}' for table in (metrics.kerning,metrics.ligatures) for a,bs in table.items() for b in bs],
        }
    (ROOT/'portable_fonts.json').write_text(json.dumps(result,indent=1)+'\n')
    print(f'Updated metadata for {len(result)} standard fonts.')


if __name__ == '__main__':
    main()
