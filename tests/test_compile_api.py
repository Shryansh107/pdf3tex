import base64
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app import app
from compiler import IMAGE, PDFLATEX_IMAGE, stage_assets, CompileError
from tests.test_app import pdf_bytes

client = TestClient(app)
ENGINE_AVAILABLE = bool(shutil.which('docker')) and subprocess.run(
    ['docker', 'image', 'inspect', IMAGE], capture_output=True, timeout=10).returncode == 0
engine = pytest.mark.skipif(not ENGINE_AVAILABLE, reason='Run ./install_engine.sh to test compilation')
PDFLATEX_AVAILABLE = bool(shutil.which('docker')) and subprocess.run(
    ['docker', 'image', 'inspect', PDFLATEX_IMAGE], capture_output=True, timeout=10).returncode == 0


@engine
def test_convert_edit_compile_returns_pdf_with_images():
    converted = client.post('/api/convert', data={'mode':'layout'}, files={'file': ('paper.pdf', pdf_bytes(image=True))}).json()
    source = converted['tex'].replace('improvement', 'improvement. EDITED SOURCE')
    response = client.post('/api/compile', json={'tex': source, 'project_zip': converted['zip']})
    assert response.status_code == 200, response.text
    result = response.json()
    with pymupdf.open(stream=base64.b64decode(result['pdf']), filetype='pdf') as doc:
        assert 'EDITED SOURCE' in ''.join(p.get_text() for p in doc)
        assert sum(len(p.get_images()) for p in doc) == 1
    assert result['engine'].startswith('Tectonic')
    assert result['log']


@engine
def test_bad_latex_returns_compiler_error_log():
    response = client.post('/api/compile', json={
        'tex': r'\documentclass{article}\begin{document}\thisCommandDoesNotExist\end{document}'})
    assert response.status_code == 422
    assert 'Undefined control sequence' in response.json()['detail']['log']
    assert 'compilation failed' in response.json()['detail']['message']


@engine
def test_compiler_cannot_read_host_files(tmp_path):
    secret = tmp_path / 'private.tex'
    secret.write_text('HOST FILE MUST NEVER BE INCLUDED')
    response = client.post('/api/compile', json={
        'tex': r'\documentclass{article}\begin{document}\input{' + str(secret) + r'}\end{document}'})
    assert response.status_code == 422
    assert 'HOST FILE MUST NEVER BE INCLUDED' not in response.text
    assert 'private.tex' in response.json()['detail']['log']


@engine
def test_infinite_tex_is_stopped_and_container_cleaned_up(monkeypatch):
    monkeypatch.setattr('compiler.TIMEOUT_SECONDS', 1)
    response = client.post('/api/compile', json={
        'tex': r'\documentclass{article}\begin{document}\loop\iftrue\repeat\end{document}'})
    assert response.status_code == 408
    run = subprocess.run(['docker', 'ps', '--filter', 'name=pdf3tex-compile-', '--format', '{{.Names}}'],
                         capture_output=True, text=True, timeout=10)
    assert not run.stdout.strip()


def test_invalid_zip_is_rejected(tmp_path):
    with pytest.raises(CompileError, match='Invalid project ZIP'):
        stage_assets('not-base64', tmp_path)


def test_zip_cannot_write_outside_assets(tmp_path):
    data = BytesIO()
    with ZipFile(data, 'w') as archive:
        archive.writestr('../escape.txt', 'never extracted')
        archive.writestr('main.tex', 'ignored')
        archive.writestr('assets/page_1_image_1.png', b'asset')
    stage_assets(base64.b64encode(data.getvalue()).decode(), tmp_path)
    assert (tmp_path / 'assets/page_1_image_1.png').read_bytes() == b'asset'
    assert not (tmp_path.parent / 'escape.txt').exists()
    assert not (tmp_path / 'main.tex').exists()


def test_empty_source_is_rejected():
    assert client.post('/api/compile', json={'tex': ''}).status_code == 422


@pytest.mark.skipif(not PDFLATEX_AVAILABLE, reason='Run ./install_pdflatex.sh first')
def test_supplied_pdflatex_source_compiles_with_background():
    with pymupdf.open() as doc:
        page = doc.new_page(width=612,height=792)
        page.draw_line((30,100),(580,100))
        background = doc.tobytes()
    bundle=BytesIO()
    with ZipFile(bundle,'w') as archive:
        archive.writestr('background.pdf',background)
    tex = r'''\documentclass{article}
\usepackage{tikz,graphicx}
\usepackage[paperwidth=612bp,paperheight=792bp,margin=0pt]{geometry}
\pagestyle{empty}
\begin{document}
\pdfpagewidth=612bp \pdfpageheight=792bp
\null\begin{tikzpicture}[remember picture,overlay]
\node[anchor=north west,inner sep=0] at (current page.north west){\includegraphics{background.pdf}};
\node[anchor=base west] at ([xshift=40bp,yshift=-80bp]current page.north west){Supplied editable source};
\end{tikzpicture}
\end{document}'''
    response = client.post('/api/compile',json={
        'tex':tex,'project_zip':base64.b64encode(bundle.getvalue()).decode(),'engine':'pdflatex'})
    assert response.status_code == 200,response.text
    with pymupdf.open(stream=base64.b64decode(response.json()['pdf']),filetype='pdf') as compiled:
        assert len(compiled)==1
        assert 'Supplied editable source' in compiled[0].get_text()
        assert len(compiled[0].get_drawings())>0
    assert response.json()['engine'].startswith('pdfLaTeX')


def test_compile_rejects_unknown_engine():
    assert client.post('/api/compile',json={'tex':'hello','engine':'unknown'}).status_code == 422
