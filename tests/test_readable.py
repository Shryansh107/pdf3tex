"""Readable source must preserve prose and edits, not just resemble a PDF."""
import base64
from io import BytesIO
import shutil
import subprocess
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app import app
from compiler import PDFLATEX_IMAGE, compile_latex
from converter import convert_pdf
from readable_converter import escape


def structured_pdf():
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 60), 'Example Reader', fontsize=22)
        page.insert_text((72, 100), 'Experience', fontsize=16, fontname='hebo')
        page.insert_text((72, 125), 'Developer', fontname='hebo')
        page.insert_text((390, 125), '2024 - 2026', fontname='hebo')
        page.insert_text((72, 140), 'Python / FastAPI', fontname='heit')
        page.insert_text((84, 165), '\u00b7 Built a useful feature with readable words.')
        page.insert_text((96, 179), 'It continues on the next visual line.')
        page.insert_text((72, 210), 'Technical Skills', fontsize=16, fontname='hebo')
        page.insert_text((72, 235), 'Languages:', fontname='hebo')
        page.insert_text((150, 235), 'Python, JavaScript')
        page.insert_text((72, 260), 'Documentation')
        page.insert_link({'kind': pymupdf.LINK_URI, 'from': pymupdf.Rect(70, 248, 160, 263),
                          'uri': 'https://example.com/docs?a=1&b=2'})
        page.insert_text((72, 290), 'Hidden OCR must not leak', render_mode=3)
        return doc.tobytes()


def test_readable_default_preserves_structure_words_and_links():
    response = TestClient(app).post('/api/convert', files={'file': ('example.pdf', structured_pdf())})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['mode'] == 'readable' and result['engine'] == 'pdflatex'
    tex = result['tex']
    assert r'\section*{Experience}' in tex
    assert '\\resumeSubheading\n  {Developer}{2024 - 2026}' in tex
    assert r'\item Built a useful feature with readable words.' in tex
    assert 'It continues on the next visual line.' in tex
    assert r'\textbf{Languages:} & Python, JavaScript' in tex
    assert r'\href{https://example.com/docs?a=1\&b=2}{Documentation}' in tex
    assert 'Hidden OCR' not in tex
    assert not any(token in tex for token in ('\\kern', '\\Spaced', '\\put(', 'fontspec', 'assets/'))
    with ZipFile(BytesIO(base64.b64decode(result['zip']))) as archive:
        assert archive.namelist() == ['main.tex']
        assert archive.read('main.tex').decode() == tex


def test_readable_scan_reports_layout_option():
    with pymupdf.open() as doc:
        doc.new_page()
        with pytest.raises(ValueError, match='Preserve original layout'):
            convert_pdf(doc.tobytes(), 'scan.pdf', 'readable')


def test_section_rules_and_selective_underlines_become_readable_commands():
    with pymupdf.open(stream=structured_pdf(), filetype='pdf') as doc:
        page = doc[0]
        page.draw_line((72, 104), (520, 104), width=.4)
        page.draw_rect(pymupdf.Rect(72, 214, 520, 214.4), color=None, fill=(0, 0, 0))
        page.draw_line((72, 126.5), (126, 126.5), width=.4)
        page.draw_line((72, 261.5), (149, 261.5), width=.4)
        # An unrelated line and vertical border must not underline body text.
        page.draw_line((72, 270), (150, 270), width=.4)
        page.draw_line((70, 160), (70, 180), width=.4)
        result = convert_pdf(doc.tobytes(), 'decorated.pdf', 'readable')
    tex = result['tex']
    assert tex.count('\\sectionrule\n') == 2
    assert r'{\underline{Developer}}{2024 - 2026}' in tex
    assert r'\href{https://example.com/docs?a=1\&b=2}{\underline{Documentation}}' in tex
    assert r'\item Built a useful feature with readable words.' in tex
    assert tex.count(r'\underline{') == 2


def test_unknown_characters_are_visible_and_reported():
    missing = set()
    text = escape('Budget: 50% & \u6f22', missing)
    assert text == r'Budget: 50\% \& \MissingGlyph{U+6F22}'
    assert missing == {'U+6F22'}


AVAILABLE = bool(shutil.which('docker')) and subprocess.run(
    ['docker', 'image', 'inspect', PDFLATEX_IMAGE], capture_output=True, timeout=10).returncode == 0


@pytest.mark.skipif(not AVAILABLE, reason='Install the pdfLaTeX compiler image')
def test_tex_ligatures_survive_reconstruction_and_normal_source_edits():
    # Produce real TeX ligatures with expanded MuPDF continuation glyphs.
    original = compile_latex(r'''\documentclass{article}
\begin{document}
\section*{Experience}
\begin{itemize}
\item Built efficient workflows and office features.
\end{itemize}
\section*{Skills}
Python and FastAPI.
\end{document}''', engine='pdflatex')
    pdf = base64.b64decode(original['pdf'])
    result = convert_pdf(pdf, 'ligatures.pdf', 'readable')
    assert 'Built efficient workflows and office features.' in result['tex']
    edited = result['tex'].replace('efficient workflows', 'editable source workflows')
    output = compile_latex(edited, engine='pdflatex')
    with pymupdf.open(stream=base64.b64decode(output['pdf']), filetype='pdf') as doc:
        text = ' '.join(page.get_text() for page in doc)
        assert 'editable source workflows' in text
        assert 'office features' in text
        assert len(doc) == 1
