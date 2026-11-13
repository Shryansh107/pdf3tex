"""Font regressions use generated programs, without private PDF fixtures."""
import base64
from io import BytesIO
from zipfile import ZipFile

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from matplotlib.ft2font import FT2Font
from PIL import Image
import pymupdf
import pytest

from compiler import compile_latex
from converter import convert_pdf
from font_reconstruction import load_font, recover_font
from layout_converter import image_asset
from pdf_fonts import FontRegistry, visible
from portable_converter import OutlinePen, standard_face
from tests.test_portable import engine


def generated_font(reverse=False, cff=False, units=2048):
    names = ['.notdef', 'space', 'A', 'B', 'quotesingle', 'bullet', 'underscore', 'Eacute', 'fl']
    if reverse:
        names[2:4] = reversed(names[2:4])
    mapping = {32:'space', 65:'A', 66:'B', 39:'quotesingle', 0x2022:'bullet', 95:'underscore', 201:'Eacute', 0xFB02:'fl'}
    builder = FontBuilder(units, isTTF=not cff)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap(mapping)
    outlines, metrics = {}, {}
    for index, name in enumerate(names):
        width = round(units * (.8 if reverse else .6))
        pen = T2CharStringPen(width, None) if cff else TTGlyphPen(None)
        if name not in ('.notdef', 'space'):
            pen.moveTo((0, 0))
            pen.lineTo((units * .4, 0))
            pen.lineTo((units * (.2 if reverse else .4), units * .6))
            pen.closePath()
        outlines[name] = pen.getCharString() if cff else pen.glyph()
        metrics[name] = (width if name != 'space' else round(units / 3), 0)
    if cff:
        builder.setupCFF('RepeatedSubset', {'FullName':'RepeatedSubset', 'FamilyName':'RepeatedSubset', 'Weight':'Regular'}, outlines, {})
    else:
        builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=round(units * .8), descent=-round(units * .2))
    builder.setupNameTable({'familyName':'RepeatedSubset', 'styleName':'Regular', 'uniqueFontIdentifier':'RepeatedSubset', 'fullName':'RepeatedSubset', 'psName':'RepeatedSubset'})
    builder.setupOS2(sTypoAscender=round(units * .8), sTypoDescender=-round(units * .2), usWinAscent=units, usWinDescent=units)
    builder.setupPost()
    output = BytesIO()
    builder.save(output)
    return output.getvalue()


def duplicate_name_pdf(second_page=False):
    with pymupdf.open() as doc:
        page = doc.new_page(width=300, height=300)
        for index, reverse in enumerate((False, True)):
            if index and second_page:
                page = doc.new_page(width=300, height=300)
            name = 'Face' + str(index)
            page.insert_font(fontname=name, fontbuffer=generated_font(reverse))
            page.insert_text((40, 80 + index * 80), 'AB BA', fontname=name, fontsize=24)
        return doc.tobytes()


@pytest.mark.parametrize('second_page', [False, True])
def test_same_named_programs_have_distinct_identities(second_page):
    with pymupdf.open(stream=duplicate_name_pdf(second_page), filetype='pdf') as doc:
        registry = FontRegistry(doc)
        traces = [t for page in registry.pages for t in page]
        assert len({t['font'] for t in traces}) == 1
        assert len({t['font_key'] for t in traces}) == 2
        widths = {round(registry.resources[t['font_key']].program().width(t['chars'][0][1]), 2) for t in traces}
        assert widths == {.6, .8}
    result = convert_pdf(duplicate_name_pdf(second_page), 'same-name.pdf', 'layout')
    with ZipFile(BytesIO(base64.b64decode(result['zip']))) as archive:
        assert len([p for p in archive.namelist() if p.endswith('.ttf')]) == 2
    assert '\\Spaced{AB}' in result['tex']


def test_repaired_cmap_maps_observed_unicode_to_actual_glyph():
    program = load_font(generated_font())
    gid = program.order.index('B')
    data, codes, advances, space, extension = recover_font(program, 'Repaired', {(65, gid), (0xFFFD, gid)})
    repaired = TTFont(BytesIO(data))
    assert repaired.getBestCmap()[codes[65, gid]] == 'B'
    assert codes[0xFFFD, gid] >= 0xF0000
    assert extension == 'ttf'
    assert 'glyf' in repaired and 'GSUB' not in repaired and 'kern' not in repaired
    assert advances[gid] == pytest.approx(program.width(gid) * 1000)


def test_raw_cff_can_be_read_and_reconstructed():
    font = TTFont(BytesIO(generated_font(cff=True, units=1000)))
    output = BytesIO()
    font['CFF '].cff.compile(output, font)
    raw = output.getvalue()
    program = load_font(raw)
    gid = program.order.index('A')
    assert program.width(gid) == pytest.approx(.6)
    data, codes, _, _, extension = recover_font(program, 'CFFRecovered', {(65, gid)})
    assert extension == 'otf'
    assert FT2Font(BytesIO(data)).num_glyphs == len(program.order)
    assert load_font(data).cmap[codes[65, gid]] == 'A'
    assert load_font(data).cff[0].CharStrings['A'].bytecode == load_font(raw).cff[0].CharStrings['A'].bytecode


def test_stencil_samples_become_transparency_in_the_paint_color():
    image = Image.new('L', (2,1), 0)
    image.putpixel((1,0), 255)
    raw = BytesIO()
    image.save(raw, format='PNG')
    asset = image_asset({'image': raw.getvalue(), 'colorspace':0}, {'color':(1,0,0), 'opacity':.5})
    result = Image.open(BytesIO(asset))
    assert result.getpixel((0,0)) == (255,0,0,0)
    assert result.getpixel((1,0)) == (255,0,0,128)


def test_layout_preserves_image_and_redaction_paint_order():
    raw = BytesIO()
    Image.new('RGB', (8,8), 'white').save(raw, format='PNG')
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_image(pymupdf.Rect(40,40,200,200), stream=raw.getvalue())
        page.draw_rect(pymupdf.Rect(60,60,180,80), fill=(0,0,0), color=None)
        result = convert_pdf(doc.tobytes(), 'redaction.pdf', 'layout')
    body = result['tex'].split('\\begin{document}',1)[1]
    assert body.index('\\PDFimage{') < body.index('\\rule{')


def test_outline_pen_uses_truetype_units():
    program = load_font(generated_font())
    pen = OutlinePen(program.glyphs, program.units)
    program.glyphs['A'].draw(pen)
    assert '0.3999 0 l' in pen.commands
    assert '819' not in ' '.join(pen.commands)


def test_common_glyphs_remain_text_in_portable_output():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_font(fontname='Custom', fontbuffer=generated_font())
        page.insert_text((72,100), "AB ' \u2022 _ \u00c9 \ufb02", fontname='Custom')
        result = convert_pdf(doc.tobytes(), 'punctuation.pdf', 'portable')
    assert 'AB' in result['tex']
    for code in (31, 149, 95, 201, 3):
        assert f'\\char{code}{{}}' in result['tex']
    assert '\\newcommand{\\symbol' not in result['tex']
    assert standard_face('UnknownSerif', 4) == 'ptmr8r'
    assert standard_face('Unknown', 16) == 'phvb8r'


@pytest.mark.parametrize('mode', ['layout', 'portable'])
def test_invisible_ocr_and_zero_opacity_text_are_not_exported(mode):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72,100), 'Visible body')
        page.insert_text((72,140), 'HiddenOCR', fontname='tiro', render_mode=3)
        page.insert_text((72,180), 'TransparentOCR', fontname='cour', fill_opacity=0)
        registry = FontRegistry(doc)
        assert [visible(t) for t in registry.pages[0]] == [True, False, False]
        result = convert_pdf(doc.tobytes(), 'hidden.pdf', mode)
    assert 'Visible' in result['tex'] and 'body' in result['tex']
    assert 'HiddenOCR' not in result['tex'] and 'TransparentOCR' not in result['tex']
    if mode == 'layout':
        assert result['tex'].count('\\newfontface') == 1


@engine
def test_duplicate_subset_fonts_compile_with_the_original_glyphs():
    source = duplicate_name_pdf(second_page=True)
    result = convert_pdf(source, 'subsets.pdf', 'layout')
    compiled = compile_latex(result['tex'], result['zip'], base64.b64encode(source).decode())
    # Subpixel rounding of 2048-unit metrics by the PDF writer affects SSIM
    # on these few sharp polygons. Also check glyph identities and positions.
    assert compiled['comparison']['similarity'] >= 90, compiled['comparison']
    with pymupdf.open(stream=source, filetype='pdf') as before, pymupdf.open(stream=base64.b64decode(compiled['pdf']), filetype='pdf') as after:
        first, second = FontRegistry(before), FontRegistry(after)
        for index, (original, output) in enumerate(zip(before, after)):
            a = [c for t in original.get_texttrace() for c in t['chars'] if c[0] != 32]
            b = [c for t in output.get_texttrace() for c in t['chars'] if c[0] != 32]
            assert [c[0] for c in a] == [c[0] for c in b]
            for expected, actual in zip(a, b):
                assert actual[2] == pytest.approx(expected[2], abs=.05)
            original_font = first.resources[first.pages[index][0]['font_key']].program()
            rebuilt_font = second.resources[second.pages[index][0]['font_key']].program()
            p, q = OutlinePen(original_font.glyphs, original_font.units), OutlinePen(rebuilt_font.glyphs, rebuilt_font.units)
            original_font.glyphs[original_font.glyph_name(a[0][1])].draw(p)
            rebuilt_font.glyphs[rebuilt_font.glyph_name(b[0][1])].draw(q)
            assert p.commands == q.commands
    edited = compile_latex(result['tex'].replace('\\Spaced{AB}', '\\Spaced{BA}'), result['zip'])
    with pymupdf.open(stream=base64.b64decode(edited['pdf']), filetype='pdf') as doc:
        assert len(doc) == 2
        assert all(page.get_text().replace(' ', '').strip() == 'BABA' for page in doc)


@engine
def test_compiled_cid_subsets_can_be_reconstructed_again():
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72,100), 'Subset glyphs retain their identities')
        source = doc.tobytes()
    result = convert_pdf(source, 'base14.pdf', 'layout')
    first = compile_latex(result['tex'], result['zip'])
    original = base64.b64decode(first['pdf'])
    result = convert_pdf(original, 'cid-subset.pdf', 'layout')
    second = compile_latex(result['tex'], result['zip'], first['pdf'])
    assert second['comparison']['similarity'] >= 95, second['comparison']


@engine
def test_leading_and_repeated_spaces_keep_glyph_positions():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72,100), '  leading  spaces stay visible', fontsize=12)
        source = doc.tobytes()
    result = convert_pdf(source, 'spaces.pdf', 'layout')
    assert r'\ \ leading\ \ spaces\ stay\ visible' in result['tex']
    compiled = compile_latex(result['tex'], result['zip'], base64.b64encode(source).decode())
    assert compiled['comparison']['similarity'] >= 95, compiled['comparison']
