"""Portable exports must compile with only editor contents, never ZIP assets."""
import base64
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app import app
from compiler import compile_latex, PDFLATEX_IMAGE
from converter import convert_pdf
from tests.test_app import pdf_bytes

client = TestClient(app)
AVAILABLE = bool(shutil.which('docker')) and subprocess.run(['docker','image','inspect',PDFLATEX_IMAGE],capture_output=True,timeout=10).returncode == 0
engine = pytest.mark.skipif(not AVAILABLE,reason='Run ./install_pdflatex.sh')
REFERENCES = [p for p in os.environ.get('PDF3TEX_REFERENCES','').split(os.pathsep) if p]


def test_default_upload_is_self_contained():
    response = client.post('/api/convert',files={'file':('sample.pdf',pdf_bytes(image=True))})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['mode'] == 'portable'
    assert result['engine'] == 'pdflatex'
    assert result['fidelity_target'] == 90
    assert result['images'] == 1
    assert 'improvement' in result['tex']
    for dependency in ('fontspec','includegraphics','newfontface','assets/','filecontents','\\input{'):
        assert dependency not in result['tex']
    with ZipFile(BytesIO(base64.b64decode(result['zip']))) as archive:
        assert archive.namelist() == ['main.tex']
        assert archive.read('main.tex').decode() == result['tex']


@engine
def test_copy_paste_and_edit_compile_without_zip():
    original = pdf_bytes(image=True)
    result = convert_pdf(original,'sample.pdf','portable')
    response = client.post('/api/compile',json={
        'tex':result['tex'],'engine':'pdflatex','fidelity_target':90,
        'original_pdf':base64.b64encode(original).decode()})
    assert response.status_code == 200, response.text
    comparison = response.json()['comparison']
    assert comparison['target'] == 90
    assert comparison['similarity'] >= 90, comparison
    assert comparison['matches']
    edited = compile_latex(result['tex'].replace('improvement','EDITEDLONGERWORD'),engine='pdflatex')
    with pymupdf.open(stream=base64.b64decode(edited['pdf']),filetype='pdf') as doc:
        assert len(doc) == 1
        assert 'EDITEDLONGERWORD' in doc[0].get_text()
        assert not doc[0].get_images()  # Illustration is a vector, body is text.
        assert doc[0].get_drawings()


def test_scan_is_not_disguised_as_editable_latex():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72,100),'Invisible OCR',render_mode=3)
        response = client.post('/api/convert',files={'file':('scan.pdf',doc.tobytes())})
    assert response.status_code == 422
    assert 'no visible text layer' in response.json()['detail']


def test_visual_target_changes_pass_fail_without_changing_score(monkeypatch):
    monkeypatch.setattr('app.compile_latex',lambda *args: {'comparison':{
        'similarity':91.5,'target':95,'matches':False,'pages':[{'page':1,'similarity':91.5}]}})
    for target,passed in [(90,True),(95,False)]:
        response = client.post('/api/compile',json={'tex':'test','fidelity_target':target})
        comparison = response.json()['comparison']
        assert comparison['similarity'] == 91.5
        assert comparison['matches'] is passed
        assert comparison['target'] == target


@engine
@pytest.mark.parametrize('reference',REFERENCES or [None])
@pytest.mark.skipif(not REFERENCES,reason='Set PDF3TEX_REFERENCES for private references')
def test_portable_references_reach_90_on_every_page_without_assets(reference):
    original = Path(reference).read_bytes()
    result = convert_pdf(original,Path(reference).name,'portable')
    compiled = compile_latex(result['tex'],original_pdf=base64.b64encode(original).decode(),engine='pdflatex')
    comparison = compiled['comparison']
    assert comparison['similarity'] >= 90, comparison
    with pymupdf.open(stream=base64.b64decode(compiled['pdf']),filetype='pdf') as doc:
        assert len(doc) == result['pages']
        assert sum(len(page.get_text()) for page in doc) > 100
        assert not any(page.get_images() for page in doc)
