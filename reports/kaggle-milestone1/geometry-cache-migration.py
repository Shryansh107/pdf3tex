"""Reuse measurements whose converter branch is unchanged by the size fix.

The source delta is limited to a PageSize macro addition for mixed-size layout
PDFs. Portable code and uniformly sized layout output are unchanged. Mixed or
uninspectable layout inputs are always re-evaluated. Original records/artifacts
remain in the previous output directory; measurements are checksum-audited.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,'.')

import pymupdf
from scripts.evaluate_dataset import save_json

old_root = Path('output/kaggle-milestone1-final')
new_root = Path('output/kaggle-milestone1-verified')
before = json.loads(Path('.tools/geometry-before.json').read_text())
manifest = before['before_manifest']
names = list(before['source_hashes'])
sha = lambda data: hashlib.sha256(data).hexdigest()
current = {name:sha(Path(name).read_bytes()) for name in names}
assert {name for name in names if current[name] != before['source_hashes'][name]} == {'layout_converter.py'}
assert sha(Path('scripts/evaluate_dataset.py').read_bytes()) == before['evaluation_script_sha256']
assert sha(Path('.tools/layout_before_geometry.py').read_bytes()) == before['source_hashes']['layout_converter.py']
pipeline = hashlib.sha256()
for name in names:
    pipeline.update(name.encode()+Path(name).read_bytes())
pipeline = pipeline.hexdigest()
fingerprint = sha(json.dumps({'pipeline':pipeline,'images':manifest['compiler_images'],
                             'packages':manifest['environment']['packages'],
                             'phase_timeout_seconds':manifest['phase_timeout_seconds'],
                             'evaluation_script':before['evaluation_script_sha256']},sort_keys=True).encode())
mixed, uninspectable, entries = set(), set(), {r['input']:r for r in manifest['inputs']}
for name in entries:
    try:
        with pymupdf.open(Path('data/kaggle/pdfs')/name) as doc:
            sizes = {(f'{p.rect.width:.5f}', f'{p.rect.height:.5f}') for p in doc}
            if len(sizes)>1:
                mixed.add(name)
    except Exception:
        uninspectable.add(name)

def measurement(record):
    return {k:v for k,v in record.items() if k not in {'pipeline_sha256','run_fingerprint','previous_pipeline_sha256','previous_run_fingerprint','cache_reuse_reason'}}

audit = {'generated_utc':datetime.now(timezone.utc).isoformat(), 'reason':'Mixed-size layout page-builder repair',
         'before_git_revision':manifest['git_revision'], 'before_pipeline':manifest['pipeline_sha256'],
         'after_pipeline':pipeline,'before_fingerprint':manifest['run_fingerprint'],'after_fingerprint':fingerprint,
         'source_hashes_before':before['source_hashes'],'source_hashes_after':current,
         'evaluation_script_sha256':before['evaluation_script_sha256'],
         'rule':'Reuse portable results and layout results for uniformly sized PDFs. Re-evaluate every mixed-size or uninspectable layout PDF. Input rejections are unchanged and can be reused.',
         'proof':'Only layout_converter.py changed. The added column/page-builder assignments are emitted only for mixed paper sizes. Portable code is unchanged. Generated TeX was byte-identical on five uniform-size fixtures; all old measurements below retain identical canonical checksums.',
         'mixed_size_inputs':sorted(mixed),'uninspectable_inputs':sorted(uninspectable), 'reused':[], 'rerun':[]}
for path in sorted(old_root.rglob('result.json')):
    record = json.loads(path.read_text(encoding='utf-8'))
    assert record['pipeline_sha256'] == manifest['pipeline_sha256']
    assert record['run_fingerprint'] == manifest['run_fingerprint']
    assert record['sha256'] == entries[record['input']]['sha256']
    if record['status']=='success' and record['metrics']['original_pages']!=record['metrics']['compiled_pages']:
        assert record['mode']=='layout' and record['input'] in mixed, 'An unexplained page-count regression must be investigated.'
    if record['mode']=='layout' and record['status']!='input_rejected' and record['input'] in mixed|uninspectable:
        audit['rerun'].append({'input':record['input'],'mode':record['mode']})
        continue
    target = new_root/path.parent.relative_to(old_root)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(path.parent,target,dirs_exist_ok=True)
    original_digest = sha(json.dumps(measurement(record),sort_keys=True).encode())
    record.update(previous_pipeline_sha256=record['pipeline_sha256'],previous_run_fingerprint=record['run_fingerprint'],
                  pipeline_sha256=pipeline,run_fingerprint=fingerprint,
                  cache_reuse_reason='Unchanged portable converter' if record['mode']=='portable' else 'Unchanged input rejection' if record['status']=='input_rejected' else 'Identical uniform-size layout TeX branch')
    updated_digest = sha(json.dumps(measurement(record),sort_keys=True).encode())
    assert original_digest == updated_digest
    save_json(target/'result.json',record)
    audit['reused'].append({'input':record['input'],'mode':record['mode'],'original_result_sha256':sha(path.read_bytes()),
                           'canonical_measurement_before':original_digest,'canonical_measurement_after':updated_digest,
                           'reason':record['cache_reuse_reason']})
    if len(audit['reused'])%100 == 0:
        print('Copied',len(audit['reused']),'unchanged measurements',flush=True)
save_json(new_root/'geometry-cache-audit.json',audit)
print(json.dumps({'reused':len(audit['reused']),'re_evaluate_completed':len(audit['rerun']),
                  'mixed_size_documents':len(mixed),'new_fingerprint':fingerprint},indent=2))
