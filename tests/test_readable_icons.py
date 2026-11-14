"""Real compiler round trips for named icons, styles and outline fallbacks."""
import base64
from io import BytesIO
import re

from fontTools.ttLib import TTFont
import pymupdf
import pytest

from compiler import compile_latex
from converter import convert_pdf
from readable_icons import IconExporter
from tests.test_pdf_fonts import generated_font
from tests.test_portable import engine


@engine
def test_fontawesome_icons_keep_names_styles_and_superscripts():
    original = compile_latex(r'''\documentclass{article}
\usepackage{fontawesome5}
\usepackage[hidelinks]{hyperref}
\begin{document}
\section*{Experience}
Visit \href{https://example.com}{Website\,\textsuperscript{\faExternalLink*}}.
Regular \faIcon[regular]{address-book}, brand \faGithub.
\section*{Skills}
Python and FastAPI.
\end{document}''', engine='pdflatex')
    result = convert_pdf(base64.b64decode(original['pdf']), 'icons.pdf')
    tex = result['tex']
    assert r'\usepackage{fontawesome5}' in tex
    assert r'\faExternalLink*' in tex
    assert r'\faIcon[regular]{address-book}' in tex
    assert r'\faGithub' in tex
    assert r'\IconExternalLinkAlt' in tex.split(r'\begin{document}')[1]
    assert '\ufffc' not in tex
    assert not any('omitted' in warning or 'fallback' in warning for warning in result['warnings'])
    match = re.search(r'\\newcommand\{\\IconExternalLinkAlt\}.*?\\raisebox\{([\d.]+)bp\}', tex, re.S)
    assert match and 3 < float(match[1]) < 5
    output = compile_latex(tex.replace('Python and FastAPI', 'Editable icon document'), engine='pdflatex')
    with pymupdf.open(stream=base64.b64decode(output['pdf']), filetype='pdf') as doc:
        assert len(doc) == 1
        assert 'Editable icon document' in doc[0].get_text()
        fonts = [font[3] for font in doc[0].get_fonts()]
        assert any('FontAwesome5Free-Solid' in font for font in fonts)
        assert any('FontAwesome5Free-Regular' in font for font in fonts)
        assert any('FontAwesome5Brands-Regular' in font for font in fonts)


@engine
def test_unknown_icon_font_becomes_reusable_inline_vector_without_assets():
    font = TTFont(BytesIO(generated_font()))
    for name_id in (1, 4, 6):
        font['name'].setName('CustomIcons', name_id, 3, 1, 0x409)
    data = BytesIO()
    font.save(data)
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 100), 'Custom icons remain editable.')
        page.insert_font(fontname='CustomIcons', fontbuffer=data.getvalue())
        page.insert_text((250, 96), 'A', fontname='CustomIcons', fontsize=9)
        page.insert_text((270, 96), 'A', fontname='CustomIcons', fontsize=9)
        result = convert_pdf(doc.tobytes(), 'custom-icons.pdf')
    tex = result['tex']
    preamble, body = tex.split(r'\begin{document}')
    assert preamble.count(r'\newcommand{\IconA}') == 1
    assert body.count(r'\IconA') == 2
    assert r'\IconVector' not in body and r'\faIcon' not in tex
    assert any('named vector fallback' in warning for warning in result['warnings'])
    output = compile_latex(tex, engine='pdflatex')
    with pymupdf.open(stream=base64.b64decode(output['pdf']), filetype='pdf') as doc:
        assert 'Custom icons remain editable.' in doc[0].get_text()
        rectangles = [path['rect'] for path in doc[0].get_drawings()]
        # The original outline is .4 x .6 em, scaled to a 9 bp icon.
        assert sum(abs(rect.width - 3.6) < .03 and abs(rect.height - 5.4) < .03
                   for rect in rectangles) == 2
        assert not doc[0].get_images()


def test_unrecoverable_icon_gets_a_visible_placeholder():
    class Resource:
        identity = 'missing'
        name = 'UnknownIcons'

    warnings = set()
    icons = IconExporter(warnings)
    command = icons.command(Resource(), None, 7, 0xFFFD, 10, 0)
    assert command.startswith(r'\IconUnknown')
    assert r'\fbox{\scriptsize icon}' in icons.preamble()
    assert any('visible placeholder' in warning for warning in warnings)
