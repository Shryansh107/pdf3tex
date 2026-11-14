"""Optional real compiler regressions: LATEX_COMPILER=/path/to/tectonic pytest."""
import base64
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import pymupdf
import pytest

from converter import convert_pdf
from portable_converter import convert_portable

COMPILER = os.environ.get('LATEX_COMPILER') or shutil.which('tectonic')
pytestmark = pytest.mark.skipif(not COMPILER, reason='Set LATEX_COMPILER to run real TeX compilation')


def compile_source(directory):
    executable = str(Path(COMPILER).resolve())
    if 'tectonic' in Path(executable).name:
        command = [executable, '--keep-logs', 'main.tex']
    else:
        command = [executable, '-interaction=nonstopmode', '-halt-on-error', 'main.tex']
    run = subprocess.run(command, cwd=directory, text=True, capture_output=True, timeout=180)
    assert run.returncode == 0, run.stdout + run.stderr
    assert (directory / 'main.pdf').stat().st_size > 0


@pytest.mark.parametrize('include_assets', [False, True])
def test_downloads_compile_with_or_without_image_assets(tmp_path, include_assets):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 100), r'Research & results: 50% #1 {x} a_b $5 ~ ^ \\')
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
        pix.clear_with(120)
        page.insert_image(pymupdf.Rect(72, 150, 112, 190), pixmap=pix)
        result = convert_portable(doc.tobytes(), 'paper.pdf')
    if include_assets:
        with ZipFile(BytesIO(base64.b64decode(result['zip']))) as archive:
            archive.extractall(tmp_path)
    else:
        (tmp_path / 'main.tex').write_text(result['tex'], encoding='utf-8')
    compile_source(tmp_path)


def test_readable_unicode_text_compiles_with_pdflatex(tmp_path):
    if 'pdflatex' not in Path(COMPILER).name:
        pytest.skip('Readable mode uses pdfLaTeX')
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 100), 'Café and naïve research & results.')
        result = convert_pdf(doc.tobytes(), 'unicode.pdf')
    (tmp_path / 'main.tex').write_text(result['tex'], encoding='utf-8')
    compile_source(tmp_path)
