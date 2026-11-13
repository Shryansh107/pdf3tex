"""Compare the two delivered workflows without editing either converter."""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from zipfile import ZipFile
from io import BytesIO

import httpx
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparison import compare_pdfs


def metrics(original, candidate):
    result = compare_pdfs(original, candidate)
    with pymupdf.open(stream=original, filetype='pdf') as src, pymupdf.open(stream=candidate, filetype='pdf') as dst:
        tokens = lambda doc: Counter(re.findall(r'\w+', ' '.join(p.get_text() for p in doc).casefold()))
        a,b = tokens(src),tokens(dst)
        common=sum((a&b).values())
        precision=common/max(1,sum(b.values()))
        recall=common/max(1,sum(a.values()))
        result.update(original_pages=len(src), compiled_pages=len(dst),
                      mean_page_similarity=round(sum(p['similarity'] for p in result['pages'])/len(result['pages']),3),
                      text_token_recall=round(100*recall,3),
                      text_token_precision=round(100*precision,3),
                      text_token_f1=round(200*precision*recall/max(1e-12,precision+recall),3))
    return result


def run_command(command, cwd, log, timeout=420):
    start=time.monotonic()
    try:
        with log.open('w') as output:
            process=subprocess.run(command,cwd=cwd,stdout=output,stderr=subprocess.STDOUT,timeout=timeout)
        return {'exit_code':process.returncode,'seconds':round(time.monotonic()-start,3)}
    except subprocess.TimeoutExpired:
        return {'exit_code':None,'seconds':round(time.monotonic()-start,3),'error':'Command timed out'}


def save_json(path, value):
    path.write_text(json.dumps(value,indent=2))


def bench_local(pdf, out, server):
    out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    record={'workflow':'local-layout','input':pdf.name}
    with httpx.Client(base_url=server,timeout=240) as client:
        response=client.post('/api/convert',files={'file':(pdf.name,pdf.read_bytes())},data={'mode':'layout'})
        record['conversion_http_status']=response.status_code
        if response.status_code!=200:
            save_json(out/'error.json',response.json())
            return record|{'status':'conversion_failed','seconds':round(time.monotonic()-start,3)}
        project=response.json()
        (out/'main.tex').write_text(project['tex'])
        (out/'project.zip').write_bytes(base64.b64decode(project['zip']))
        save_json(out/'conversion.json',{k:v for k,v in project.items() if k not in ('tex','zip')})
        # The existing compiler is used as-is, including its cached packages.
        response=client.post('/api/compile',json={'tex':project['tex'],'project_zip':project['zip']})
        record['compile_http_status']=response.status_code
        record['seconds']=round(time.monotonic()-start,3)
        if response.status_code!=200:
            error=response.json(); save_json(out/'error.json',error)
            (out/'compile.log').write_text(str(error.get('detail',{}).get('log','')))
            return record|{'status':'compile_failed'}
        compiled=response.json()
        data=base64.b64decode(compiled['pdf'])
        (out/'compiled.pdf').write_bytes(data)
        (out/'compile.log').write_text(compiled['log'])
        return record|{'status':'success','engine':compiled['engine'],'metrics':metrics(pdf.read_bytes(),data)}


def bench_mcp(pdf,out,project,source_project=None):
    # Keep outputs in separate directories: compiler retries never overwrite a
    # default-run result and never modify the referenced project checkout.
    exe=project/'.venv/bin/pdf-to-latex'
    record={'workflow':'mcp-project' if source_project is None else 'local-source-via-mcp','input':pdf.name}
    command=[str(exe),'convert',str(pdf),'--out',str(out)]
    if source_project is not None:
        out.mkdir(parents=True,exist_ok=True)
        with ZipFile(source_project/'project.zip') as archive:
            archive.extractall(out)
        command=[str(exe),'compile',str(out),'--compiler','xelatex']
    info=run_command(command,project,out.parent/(out.name+'-cli.log'))
    record['default_attempt']=info
    # A documented engine switch is recorded separately, with untouched source.
    if info['exit_code']!=0 and source_project is None and (out/'main.tex').exists():
        retry=out.parent/(out.name+'-xelatex')
        retry.mkdir(exist_ok=True)
        (retry/'main.tex').write_bytes((out/'main.tex').read_bytes())
        import shutil
        if (out/'assets').exists():
            shutil.copytree(out/'assets',retry/'assets',dirs_exist_ok=True)
        record['xelatex_retry']=run_command([str(exe),'compile',str(retry),'--compiler','xelatex'],project,out.parent/(out.name+'-xelatex-cli.log'))
        if (retry/'compiled.pdf').exists():
            out=retry
            record['used_engine_fallback']=True
    record['output_directory']=str(out)
    if (out/'compiled.pdf').exists():
        data=(out/'compiled.pdf').read_bytes()
        return record|{'status':'success','metrics':metrics(pdf.read_bytes(),data)}
    return record|{'status':'compile_failed' if (out/'main.tex').exists() else 'conversion_failed'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-project',required=True,type=Path)
    parser.add_argument('--inputs',type=Path,default=Path('pdfs'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--server',default='http://127.0.0.1:8000')
    parser.add_argument('--workflow',choices=['local','local-warmed','mcp','control'],required=True)
    args=parser.parse_args()
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=True)
    for pdf in sorted(args.inputs.resolve().glob('*.pdf')):
        name='resume' if any(term in pdf.stem.lower() for term in ('resume', 'cv')) else pdf.stem
        directory=args.output/name
        directory.mkdir(exist_ok=True)
        print(args.workflow,pdf.name,'starting',flush=True)
        try:
            if args.workflow in ('local','local-warmed'):
                record=bench_local(pdf,directory/args.workflow,args.server)
                if args.workflow=='local-warmed':
                    record['runtime_note']='Same converter/compiler code; compiler font cache warmed after the initial failure.'
            elif args.workflow=='mcp':
                record=bench_mcp(pdf,directory/'mcp',args.mcp_project)
            else:
                record=bench_mcp(pdf,directory/'local-source-mcp',args.mcp_project,directory/'local')
        except Exception as error:
            record={'workflow':args.workflow,'input':pdf.name,'status':'error','error':str(error)}
        save_json(directory/(args.workflow+'-result.json'),record)
        print(json.dumps(record),flush=True)


if __name__=='__main__':
    main()
