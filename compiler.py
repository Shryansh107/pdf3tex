"""Compile supplied LaTeX in disposable, resource-bounded containers."""
import base64
import binascii
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

IMAGE = 'pdf3tex-tectonic:0.17.0'
PDFLATEX_IMAGE = 'pdf3tex-pdflatex:local'
TIMEOUT_SECONDS = 90
MAX_ASSET_BYTES = 48 * 1024 * 1024


class CompileError(Exception):
    def __init__(self, message, log='', status=422):
        super().__init__(message)
        self.log = log
        self.status = status


def read_log(path):
    if not path.exists():
        return ''
    with path.open('rb') as file:
        file.seek(max(0, path.stat().st_size - 64000))
        return file.read().decode('utf-8', errors='replace')


def stage_assets(project_zip, directory):
    if not project_zip:
        return
    try:
        data = base64.b64decode(project_zip, validate=True)
        with ZipFile(BytesIO(data)) as archive:
            if len(archive.infolist()) > 1000:
                raise ValueError('Too many files in the project ZIP.')
            images = [info for info in archive.infolist() if re.fullmatch(r'(?:background\.pdf|assets/(?:page_\d+_image_\d+\.png|font_\d+\.(?:ttf|otf)))', info.filename)]
            if sum(info.file_size for info in images) > MAX_ASSET_BYTES:
                raise ValueError('Project assets exceed the 48 MB compilation limit.')
            for info in images:
                target = directory / info.filename
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(archive.read(info))
    except (BadZipFile, binascii.Error, ValueError, RuntimeError, OSError) as exc:
        raise CompileError(f'Invalid project ZIP: {exc}', status=400) from exc


def compile_latex(tex, project_zip='', original_pdf='', engine='tectonic'):
    if engine not in ('tectonic', 'pdflatex'):
        raise CompileError('Unsupported LaTeX engine.', status=400)
    original = None
    if original_pdf:
        try:
            original = base64.b64decode(original_pdf, validate=True)
            import pymupdf
            with pymupdf.open(stream=original, filetype='pdf') as doc:
                if doc.needs_pass or not 1 <= len(doc) <= 50:
                    raise ValueError('Reference PDF must be unlocked and contain 1–50 pages.')
        except Exception as exc:
            raise CompileError('Invalid original PDF for visual comparison.', status=400) from exc
    if not shutil.which('docker'):
        raise CompileError('The compiler is not installed. Run ./install_engine.sh first.', status=503)
    container = f'pdf3tex-compile-{uuid4().hex}'
    with TemporaryDirectory(prefix='pdf3tex-compile-') as temp:
        directory = Path(temp)
        (directory / 'main.tex').write_text(tex, encoding='utf-8')
        stage_assets(project_zip, directory)
        command = [
            'docker', 'run', '--rm', '--name', container, '--pull=never',
            '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--cpus=2', '--memory=768m',
            '--pids-limit=64', '--ulimit', 'fsize=33554432:33554432',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
            '--mount', f'type=bind,src={directory},dst=/work',
        ]
        # Docker Desktop translates Windows bind mounts; Windows has no POSIX
        # uid/gid. Linux hosts still need their own user to own generated files.
        if os.name != 'nt':
            command += ['--user', f'{os.getuid()}:{os.getgid()}']
        if engine == 'pdflatex':
            command += [PDFLATEX_IMAGE, '-no-shell-escape', '-interaction=nonstopmode',
                        '-halt-on-error', '-file-line-error', 'main.tex']
        else:
            command += [IMAGE, '--untrusted', '--only-cached', '--keep-logs',
                        '--color=never', 'main.tex']
        output_log = directory / 'compiler-output.txt'
        started = time.monotonic()
        try:
            with output_log.open('wb') as output:
                run = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                     timeout=TIMEOUT_SECONDS)
                # TikZ remember-picture positioning needs a second pass. Use
                # the exact same source and per-request container directory.
                if engine == 'pdflatex' and run.returncode == 0:
                    remaining = max(.01, TIMEOUT_SECONDS - (time.monotonic() - started))
                    run = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                         timeout=remaining)
            log = read_log(output_log) + '\n' + read_log(directory / 'main.log')
            if run.returncode:
                status = 503 if run.returncode == 125 else 422
                message = ('The compiler container could not start. Run ./install_engine.sh and check Docker.'
                           if status == 503 else 'LaTeX compilation failed. Check the compiler log and edit the source.')
                if 'not in cache' in log.lower() or 'not cached' in log.lower():
                    message = 'A required LaTeX package is not cached. See the compiler log.'
                raise CompileError(message, log, status)
            pdf = directory / 'main.pdf'
            if not pdf.exists() or not pdf.stat().st_size:
                raise CompileError('The compiler did not produce a PDF.', log)
            if pdf.stat().st_size > 20 * 1024 * 1024:
                raise CompileError('The compiled PDF exceeds the 20 MB download limit.', log)
            output = pdf.read_bytes()
            result = {'pdf': base64.b64encode(output).decode(),
                      'log': log[-64000:], 'engine': 'pdfLaTeX (TeX Live)' if engine == 'pdflatex' else 'Tectonic 0.17.0 (XeTeX)'}
            if original:
                from comparison import compare_pdfs
                result['comparison'] = compare_pdfs(original, output)
            return result
        except subprocess.TimeoutExpired as exc:
            raise CompileError(f'Compilation exceeded {TIMEOUT_SECONDS} seconds. Simplify the source and try again.',
                               read_log(output_log), 408) from exc
        finally:
            # Killing a Docker client does not stop its container, so remove it
            # explicitly before deleting the per-request workspace.
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=15)
