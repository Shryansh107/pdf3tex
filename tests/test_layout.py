import base64
from io import BytesIO
import os
import re
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import pytest

from comparison import compare_pdfs
from converter import convert_pdf
from compiler import compile_latex
from layout_converter import recovered_words
from PIL import Image

REFERENCE_FILES = [p for p in os.environ.get('PDF3TEX_REFERENCES', os.environ.get('PDF3TEX_REFERENCE', '')).split(os.pathsep) if p]


def sample_pdf(x=72, second_page=False):
    with pymupdf.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_text((x,100), 'An editable document heading', fontsize=18)
        page.draw_line((40,120),(570,120),width=.5)
        page.insert_text((x,150), 'Text and layout should survive conversion.', fontsize=11)
        if second_page:
            doc.new_page(width=612,height=792).insert_text((72,100),'Second page')
        return doc.tobytes()


def test_comparison_is_exact_for_identical_pages():
    data = sample_pdf()
    result = compare_pdfs(data,data)
    assert result['similarity'] == 100
    assert result['matches']


def test_white_margins_do_not_hide_moved_text():
    result = compare_pdfs(sample_pdf(),sample_pdf(x=200))
    assert result['similarity'] < 95
    assert not result['matches']


def test_missing_page_fails_match_target():
    result = compare_pdfs(sample_pdf(second_page=True),sample_pdf())
    assert result['similarity'] == 0
    assert result['pages'][1]['reason']


def test_layout_keeps_dimensions_coordinates_and_editable_text():
    result = convert_pdf(sample_pdf(),'sample.pdf','layout')
    assert result['mode'] == 'layout'
    assert 'paperwidth=612.00000bp,paperheight=792.00000bp' in result['tex']
    assert r'\PDFunicode{72.00000}{692.00000}' in result['tex']
    assert 'An editable document heading' in result['tex']
    assert r'\rule{530.00000bp}' in result['tex']
    with ZipFile(BytesIO(base64.b64decode(result['zip']))) as archive:
        assert not any(name.endswith('.pdf') for name in archive.namelist())
        assert archive.read('main.tex').decode() == result['tex']


@pytest.mark.parametrize('reference_file', REFERENCE_FILES or [None])
@pytest.mark.skipif(not REFERENCE_FILES, reason='Set PDF3TEX_REFERENCE(S) to test local reference PDFs')
def test_reference_pdf_exceeds_visual_match_target(reference_file):
    data = Path(reference_file).read_bytes()
    result = convert_pdf(data,'reference.pdf','layout')
    compiled = compile_latex(result['tex'],result['zip'],base64.b64encode(data).decode())
    assert compiled['comparison']['matches'], compiled['comparison']
    assert compiled['comparison']['similarity'] >= 95
    with pymupdf.open(stream=base64.b64decode(compiled['pdf']),filetype='pdf') as pdf:
        assert sum(len(page.get_text()) for page in pdf) > 100


def test_original_glyph_positions_restore_word_kerning():
    font = {'codes': {1:ord('A'),2:ord('V'),3:ord('X')}, 'advances':{1:600,2:600,3:600}}
    trace = {'size':10,'chars':[(65,1,(10,30),None),(86,2,(15.5,30),None),(88,3,(29,30),None)]}
    assert list(recovered_words(trace,font)) == [((10,30),r'A\kern-0.50000bp V'),((29,30),'X')]


def test_filled_vector_rectangles_are_retained():
    with pymupdf.open(stream=sample_pdf(),filetype='pdf') as doc:
        doc[0].draw_rect(pymupdf.Rect(40,30,570,34),fill=(0,0,0),color=None)
        result=convert_pdf(doc.tobytes(),'filled-rule.pdf','layout')
    assert r'\rule{530.00000bp}{4.00000bp}' in result['tex']


def test_figure_soft_mask_survives_asset_extraction():
    image=Image.new('RGBA',(16,16),(255,0,0,128))
    image.putpixel((0,0),(0,0,0,0))
    buffer=BytesIO();image.save(buffer,format='PNG')
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((72,50),'Transparent figure')
        page.insert_image(pymupdf.Rect(72,72,150,150),stream=buffer.getvalue())
        result=convert_pdf(doc.tobytes(),'alpha.pdf','layout')
    with ZipFile(BytesIO(base64.b64decode(result['zip']))) as archive:
        asset=next(name for name in archive.namelist() if name.endswith('.png'))
        extracted=Image.open(BytesIO(archive.read(asset)))
        assert extracted.mode=='RGBA'
        assert extracted.getpixel((0,0))[3]==0
        assert extracted.getpixel((8,8))[3]==128


@pytest.mark.parametrize('reference_file', REFERENCE_FILES or [None])
@pytest.mark.skipif(not REFERENCE_FILES, reason='Set PDF3TEX_REFERENCE(S) for editable source regressions')
def test_recovered_words_remain_editable(reference_file):
    data=Path(reference_file).read_bytes()
    result=convert_pdf(data,'reference.pdf','layout')
    match=re.search(r'\\PDF(?:unicode|text)[^\n]*?\\color\[rgb\]\{[^}]*\}([A-Za-z]{5,})\}',result['tex'])
    if not match:
        pytest.skip('Reference has no recovered word without spacing commands')
    word=match.group(1)
    edited=result['tex'][:match.start(1)]+word[::-1]+result['tex'][match.end(1):]
    compiled=compile_latex(edited,result['zip'])
    with pymupdf.open(stream=base64.b64decode(compiled['pdf']),filetype='pdf') as doc:
        assert word[::-1] in ''.join(page.get_text() for page in doc)
