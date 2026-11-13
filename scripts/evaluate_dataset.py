"""Evaluate the real conversion/compile APIs on every PDF in a directory.

Keep input PDFs and generated projects under ignored data/ and output/ paths.
Only the compact reports contain data suitable for committing to the repository.
"""
import argparse
import base64
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import multiprocessing
from multiprocessing.connection import wait
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymupdf
from fastapi.testclient import TestClient

from app import app, MAX_BYTES
from comparison import compare_pdfs
from converter import MAX_PAGES

DATASET_URL = 'https://www.kaggle.com/datasets/manisha717/dataset-of-pdf-files'
TARGETS = {'portable': 90, 'layout': 95}


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def grade(score):
    return next(letter for threshold, letter in [(90, 'A'), (80, 'B'), (70, 'C'), (60, 'D'), (0, 'F')]
                if score >= threshold)


def tokens(document):
    return Counter(re.findall(r'\w+', ' '.join(page.get_text() for page in document).casefold()))


def text_metrics(original, compiled):
    with pymupdf.open(stream=original, filetype='pdf') as source, pymupdf.open(stream=compiled, filetype='pdf') as output:
        reference, candidate = tokens(source), tokens(output)
        common = sum((reference & candidate).values())
        # Image-only inputs have no text ground truth; a zero/100 F1 would lie.
        recall = common / sum(reference.values()) if reference else None
        precision = common / sum(candidate.values()) if candidate else (0 if reference else None)
        f1 = (2 * precision * recall / (precision + recall) if precision + recall else 0) if reference else None
        return {
            'original_pages': len(source), 'compiled_pages': len(output),
            'reference_tokens': sum(reference.values()), 'compiled_tokens': sum(candidate.values()),
            'text_token_precision': round(100 * precision, 3) if precision is not None else None,
            'text_token_recall': round(100 * recall, 3) if recall is not None else None,
            'text_token_f1': round(100 * f1, 3) if f1 is not None else None,
        }


def inspect_pdf(path, inputs):
    data = path.read_bytes()
    record = {'input': path.relative_to(inputs).as_posix(), 'bytes': len(data), 'sha256': sha256(data)}
    record['id'] = sha256(record['input'].encode())[:12]
    try:
        with pymupdf.open(stream=data, filetype='pdf') as document:
            record.update(pages=len(document), encrypted=document.needs_pass)
            if document.needs_pass:
                record['input_error'] = 'Password protected PDF.'
    except Exception as error:
        record['input_error'] = str(error)
    if len(data) > MAX_BYTES:
        record['limit_error'] = 'Exceeds the application 20 MiB upload limit.'
    elif record.get('pages', 0) > MAX_PAGES:
        record['limit_error'] = f'Exceeds the application {MAX_PAGES}-page limit.'
    return record


def evaluate(client, path, entry, mode, directory, stage_callback=lambda stage: None):
    directory.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    record = {'input': entry['input'], 'sha256': entry['sha256'], 'mode': mode, 'target': TARGETS[mode]}
    if entry.get('input_error') or entry.get('limit_error'):
        return record | {'status': 'input_rejected', 'error': entry.get('input_error') or entry['limit_error'], 'seconds': 0}
    data = path.read_bytes()
    stage_callback('conversion')
    response = client.post('/api/convert', files={'file': (path.name, data, 'application/pdf')}, data={'mode': mode})
    record['conversion_http_status'] = response.status_code
    record['conversion_seconds'] = round(time.monotonic() - start, 3)
    if response.status_code != 200:
        return record | {'status': 'conversion_failed', 'error': response.json().get('detail'), 'seconds': record['conversion_seconds']}
    project = response.json()
    (directory / 'main.tex').write_text(project['tex'], encoding='utf-8')
    # Portable mode deliberately supplies no assets to the compiler.
    if mode != 'portable':
        (directory / 'project.zip').write_bytes(base64.b64decode(project['zip']))
    metadata = {k: v for k, v in project.items() if k not in ('tex', 'zip')}
    save_json(directory / 'conversion.json', metadata)
    record['warnings'] = project.get('warnings', [])
    stage_callback('compilation')
    response = client.post('/api/compile', json={
        'tex': project['tex'], 'project_zip': project['zip'] if mode != 'portable' else '',
        'engine': project.get('engine', 'tectonic'), 'fidelity_target': TARGETS[mode],
    })
    record['compile_http_status'] = response.status_code
    record['seconds'] = round(time.monotonic() - start, 3)
    if response.status_code != 200:
        detail = response.json().get('detail')
        if isinstance(detail, dict):
            (directory / 'compile.log').write_text(detail.get('log', ''), encoding='utf-8')
            detail = detail.get('message', detail)
        return record | {'status': 'compile_failed', 'error': detail}
    result = response.json()
    compiled = base64.b64decode(result['pdf'])
    (directory / 'compiled.pdf').write_bytes(compiled)
    (directory / 'compile.log').write_text(result['log'], encoding='utf-8')
    stage_callback('comparison')
    comparison = compare_pdfs(data, compiled)
    comparison.update(target=TARGETS[mode], matches=comparison['similarity'] >= TARGETS[mode])
    comparison['mean_page_similarity'] = round(statistics.mean(p['similarity'] for p in comparison['pages']), 3)
    record.update(status='success', engine=result['engine'], metrics=comparison | text_metrics(data, compiled))
    record['seconds'] = round(time.monotonic() - start, 3)
    return record


def worker(connection):
    """Keep imports warm while isolating each worker's API locks."""
    while True:
        job = connection.recv()
        if job is None:
            return
        path, entry, mode, directory = job
        try:
            with TestClient(app) as client:
                result = evaluate(client, path, entry, mode, directory,
                                  lambda stage: connection.send({'event': stage}))
        except Exception as error:
            result = {'input': entry['input'], 'sha256': entry['sha256'], 'mode': mode,
                      'target': TARGETS[mode], 'status': 'error', 'error': str(error)}
        connection.send({'result': result})


def run_jobs(jobs, workers, timeout):
    """Replace crashed/timed-out workers so one malformed PDF cannot stall a run."""
    context = multiprocessing.get_context('spawn')
    queue = deque(jobs)
    active = {}
    def start_worker():
        parent, child = context.Pipe()
        process = context.Process(target=worker, args=(child,), daemon=True)
        process.start()
        child.close()
        active[parent] = {'process': process}
    def dispatch(connection):
        state = active[connection]
        if not queue:
            connection.send(None)
            state['process'].join(timeout=5)
            connection.close()
            del active[connection]
            return
        job, result_file = queue.popleft()
        state.update(job=job, result_file=result_file, started=time.monotonic(), stage='startup')
        connection.send(job)
    for _ in range(min(workers, len(queue))):
        start_worker()
    for connection in list(active):
        dispatch(connection)
    try:
        while active:
            ready = wait(list(active), timeout=1)
            for connection in list(active):
                state = active[connection]
                message = None
                if connection in ready:
                    try:
                        message = connection.recv()
                    except (EOFError, OSError):
                        pass
                if message and 'event' in message:
                    state.update(started=time.monotonic(), stage=message['event'])
                    continue
                if message and 'result' in message:
                    yield state['result_file'], message['result']
                    dispatch(connection)
                elif time.monotonic() - state['started'] > timeout or not state['process'].is_alive():
                    _, entry, mode, _ = state['job']
                    timed_out = state['process'].is_alive()
                    state['process'].terminate()
                    state['process'].join(timeout=5)
                    result = {'input': entry['input'], 'sha256': entry['sha256'], 'mode': mode,
                              'target': TARGETS[mode], 'status': 'timeout' if timed_out else 'worker_failed',
                              'error': f'{state["stage"]} exceeded {timeout}s.' if timed_out else 'Worker exited unexpectedly.'}
                    yield state['result_file'], result
                    connection.close()
                    del active[connection]
                    if queue:
                        start_worker()
                        dispatch(next(reversed(active)))
    finally:
        for connection, state in active.items():
            state['process'].terminate()
            state['process'].join(timeout=5)
            connection.close()


def aggregate(records, inventory):
    by_input = {entry['input']: entry for entry in inventory}
    summary = {}
    for mode in sorted({record['mode'] for record in records}):
        selected = [record for record in records if record['mode'] == mode]
        successes = [record for record in selected if record['status'] == 'success']
        scores = [record['metrics']['similarity'] if record['status'] == 'success' else 0 for record in selected]
        eligible = [record for record in selected if not by_input[record['input']].get('input_error') and not by_input[record['input']].get('limit_error')]
        eligible_scores = [record['metrics']['similarity'] if record['status'] == 'success' else 0 for record in eligible]
        f1 = [record['metrics']['text_token_f1'] for record in successes if record['metrics']['text_token_f1'] is not None]
        score = statistics.mean(scores) if scores else 0
        summary[mode] = {
            'documents': len(selected), 'target': TARGETS[mode],
            'statuses': dict(Counter(record['status'] for record in selected)),
            'compiled': len(successes),
            'compiled_percent': round(100 * len(successes) / len(selected), 3) if selected else 0,
            'passed': sum(record['metrics']['matches'] for record in successes),
            'pass_percent': round(100 * sum(record['metrics']['matches'] for record in successes) / len(selected), 3) if selected else 0,
            'dataset_score': round(score, 3), 'grade': grade(score),
            'eligible_documents': len(eligible),
            'eligible_dataset_score': round(statistics.mean(eligible_scores), 3) if eligible_scores else None,
            'successful_mean_lowest_page_ssim': round(statistics.mean(record['metrics']['similarity'] for record in successes), 3) if successes else None,
            'successful_mean_page_ssim': round(statistics.mean(record['metrics']['mean_page_similarity'] for record in successes), 3) if successes else None,
            'successful_mean_text_token_f1': round(statistics.mean(f1), 3) if f1 else None,
            'image_only_successes': sum(record['metrics'].get('reference_tokens') == 0 for record in successes),
        }
    return summary


def write_reports(directory, manifest, records):
    summary = aggregate(records, manifest['inputs'])
    save_json(directory / 'results.json', {'manifest': manifest, 'summary': summary, 'results': records})
    lines = ['# Kaggle PDF conversion evaluation', '', f"Dataset: [{manifest['dataset']}]({manifest['dataset']})", '',
             f"Converter revision: `{manifest['git_revision']}`; pipeline fingerprint: `{manifest['pipeline_sha256']}`.", '',
             f"Evaluated {len(manifest['inputs'])} PDF files ({manifest['unique_pdf_hashes']} distinct SHA-256 hashes).", '',
             '| Mode | Compiled | Meets target | Dataset score | Grade | Successful mean minimum-page SSIM |',
             '| --- | ---: | ---: | ---: | :---: | ---: |']
    for mode, values in summary.items():
        lines.append(f"| {mode} | {values['compiled']}/{values['documents']} | {values['passed']}/{values['documents']} (target {values['target']}%) | {values['dataset_score']}% | {values['grade']} | {values['successful_mean_lowest_page_ssim']}% |")
    lines += ['', '## Method', '',
              'All PDFs are inventoried. Unlocked, readable inputs within the application 20 MiB/50-page limits are submitted to the real `/api/convert` and `/api/compile` endpoints. Preflight rejections count as zero. Portable output compiles from only its generated `.tex`; layout output includes its extracted assets. No converter fallback, source repair, page splitting, registration or score-threshold changes are applied. Each conversion/comparison phase is bounded by the recorded phase timeout; compilation retains its existing 90-second timeout.', '',
              'Visual similarity uses the existing foreground SSIM at up to 144 dpi with a 2200-pixel cap and a two-pixel foreground halo. The document score is its lowest page score; missing pages score zero. Blank margins cannot increase the score. A document passes only when every page meets the existing mode target (90% portable, 95% layout).', '',
              'The **dataset score** is the arithmetic mean of document scores across all evaluated files, with every rejected/failed document assigned zero. Grades: A >= 90, B >= 80, C >= 70, D >= 60, F < 60. This is an explicit benchmark rubric, not a standardized assessment. The JSON also reports a score limited to unlocked, readable inputs within the application upload/page limits.', '',
              'Token precision/recall/F1 compare case-folded Unicode word multisets extracted from the original and compiled PDFs. Image-only originals have no text ground truth, so their text scores are null. These scores do not establish reading order, semantic LaTeX quality, equation correctness or OCR accuracy. Layout can reproduce scanned images without recovering editable text; image-only successes are counted separately.', '',
              'This dataset supplies PDFs, not paired original TeX sources. The evaluation measures visual reconstruction and extracted-text retention, not recovery of original macros. Repeated files remain in the file-weighted score; the manifest includes hashes so duplication is visible.', '',
              '## Reproduce', '', '```bash',
              'curl -L --fail "https://www.kaggle.com/api/v1/datasets/download/manisha717/dataset-of-pdf-files" -o data/kaggle/pdfs.zip',
              'python -m zipfile -e data/kaggle/pdfs.zip data/kaggle/pdfs',
              'python scripts/evaluate_dataset.py --inputs data/kaggle/pdfs --output output/kaggle --report-dir reports/kaggle',
              '```', '',
              'Install the Python dependencies and both compiler images using the README instructions first. Rerunning resumes only matching input hashes and pipeline fingerprints; use a fresh output directory for a separate experiment. Input PDFs and generated sources/PDFs/logs remain in ignored directories.', '',
              '## Failures', '']
    for mode in summary:
        errors = Counter(str(record.get('error', '')) for record in records if record['mode'] == mode and record['status'] != 'success')
        lines.append(f'### {mode}')
        lines.append('')
        lines.extend(f'- {count}: {error.replace(chr(10), " ")}' for error, count in errors.most_common())
        lines.append('')
    (directory / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, default=Path('reports/kaggle'))
    parser.add_argument('--archive', type=Path, help='Record the SHA-256 of the downloaded dataset ZIP.')
    parser.add_argument('--modes', nargs='+', choices=TARGETS, default=list(TARGETS))
    parser.add_argument('--workers', type=int, default=2, choices=range(1, 5))
    parser.add_argument('--phase-timeout', type=int, default=240)
    args = parser.parse_args()
    if args.phase_timeout < 120:
        parser.error('--phase-timeout must be at least 120s to allow compiler timeout cleanup.')
    inputs, output, reports = args.inputs.resolve(), args.output.resolve(), args.report_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    paths = sorted((path for path in inputs.rglob('*') if path.suffix.lower() == '.pdf'), key=lambda path: path.relative_to(inputs).as_posix())
    if not paths:
        parser.error(f'No PDFs found under {inputs}')
    pipeline = ['app.py', 'converter.py', 'portable_converter.py', 'layout_converter.py', 'font_reconstruction.py', 'compiler.py', 'comparison.py', 'portable_fonts.json']
    pipeline_hash = hashlib.sha256()
    for name in pipeline:
        pipeline_hash.update(name.encode() + (ROOT / name).read_bytes())
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    inventory = []
    for index, path in enumerate(paths, 1):
        inventory.append(inspect_pdf(path, inputs))
        if index % 50 == 0 or index == len(paths):
            print(f'Inventoried {index}/{len(paths)} PDFs', flush=True)
    manifest = {
        'dataset': DATASET_URL, 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'git_revision': revision, 'pipeline_sha256': pipeline_hash.hexdigest(),
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'packages': {name: version(name) for name in ['pymupdf', 'fonttools', 'numpy', 'scipy', 'scikit-image', 'fastapi']}},
        'inputs': inventory, 'unique_pdf_hashes': len({entry['sha256'] for entry in inventory}),
    }
    if args.archive:
        with args.archive.open('rb') as archive:
            manifest['archive_sha256'] = hashlib.file_digest(archive, 'sha256').hexdigest()
    images = {'portable': 'pdf3tex-pdflatex:local', 'layout': 'pdf3tex-tectonic:0.17.0'}
    for image in {images[mode] for mode in args.modes}:
        result = subprocess.run(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], capture_output=True, text=True)
        if result.returncode:
            parser.error(f'Missing compiler image {image}; install it before benchmarking.')
        manifest.setdefault('compiler_images', {})[image] = result.stdout.strip()
    run_fingerprint = sha256(json.dumps({
        'pipeline': manifest['pipeline_sha256'], 'images': manifest['compiler_images'],
        'packages': manifest['environment']['packages'],
        'phase_timeout_seconds': args.phase_timeout,
        'evaluation_script': sha256(Path(__file__).read_bytes()),
    }, sort_keys=True).encode())
    manifest.update(run_fingerprint=run_fingerprint, workers=args.workers, phase_timeout_seconds=args.phase_timeout)
    save_json(output / 'manifest.json', manifest)
    records = []
    pending = []
    for path, entry in zip(paths, inventory):
        for mode in args.modes:
            directory = output / entry['id'] / mode
            result_file = directory / 'result.json'
            cached = json.loads(result_file.read_text(encoding='utf-8')) if result_file.exists() else {}
            if cached.get('run_fingerprint') == run_fingerprint and cached.get('sha256') == entry['sha256']:
                records.append(cached)
            else:
                pending.append(((path, entry, mode, directory), result_file))
    for result_file, record in run_jobs(pending, args.workers, args.phase_timeout):
        record.update(pipeline_sha256=manifest['pipeline_sha256'], run_fingerprint=run_fingerprint)
        save_json(result_file, record)
        records.append(record)
        score = record.get('metrics', {}).get('similarity')
        print(f'{len(records)}/{len(paths) * len(args.modes)} {record["mode"]} {record["input"]} {record["status"]} score={score}', flush=True)
        if len(records) % 10 == 0 or len(records) == len(paths) * len(args.modes):
            save_json(output / 'progress.json', {'completed_jobs': len(records), 'total_jobs': len(paths) * len(args.modes), 'summary': aggregate(records, inventory)})
    records.sort(key=lambda record: (record['input'], record['mode']))
    summary = write_reports(reports, manifest, records)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
