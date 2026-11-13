import base64
from io import BytesIO
from zipfile import ZipFile

import pymupdf
from fastapi.testclient import TestClient
import pytest

from app import app
from converter import convert_pdf

client = TestClient(app)


def pdf_bytes(text="Research & results: 50% improvement", image=False):
    with pymupdf.open() as doc:
        page = doc.new_page()
        if text:
            page.insert_text((72, 100), text)
        if image:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
            pix.clear_with(120)
            page.insert_image(pymupdf.Rect(72, 150, 112, 190), pixmap=pix)
        return doc.tobytes()


def test_upload_returns_escaped_source_and_complete_project():
    response = client.post('/api/convert', data={'mode':'layout'}, files={'file': ('paper.pdf', pdf_bytes(image=True), 'application/pdf')})
    assert response.status_code == 200
    result = response.json()
    assert r'Research \& results: 50\% improvement' in result['tex']
    assert result['pages'] == 1 and result['images'] == 1 and result['ocr_pages'] == 0
    assert '<pdf2tex.' not in result['tex']
    with ZipFile(BytesIO(base64.b64decode(result['zip']))) as archive:
        assert archive.read('main.tex').decode() == result['tex']
        assets = [p for p in archive.namelist() if p.endswith('.png')]
        assert len(assets) == 1
        assert assets[0] in result['tex']
        assert archive.read(assets[0]).startswith(b'\x89PNG')
        assert any(p.endswith(('.otf', '.ttf')) for p in archive.namelist())


def test_scan_routes_through_ocr(monkeypatch):
    monkeypatch.setattr('converter.read_scan', lambda page: ['Scanned page & OCR'])
    result = convert_pdf(pdf_bytes(text='', image=True), 'scan.pdf')
    assert result['ocr_pages'] == 1
    assert r'Scanned page \& OCR' in result['tex']
    assert result['images'] == 0


@pytest.mark.parametrize('filename,data,status', [
    ('bad.txt', b'hello', 400), ('bad.pdf', b'hello', 400),
    ('bad.pdf', b'%PDF-1.7\nbroken', 422), ('empty.pdf', b'', 400),
    ('big.pdf', b'%PDF-' + b'x' * (20 * 1024 * 1024), 413),
])
def test_invalid_uploads(filename, data, status):
    response = client.post('/api/convert', files={'file': (filename, data)})
    assert response.status_code == status
    assert isinstance(response.json()['detail'], str)


def test_encrypted_pdf_rejected():
    with pymupdf.open(stream=pdf_bytes(), filetype='pdf') as doc:
        locked = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
    response = client.post('/api/convert', files={'file': ('locked.pdf', locked)})
    assert response.status_code == 422
    assert 'password' in response.json()['detail']


def test_page_limit():
    with pymupdf.open() as doc:
        for _ in range(51):
            doc.new_page()
        response = client.post('/api/convert', files={'file': ('long.pdf', doc.tobytes())})
    assert response.status_code == 422


def test_multiple_pages_keep_order():
    with pymupdf.open() as doc:
        for text in ['First page', 'Second page']:
            doc.new_page().insert_text((72, 100), text)
        result = convert_pdf(doc.tobytes(), 'two.pdf')
    assert result['tex'].index('First page') < result['tex'].index('Second page')
    assert r'\clearpage' in result['tex']
    assert result['pages'] == 2


def test_workspace_and_health():
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/api/health').json()['status'] == 'ok'
