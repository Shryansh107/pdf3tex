"""Reconstruct visible PDF text with its actual fonts and glyph positions."""
import base64
from io import BytesIO
import math
from zipfile import ZipFile, ZIP_DEFLATED

import pymupdf
from pdf2tex import Utils
from PIL import Image, ImageChops

from font_reconstruction import FontError, recover_font
from pdf_fonts import FontRegistry, visible
from portable_converter import editable_words, letters


def recovered_words(trace, font):
    """Compatibility helper for Type 1 words with explicit PDF kerning."""
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


def trace_lines(trace, font):
    """Keep readable text runs while correcting advances along each baseline."""
    dx, dy = trace['dir']
    origin, parts, cursor = None, [], 0
    size = trace['size']
    for unicode, gid, point, _ in trace['chars']:
        whitespace = 0 <= unicode <= 0x10FFFF and chr(unicode).isspace()
        code = 32 if whitespace else font['codes'].get((unicode, gid))
        if code is None:
            continue
        if origin is not None:
            x, y = point[0] - origin[0], point[1] - origin[1]
            along, across = x * dx + y * dy, -x * dy + y * dx
            if abs(across) > .01 or along < cursor - size:
                yield origin, editable_words(''.join(parts))
                origin, parts, cursor = None, [], 0
        if origin is None:
            origin, along = point, 0
        gap = along - cursor
        if abs(gap) > .002:
            parts.append(f'\\kern{gap:.5f}bp{{}}')
        if code >= 0xF0000 or code in (127, 0x2028, 0x2029):
            parts.append('\\char"' + format(code, 'X') + '{}')
        else:
            parts.append(Utils.escape_special_chars(chr(code)))
        width = font['space'] if whitespace else font['advances'][gid] / 1000
        cursor = along + width * size
    if origin is not None:
        yield origin, editable_words(''.join(parts))


def rgb_color(value):
    if isinstance(value, (int, float)):
        value = (value,) * 3
    return value if len(value) == 3 else (0, 0, 0)


def image_asset(block, paint):
    image = Image.open(BytesIO(block['image']))
    if block.get('colorspace') == 0:
        # Stencil PNG samples are coverage, not grayscale page pixels.
        color = paint.get('color') or (0, 0, 0)
        alpha = image.convert('L')
        image = Image.new('RGBA', image.size, tuple(round(v * 255) for v in color))
        image.putalpha(alpha)
    else:
        image = image.convert('RGBA')
    if block.get('mask'):
        mask = Image.open(BytesIO(block['mask'])).convert('L')
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.Resampling.LANCZOS)
        image.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
    opacity = paint.get('opacity', 1)
    if opacity < 1:
        image.putalpha(image.getchannel('A').point(lambda v: round(v * opacity)))
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def convert_layout(data, filename):
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        if doc.needs_pass:
            raise ValueError('This PDF is password protected. Upload an unlocked copy.')
        if not 1 <= len(doc) <= 50:
            raise ValueError('Upload a PDF with 1–50 pages.')
        assets, body, definitions, warnings = {}, [], [], []
        fonts, char_count, graphics = {}, 0, 0
        registry = FontRegistry(doc)
        observed = {}
        for traces in registry.pages:
            for trace in traces:
                if visible(trace):
                    observed.setdefault(trace['font_key'], set()).update((c[0], c[1]) for c in trace['chars'])
        for identity, pairs in observed.items():
            resource = registry.resources[identity]
            try:
                payload, codes, advances, space, extension = recover_font(resource.program(), 'PDF' + identity[:20], pairs)
            except Exception as error:
                # Substituting a damaged font makes a successful compile look
                # trustworthy while silently changing its glyphs. Report it.
                raise FontError(f'Cannot reconstruct font {resource.name}: {error}') from error
            key = f'font_{len(fonts)}'
            command = '\\PDFfont' + letters(len(fonts))
            assets[f'assets/{key}.{extension}'] = payload
            definitions.append('\\newfontface' + command + '[Path=assets/]{' + key + '.' + extension + '}')
            fonts[identity] = {'command': command, 'codes': codes, 'advances': advances, 'space': space}
        w, h = doc[0].rect.width, doc[0].rect.height
        preamble = (f'% !TeX program = xelatex\n% Editable text placed at original PDF coordinates.\n'
                    '\\documentclass{article}\n\\usepackage{fontspec,graphicx,color}\n'
                    '\\setmainfont{lmroman10-regular.otf}[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf,BoldItalicFont=lmroman10-bolditalic.otf]\n'
                    f'\\usepackage[paperwidth={w:.5f}bp,paperheight={h:.5f}bp,margin=0bp]{{geometry}}\n'
                    '\\pagestyle{empty}\n\\setlength{\\parindent}{0pt}\n\\setlength{\\topskip}{0pt}\n'
                    '\\setlength{\\unitlength}{1bp}\n'
                    '\\newcommand{\\PageSize}[2]{\\setlength{\\paperwidth}{#1bp}\\setlength{\\paperheight}{#2bp}'
                    '\\special{papersize=#1bp,#2bp}\\setlength{\\textwidth}{\\paperwidth}\\setlength{\\textheight}{\\paperheight}}\n'
                    '\\newcommand{\\PDFimage}[5]{\\put(#1bp,#2bp){\\includegraphics[width=#3bp,height=#4bp]{#5}}}\n'
                    '\\newcommand{\\PDFunicode}[5]{\\put(#1bp,#2bp){\\makebox[0pt][l]{\\begingroup'
                    '#3\\fontsize{#4bp}{#4bp}\\selectfont #5\\endgroup}}}\n'
                    '% Edit the word in the first argument; the second stores spacing.\n'
                    '\\ExplSyntaxOn\n\\NewDocumentCommand{\\Spaced}{mm}{'
                    '\\seq_set_split:Nnn \\l_tmpa_seq {,} {#2}'
                    '\\tl_map_inline:nn {#1}{\\seq_pop_left:NN \\l_tmpa_seq \\l_tmpa_tl'
                    '\\quark_if_no_value:NTF \\l_tmpa_tl {\\kern0bp}{\\kern\\l_tmpa_tl bp}##1}}\n'
                    '\\ExplSyntaxOff\n' + '\n'.join(definitions) + '\n\\begin{document}\n')
        for number, page in enumerate(doc, 1):
            pw, ph = page.rect.width, page.rect.height
            body.append(f'% Page {number}\n\\PageSize{{{pw:.5f}}}{{{ph:.5f}}}\n\\noindent\\begin{{picture}}({pw:.5f}bp,{ph:.5f}bp)')
            elements = []
            def add(seqno, content):
                elements.append((seqno, len(elements), content))
            for path in page.get_drawings():
                for item in path['items']:
                    if item[0] == 're' and path['type'] == 'f':
                        rect = item[1]
                        color = rgb_color(path.get('fill') or (0, 0, 0))
                        add(path['seqno'], f'\\put({rect.x0:.5f}bp,{ph-rect.y1:.5f}bp)'
                                    f'{{\\color[rgb]{{{color[0]:.5f},{color[1]:.5f},{color[2]:.5f}}}'
                                    f'\\rule{{{rect.width:.5f}bp}}{{{rect.height:.5f}bp}}}}')
                    if item[0] == 'l' and abs(item[1].y - item[2].y) < .01:
                        x1, x2 = sorted([item[1].x, item[2].x])
                        thickness = max(path['width'] or .4, .1)
                        color = rgb_color(path.get('color') or (0, 0, 0))
                        add(path['seqno'], f'\\put({x1:.5f}bp,{ph-item[1].y-thickness/2:.5f}bp)'
                                    f'{{\\color[rgb]{{{color[0]:.5f},{color[1]:.5f},{color[2]:.5f}}}'
                                    f'\\rule{{{x2-x1:.5f}bp}}{{{thickness:.5f}bp}}}}')
            paints = list(registry.images[number - 1])
            for block in page.get_text('dict', sort=False)['blocks']:
                if block['type'] != 1:
                    continue
                graphics += 1
                name = f'assets/page_{number}_image_{graphics}.png'
                match = next((i for i, event in enumerate(paints) if max(abs(a-b) for a,b in zip(event['bbox'], block['bbox'])) < .05), None)
                paint = paints.pop(match) if match is not None else {'seqno': 0}
                assets[name] = image_asset(block, paint)
                x0, y0, x1, y1 = block['bbox']
                add(paint['seqno'], f'\\PDFimage{{{x0:.5f}}}{{{ph-y1:.5f}}}{{{x1-x0:.5f}}}{{{y1-y0:.5f}}}{{{name}}}')
            for trace in registry.pages[number - 1]:
                if not visible(trace):
                    continue
                font = fonts[trace['font_key']]
                color = rgb_color(trace['color'])
                style = f'\\color[rgb]{{{color[0]:.5f},{color[1]:.5f},{color[2]:.5f}}}'
                angle = -math.degrees(math.atan2(trace['dir'][1], trace['dir'][0]))
                char_count += sum(not chr(c[0]).isspace() for c in trace['chars'] if 0 <= c[0] <= 0x10FFFF)
                for (x, y), content in trace_lines(trace, font):
                    if abs(angle) > .001:
                        content = f'\\rotatebox[origin=Bl]{{{angle:.5f}}}{{{content}}}'
                    add(trace['seqno'], f'\\PDFunicode{{{x:.5f}}}{{{ph-y:.5f}}}{{{font["command"]}}}{{{trace["size"]:.5f}}}{{{style}{content}}}')
            body.extend(content for _, _, content in sorted(elements))
            body.append('\\end{picture}')
            if number != len(doc):
                body.append('\\newpage')
        if not char_count:
            warnings.append('This PDF has no visible editable text layer; its scanned images are preserved in layout mode. Use editable-text mode for OCR.')
        source = preamble + '\n'.join(body) + '\n\\end{document}\n'
        buffer = BytesIO()
        with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('main.tex', source)
            archive.writestr('README.txt', 'Compile main.tex with XeLaTeX. Edit PDFunicode text or the first argument of Spaced. Keep assets/ beside main.tex. Fonts retain the PDF glyphs; subsets may lack letters needed for new text.\n')
            for name, content in assets.items():
                archive.writestr(name, content)
        return {'tex': source, 'zip': base64.b64encode(buffer.getvalue()).decode(),
                'pages': len(doc), 'images': graphics, 'ocr_pages': 0,
                'characters': char_count, 'warnings': warnings, 'mode': 'layout'}
