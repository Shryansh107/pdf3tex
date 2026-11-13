"""Reconstruct PDF text at its original coordinates rather than reflowing it."""
import base64
from io import BytesIO
import re
from zipfile import ZipFile, ZIP_DEFLATED

import pymupdf
from pdf2tex import Utils
from font_reconstruction import recover_type1
from fontTools.t1Lib import T1Error
from fontTools.ttLib import TTLibError


def unicode_codes(doc, xref):
    mapping = {}
    entry = doc.xref_get_key(xref, 'ToUnicode')[1]
    if not entry.endswith(' R'):
        return mapping
    cmap = doc.xref_stream(int(entry.split()[0])).decode('latin1')
    for section in re.findall(r'beginbfrange(.*?)endbfrange', cmap, re.S):
        for start, end, first in re.findall(r'<([\dA-Fa-f]+)>\s*<([\dA-Fa-f]+)>\s*<([\dA-Fa-f]+)>', section):
            for code in range(int(start, 16), min(int(end, 16) + 1, int(start, 16) + 256)):
                mapping.setdefault(chr(int(first, 16) + code - int(start, 16)), code)
    for section in re.findall(r'beginbfchar(.*?)endbfchar', cmap, re.S):
        for code, value in re.findall(r'<([\dA-Fa-f]+)>\s*<([\dA-Fa-f]+)>', section):
            try:
                mapping.setdefault(bytes.fromhex(value).decode('utf-16-be'), int(code, 16))
            except (ValueError, UnicodeError):
                continue
    return mapping


def encoded_text(text, mapping):
    # Keep normal words editable. Explicit character codes preserve the PDF's
    # legacy-font punctuation encoding, rather than substituting Unicode glyphs.
    out = []
    for char in text:
        if char.isascii() and (char.isalnum() or char in ' .,;:!?()-/+=@[]'):
            out.append(char)
        elif char in mapping:
            out.append(r'\char"' + format(mapping[char], 'X') + '{}')
        else:
            out.append(Utils.escape_special_chars(char))
    return ''.join(out)


def recovered_words(trace, font):
    """Editable Unicode words with explicit corrections for PDF glyph spacing."""
    words, current = [], []
    for char in trace['chars']:
        unicode, gid, origin, _ = char
        if gid not in font['codes']:
            continue
        if chr(unicode).isspace():
            if current:
                words.append(current)
                current = []
            continue
        if current:
            prev = current[-1]
            advance = font['advances'][prev[1]] / 1000 * trace['size']
            gap = origin[0] - prev[2][0] - advance
            if abs(origin[1] - prev[2][1]) > .01 or gap > trace['size'] * .18:
                words.append(current)
                current = []
        current.append(char)
    if current:
        words.append(current)
    for word in words:
        content, previous = [], None
        for unicode, gid, origin, bbox in word:
            if previous is not None:
                kern = origin[0] - previous[2][0] - font['advances'][previous[1]] / 1000 * trace['size']
                if abs(kern) > .0001:
                    content.append(f'\\kern{kern:.5f}bp ')
            code = font['codes'][gid]
            char = chr(code)
            if char in '\\&%$#_{}~^' or code >= 0xF0000:
                content.append('\\char"' + format(code, 'X') + '{}')
            else:
                content.append(char)
            previous = (unicode, gid, origin, bbox)
        yield word[0][2], ''.join(content)


def convert_layout(data, filename):
    doc = pymupdf.open(stream=data, filetype='pdf')
    with doc:
        if doc.needs_pass:
            raise ValueError('This PDF is password protected. Upload an unlocked copy.')
        if not 1 <= len(doc) <= 50:
            raise ValueError('Upload a PDF with 1–50 pages.')
        assets, body, definitions, warnings = {}, [], [], []
        fonts, char_count, graphics, fallback_fonts = {}, 0, 0, set()
        traces = [page.get_texttrace() for page in doc]
        observed = {}
        for page_traces in traces:
            for trace in page_traces:
                observed.setdefault(trace['font'], set()).update((c[0], c[1]) for c in trace['chars'])
        recovered = {}
        for page in doc:
            for xref, ext, kind, name, *_ in page.get_fonts(full=True):
                base = re.sub(r'^[A-Z]{6}\+', '', name)
                if base in fonts:
                    continue
                mapping = unicode_codes(doc, xref)
                legacy = bool(re.fullmatch(r'CM(?:R|BX|TI|SL|TT|CSC|SY|BSY|MI|EX|SS|SSI|SSBX)\d+', base, re.I))
                if ext in ('pfa', 'pfb') and (not mapping or not legacy):
                    key = f'font_{len(fonts)}'
                    command = 'PDFfont' + ''.join(chr(97 + int(d)) for d in str(len(fonts)))
                    try:
                        data, codes, advances = recover_type1(doc.extract_font(xref)[3], 'Recovered' + str(xref), observed.get(base, set()))
                    except (T1Error, TTLibError, ValueError, RuntimeError, KeyError, AssertionError, EOFError) as exc:
                        warnings.append(f'Embedded font {base} could not be reconstructed ({exc}); using a substitute.')
                        fonts[base] = ('fallback', '', {})
                        continue
                    assets[f'assets/{key}.otf'] = data
                    definitions.append('\\newfontface\\' + command + '[Path=assets/]{' + key + '.otf}')
                    fonts[base] = ('recovered', '\\' + command, {})
                    recovered[base] = {'command': '\\' + command, 'codes': codes, 'advances': advances}
                elif legacy:
                    fonts[base] = ('legacy', base.lower(), unicode_codes(doc, xref))
                elif ext in ('ttf', 'otf'):
                    key = f'font_{len(fonts)}'
                    asset = f'assets/{key}.{ext}'
                    assets[asset] = doc.extract_font(xref)[3]
                    command = 'PDFfont' + ''.join(chr(97 + int(d)) for d in str(len(fonts)))
                    definitions.append('\\newfontface\\' + command + '[Path=assets/]{' + key + '.' + ext + '}')
                    fonts[base] = ('unicode', '\\' + command, {})
                else:
                    fonts[base] = ('fallback', '', {})
        w, h = doc[0].rect.width, doc[0].rect.height
        preamble = (f'% !TeX program = xelatex\n% Editable text placed at original PDF coordinates.\n'
                    '\\documentclass{article}\n\\usepackage{fontspec,graphicx,color}\n'
                    '\\setmainfont{lmroman10-regular.otf}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf,BoldItalicFont=lmroman10-bolditalic.otf]\n'
                    '\\setsansfont{lmsans10-regular.otf}[BoldFont=lmsans10-bold.otf,ItalicFont=lmsans10-oblique.otf,BoldItalicFont=lmsans10-boldoblique.otf]\n'
                    f'\\usepackage[paperwidth={w:.5f}bp,paperheight={h:.5f}bp,margin=0bp]{{geometry}}\n'
                    '\\pagestyle{empty}\n\\setlength{\\parindent}{0pt}\n\\setlength{\\topskip}{0pt}\n'
                    '\\setlength{\\unitlength}{1bp}\n'
                    '\\newcommand{\\PDFimage}[5]{\\put(#1,#2){\\IfFileExists{#5}'
                    '{\\includegraphics[width=#3bp,height=#4bp]{#5}}{\\framebox(#3,#4){}}}}\n'
                    '\\newcommand{\\PDFtext}[5]{\\put(#1,#2){\\makebox[0pt][l]{\\begingroup'
                    '\\font\\PDFfont=#3 at #4bp\\PDFfont #5\\endgroup}}}\n'
                    '\\newcommand{\\PDFunicode}[5]{\\put(#1,#2){\\makebox[0pt][l]{\\begingroup'
                    '\\fontsize{#4bp}{#4bp}\\selectfont #3#5\\endgroup}}}\n'
                    + '\n'.join(definitions) + '\n\\begin{document}\n')
        for number, page in enumerate(doc, 1):
            pw, ph = page.rect.width, page.rect.height
            body.append(f'% Page {number}\n\\noindent\\begin{{picture}}({pw:.5f},{ph:.5f})')
            # Lines remain vector rules rather than becoming a page screenshot.
            for path in page.get_drawings():
                for item in path['items']:
                    if item[0] == 're' and path['type'] == 'f':
                        rect = item[1]
                        color = path.get('fill') or (0, 0, 0)
                        body.append(f'\\put({rect.x0:.5f},{ph-rect.y1:.5f})'
                                    f'{{\\color[rgb]{{{color[0]:.5f},{color[1]:.5f},{color[2]:.5f}}}'
                                    f'\\rule{{{rect.width:.5f}bp}}{{{rect.height:.5f}bp}}}}')
                    if item[0] == 'l' and abs(item[1].y - item[2].y) < .01:
                        x1, x2 = sorted([item[1].x, item[2].x])
                        thickness = max(path['width'] or .4, .1)
                        color = path.get('color') or (0, 0, 0)
                        body.append(f'\\put({x1:.5f},{ph-item[1].y-thickness/2:.5f})'
                                    f'{{\\color[rgb]{{{color[0]:.5f},{color[1]:.5f},{color[2]:.5f}}}'
                                    f'\\rule{{{x2-x1:.5f}bp}}{{{thickness:.5f}bp}}}}')
            for block in page.get_text('dict', sort=False)['blocks']:
                if block['type'] == 1:
                    graphics += 1
                    name = f'assets/page_{number}_image_{graphics}.png'
                    pix = pymupdf.Pixmap(block['image'])
                    if pix.colorspace and pix.colorspace.n > 3:
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    if block.get('mask'):
                        pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(block['mask']))
                    assets[name] = pix.tobytes('png')
                    x0,y0,x1,y1 = block['bbox']
                    body.append(f'\\PDFimage{{{x0:.5f}}}{{{ph-y1:.5f}}}{{{x1-x0:.5f}}}{{{y1-y0:.5f}}}{{{name}}}')
                    continue
                for line in block.get('lines', []):
                    for span in line['spans']:
                        text = span['text']
                        if not text.strip():
                            continue
                        char_count += len(text)
                        x, y = span['origin']
                        size = span['size']
                        font = re.sub(r'^[A-Z]{6}\+', '', span['font'])
                        kind, fontcommand, mapping = fonts.get(font, ('fallback', '', {}))
                        if kind == 'recovered':
                            continue
                        rgb = pymupdf.sRGB_to_pdf(span['color'])
                        color = f'\\color[rgb]{{{rgb[0]:.5f},{rgb[1]:.5f},{rgb[2]:.5f}}}'
                        if kind == 'legacy':
                            body.append(f'\\PDFtext{{{x:.5f}}}{{{ph-y:.5f}}}{{{fontcommand}}}{{{size:.5f}}}{{{color}{encoded_text(text, mapping)}}}')
                        elif 'Awesome' in font or 'Symbol' in font:
                            # Preserve tiny pictograms whose PDF Unicode map is
                            # absent/wrong; body text is always reconstructed.
                            graphics += 1
                            name = f'assets/page_{number}_image_{graphics}.png'
                            rect = pymupdf.Rect(span['bbox'])
                            assets[name] = page.get_pixmap(matrix=pymupdf.Matrix(4,4), clip=rect, alpha=True).tobytes('png')
                            body.append(f'\\PDFimage{{{rect.x0:.5f}}}{{{ph-rect.y1:.5f}}}{{{rect.width:.5f}}}{{{rect.height:.5f}}}{{{name}}}')
                        else:
                            if kind == 'fallback':
                                fallback_fonts.add(font)
                                fontcommand = r'\rmfamily'
                                if any(name in font.lower() for name in ('helvetica','arial','sans')):
                                    fontcommand = r'\sffamily'
                                if span['flags'] & 2:
                                    fontcommand += r'\itshape'
                                if span['flags'] & 16:
                                    fontcommand += r'\bfseries'
                            body.append(f'\\PDFunicode{{{x:.5f}}}{{{ph-y:.5f}}}{{{fontcommand}}}{{{size:.5f}}}{{{color}{Utils.escape_special_chars(text)}}}')
            for trace in traces[number - 1]:
                font = recovered.get(trace['font'])
                if not font or trace['type'] == 3:
                    continue
                color = trace['color']
                if isinstance(color, (int, float)):
                    color = (color, color, color)
                if len(color) != 3:
                    color = (0, 0, 0)
                style = f'\\color[rgb]{{{color[0]:.5f},{color[1]:.5f},{color[2]:.5f}}}'
                for (x, y), content in recovered_words(trace, font):
                    body.append(f'\\PDFunicode{{{x:.5f}}}{{{ph-y:.5f}}}{{{font["command"]}}}{{{trace["size"]:.5f}}}{{{style}{content}}}')
            body.append('\\end{picture}')
            if number != len(doc):
                body.append('\\newpage')
        for font in sorted(fallback_fonts):
            warnings.append(f'Font {font} was substituted; visual comparison may show differences.')
        if not char_count:
            warnings.append('This PDF has no editable text layer; its scanned images are preserved in layout mode. Use editable-text mode for OCR.')
        source = preamble + '\n'.join(body) + '\n\\end{document}\n'
        buffer = BytesIO()
        with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('main.tex', source)
            archive.writestr('README.txt', 'Compile main.tex with XeLaTeX. Text coordinates are preserved; edit the PDFtext/PDFunicode content. Keep assets/ beside main.tex.\n')
            for name, content in assets.items():
                archive.writestr(name, content)
        return {'tex': source, 'zip': base64.b64encode(buffer.getvalue()).decode(),
                'pages': len(doc), 'images': graphics, 'ocr_pages': 0,
                'characters': char_count, 'warnings': warnings, 'mode': 'layout'}
