"""Single-file, editable PDF reconstruction using standard TeX fonts and PGF.

No original pages, external images, font files, or binary payloads are embedded.
Small nonstandard glyphs and raster illustrations become inline vector paths.
"""
import base64
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

import cv2
import numpy as np
from PIL import Image
import pymupdf
from fontTools import agl
from fontTools.pens.basePen import BasePen

from font_reconstruction import load_type1


@lru_cache(maxsize=1)
def standard_fonts():
    return json.loads(Path(__file__).with_name('portable_fonts.json').read_text())


def number(value):
    return f'{value:.4f}'.rstrip('0').rstrip('.') or '0'


def letters(index):
    result = ''
    while True:
        result = chr(97 + index % 26) + result
        index = index // 26 - 1
        if index < 0:
            return result


class OutlinePen(BasePen):
    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.commands = []

    def point(self, point):
        return ' '.join(number(c / 1000) for c in point)

    def _moveTo(self, p):
        self.commands.append(self.point(p) + ' m')

    def _lineTo(self, p):
        self.commands.append(self.point(p) + ' l')

    def _curveToOne(self, p1, p2, p3):
        self.commands.append(' '.join(self.point(p) for p in (p1, p2, p3)) + ' c')

    def _closePath(self):
        self.commands.append('h')

    def _endPath(self):
        pass


def vector(content):
    # PGF dispatches the PDF graphics operators through each engine's driver.
    # Unlike \\pdfliteral, this works in pdfLaTeX, XeLaTeX and LuaLaTeX.
    return r'\InlineGraphic{' + content + '}'


def standard_face(base):
    aliases = {'NimbusRomNo9L-Regu':'ptmr8r', 'NimbusRomNo9L-Medi':'ptmb8r',
               'NimbusRomNo9L-ReguItal':'ptmri8r', 'SFTT1000':'ec-lmtt10',
               'Times-Roman':'ptmr8r', 'Times-Bold':'ptmb8r', 'Times-Italic':'ptmri8r',
               'Times-BoldItalic':'ptmbi8r', 'Helvetica':'phvr8r', 'Helvetica-Bold':'phvb8r',
               'Helvetica-Oblique':'phvro8r', 'Helvetica-BoldOblique':'phvbo8r',
               'Courier':'pcrr8r', 'Courier-Bold':'pcrb8r', 'Courier-Oblique':'pcrro8r',
               'Courier-BoldOblique':'pcrbo8r', 'ArialMT':'phvr8r', 'Arial-BoldMT':'phvb8r',
               'Arial-ItalicMT':'phvro8r', 'Arial-BoldItalicMT':'phvbo8r',
               'TimesNewRomanPSMT':'ptmr8r', 'TimesNewRomanPS-BoldMT':'ptmb8r',
               'TimesNewRomanPS-ItalicMT':'ptmri8r', 'TimesNewRomanPS-BoldItalicMT':'ptmbi8r'}
    return aliases.get(base,base.lower())


def editable_words(content):
    """Keep words intact in source; store per-letter spacing beside the word.

    Extra letters after an edit receive zero correction. Fixed line positioning
    still applies, but users need not edit around internal kern commands.
    """
    pattern = r'[A-Za-z](?:(?:\\kern[-\d.]+bp\{\})?[A-Za-z])+'
    def replace(match):
        value = match.group()
        if '\\kern' not in value:
            return value
        chars = re.findall(r'(?:\\kern([-\d.]+)bp\{\})?([A-Za-z])',value)
        return '\\Spaced{' + ''.join(c for _,c in chars) + '}{' + ','.join(k or '0' for k,_ in chars) + '}'
    return re.sub(pattern,replace,content)


def illustration(block):
    """Quantized contours of an illustration, never of a rendered PDF page."""
    image = Image.open(BytesIO(block['image'])).convert('RGBA')
    if block.get('mask'):
        image.putalpha(Image.open(BytesIO(block['mask'])).convert('L'))
    white = Image.new('RGBA', image.size, 'white')
    white.alpha_composite(image)
    image = white.convert('RGB')
    x0, y0, x1, y1 = block['bbox']
    width, height = x1 - x0, y1 - y0
    scale = min(3, 1400 / max(width, height))
    image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS)
    quantized = image.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    pixels = np.array(quantized)
    palette = np.array(quantized.getpalette()).reshape(-1, 3)
    commands = ['q']
    # White backing preserves opaque white pixels and flattened transparency.
    commands.append(f'1 1 1 rg 0 0 {number(width)} {number(height)} re f')
    sx, sy = width / (2 * image.width), height / (2 * image.height)
    commands.append(f'{number(sx)} 0 0 {number(-sy)} {number(.5*sx)} {number(height-.5*sy)} cm')
    for index in np.unique(pixels):
        rgb = palette[index]
        if min(rgb) >= 253:
            continue
        mask = cv2.resize((pixels == index).astype(np.uint8), None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        commands.append(' '.join(number(int(c) / 255) for c in rgb) + ' rg')
        paths = []
        for contour in contours:
            contour = cv2.approxPolyDP(contour, .65, True).reshape(-1, 2)
            if len(contour) < 3:
                continue
            for j, (x, y) in enumerate(contour):
                paths.append(f'{x} {y} ' + ('m' if j == 0 else 'l'))
            paths.append('h')
        # Even-odd filling preserves holes, independent of contour orientation.
        if paths:
            commands.append('\n'.join(paths) + ' f*')
    commands.append('Q')
    return '\n'.join(commands)


def drawing(path, height):
    commands = ['q']
    if path.get('fill') is not None:
        commands.append(' '.join(number(v) for v in path['fill']) + ' rg')
    if path.get('color') is not None:
        commands.append(' '.join(number(v) for v in path['color']) + ' RG')
    commands.append(number(path.get('width') or .1) + ' w')
    commands.append(str(int(path.get('lineJoin') or 0)) + ' j')
    caps = path.get('lineCap') or (0,)
    commands.append(str(int(max(caps))) + ' J')
    if path.get('dashes') and re.fullmatch(r'[\d.\s\[\]-]+', path['dashes']):
        commands.append(path['dashes'] + ' d')
    def point(p):
        return f'{number(p.x)} {number(height-p.y)}'
    last = None
    for item in path['items']:
        kind = item[0]
        if kind in ('l', 'c'):
            if last != item[1]:
                commands.append(point(item[1]) + ' m')
            if kind == 'l':
                commands.append(point(item[2]) + ' l')
            else:
                commands.append(' '.join(point(p) for p in item[2:]) + ' c')
            last = item[-1]
        elif kind == 're':
            r = item[1]
            commands.append(f'{number(r.x0)} {number(height-r.y1)} {number(r.width)} {number(r.height)} re')
            last = None
        elif kind == 'qu':
            q = item[1]
            commands.extend([point(q.ul)+' m', point(q.ur)+' l', point(q.lr)+' l', point(q.ll)+' l', 'h'])
            last = None
    if path.get('closePath'):
        commands.append('h')
    commands.append({'f': 'f', 's': 'S', 'fs': 'B'}.get(path['type'], 'n') + ('*' if path.get('even_odd') and 'f' in path['type'] else ''))
    commands.append('Q')
    return '\n'.join(commands)


def convert_portable(data, filename):
    fonts = standard_fonts()
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        traces = [p.get_texttrace() for p in doc]
        # OCR overlays on scanned page images are not visible editable content.
        for i, page_traces in enumerate(traces):
            if not any(t['type'] != 3 and t['chars'] for t in page_traces):
                raise ValueError(f'Page {i+1} has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.')
        definitions, warnings, body = [], [], []
        faces, glyph_definitions = {}, {}
        for page in doc:
            for xref, ext, kind, name, *_ in page.get_fonts(full=True):
                base = re.sub(r'^[A-Z]{6}\+', '', name)
                if base in faces:
                    continue
                target = standard_face(base)
                face = {'target':target if target in fonts else 'cmr10', 'order':[], 'glyphs':None, 'encoding':{}}
                if ext in ('pfa', 'pfb'):
                    try:
                        original, face['order'], face['glyphs'] = load_type1(doc.extract_font(xref)[3])
                        face['encoding'] = {g:c for c,g in enumerate(original.font['Encoding']) if g != '.notdef'}
                    except (ValueError, RuntimeError, KeyError, AssertionError, EOFError):
                        pass
                if target not in fonts and 'Awesome' not in base:
                    warnings.append(f'Font {base} uses a standard Computer Modern substitute; check the compiled result.')
                faces[base] = face

        def glyph(trace, char):
            unicode, gid, origin, _ = char
            face = faces.get(trace['font'], {'target':'cmr10','order':[], 'glyphs':None, 'encoding':{}})
            target = face['target']
            meta = fonts[target]
            name = face['order'][gid] if 0 <= gid < len(face['order']) else agl.UV2AGL.get(unicode)
            encoding = meta['encoding'] or face['encoding']
            code = encoding.get(name) if name else (unicode if 32 <= unicode < 127 else None)
            if name == 'space' or chr(unicode).isspace():
                return target, ' ', meta['space'] * trace['size'], 32
            if code is not None and str(code) in meta['widths']:
                # Literal words remain readable/editable. Non-ASCII font slots
                # use TeX character numbers, independent of Unicode engines.
                text = chr(code) if 33 <= code < 127 and chr(code) not in '\\&%$#_{}~^' else f'\\char{code}{{}}'
                return target, text, meta['widths'][str(code)] * trace['size'], code
            if face['glyphs'] is not None and name in face['glyphs']:
                key = (trace['font'], gid)
                if key not in glyph_definitions:
                    command = 'symbol' + letters(len(glyph_definitions))
                    pen = OutlinePen(face['glyphs'])
                    face['glyphs'][name].draw(pen)
                    definitions.append('\\newcommand{\\' + command + '}[1]{' + vector('q #1 0 0 #1 0 0 cm ' + ' '.join(pen.commands) + ' f Q') + '}')
                    glyph_definitions[key] = command
                width = face['glyphs'][name].width / 1000 * trace['size']
                return target, '\\' + glyph_definitions[key] + '{' + number(trace['size']) + '}\\kern' + number(width) + 'bp{}', width, None
            raise ValueError(f'Cannot export glyph U+{unicode:04X} in {trace["font"]} without an external font. Use Preserve original layout for this PDF.')

        images, characters = 0, 0
        for page, page_traces in zip(doc, traces):
            w, h = page.rect.width, page.rect.height
            body.append(f'% Page {page.number+1}\n\\PageSize{{{number(w)}}}{{{number(h)}}}\n\\noindent\\begin{{picture}}({number(w)},{number(h)})')
            # Keep graphical objects separate from editable body text.
            for path in page.get_drawings():
                if path['type'] in ('f','s','fs'):
                    body.append('\\put(0,0){' + vector(drawing(path, h)) + '}')
            for block in page.get_text('dict')['blocks']:
                if block['type'] != 1:
                    continue
                x0,y0,x1,y1 = block['bbox']
                if (x1-x0)*(y1-y0) > .7*w*h:
                    raise ValueError('Portable mode does not embed full-page scan images. Use Reflow / OCR for a scanned PDF.')
                images += 1
                command = 'figure' + letters(images-1)
                definitions.append('% Inline vector illustration ' + str(images) + '\n\\newcommand{\\' + command + '}{' + vector(illustration(block)) + '}')
                body.append(f'\\put({number(x0)},{number(h-y1)}){{\\{command}}}')
            lines = {}
            for trace in page_traces:
                if trace['type'] == 3:
                    continue
                if abs(trace['dir'][0]-1) > .001 or abs(trace['dir'][1]) > .001:
                    raise ValueError('Portable mode currently supports horizontal text. Use Preserve original layout for rotated text.')
                for char in trace['chars']:
                    lines.setdefault(round(char[2][1], 2), []).append((trace,char))
            for baseline, items in sorted(lines.items()):
                items.sort(key=lambda item:item[1][2][0])
                start = items[0][1][2][0]
                cursor, last_code, last_font = start, None, None
                parts, run, style = [], [], None
                def flush():
                    if run:
                        parts.append('\\TextStyle{' + style[0] + '}{' + number(style[1]) + '}{' + style[2] + '}{' + editable_words(''.join(run)) + '}')
                        run.clear()
                for trace,char in items:
                    target, content, width, code = glyph(trace,char)
                    rgb = trace['color']
                    if isinstance(rgb, (int,float)):
                        rgb = (rgb,)*3
                    if len(rgb) != 3:
                        rgb = (0,0,0)
                    current_style = (target, trace['size'], ','.join(number(v) for v in rgb))
                    if current_style != style:
                        flush()
                        style = current_style
                    gap = char[2][0] - cursor
                    pair = f'{last_code},{code}'
                    if abs(gap) > .002 or (last_font == target and pair in fonts[target]['pairs']):
                        run.append('\\kern' + number(gap) + 'bp{}')
                    run.append(r'\ ' if content == ' ' else content)
                    cursor = char[2][0] + width
                    last_code, last_font = code, target
                    characters += 1
                flush()
                body.append(f'\\PlaceText{{{number(start)}}}{{{number(h-baseline)}}}{{' + ''.join(parts) + '}')
            body.append('\\end{picture}' + ('\n\\newpage' if page.number+1 < len(doc) else ''))
        w,h = doc[0].rect.width,doc[0].rect.height
        preamble = r'''% !TeX program = pdflatex
% Single-file reconstruction: copy ALL this source into main.tex.
% Works with pdfLaTeX, XeLaTeX and LuaLaTeX using standard TeX Live/MiKTeX packages.
% Text is editable, with fixed line positions. Longer edits may overlap.
% Symbols and illustrations are inline vectors; no external assets are needed.
\documentclass{article}
\usepackage{iftex,pgf,xcolor}
\usepackage[paperwidth=WIDTHbp,paperheight=HEIGHTbp,margin=0bp]{geometry}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\topskip}{0pt}
\setlength{\unitlength}{1bp}
\newcommand{\PageSize}[2]{\setlength{\paperwidth}{#1bp}\setlength{\paperheight}{#2bp}%
  \ifPDFTeX\pdfpagewidth=\paperwidth\pdfpageheight=\paperheight\else
  \ifLuaTeX\pagewidth=\paperwidth\pageheight=\paperheight\else
  \special{papersize=#1bp,#2bp}\fi\fi
  \setlength{\textwidth}{\paperwidth}\setlength{\textheight}{\paperheight}}
\newcommand{\PlaceText}[3]{\put(#1,#2){\makebox[0pt][l]{#3}}}
\newcommand{\TextStyle}[4]{{\font\TextFace=#1 at #2bp\TextFace\color[rgb]{#3}#4}}
% Edit the first argument of \Spaced normally; the second stores original spacing.
\ExplSyntaxOn
\NewDocumentCommand{\Spaced}{mm}{
  \seq_set_split:Nnn \l_tmpa_seq {,} {#2}
  \tl_map_inline:nn {#1}{
    \seq_pop_left:NN \l_tmpa_seq \l_tmpa_tl
    \quark_if_no_value:NTF \l_tmpa_tl {\kern0bp}{\kern\l_tmpa_tl bp}
    ##1
  }
}
\ExplSyntaxOff
\makeatletter
\newcommand{\InlineGraphic}[1]{\begin{pgfpicture}\pgfpathmoveto{\pgfpointorigin}\pgfusepath{use as bounding box}\pgfsysprotocol@flushcurrentprotocol\pgfsys@invoke{#1}\end{pgfpicture}}
\makeatother
'''.replace('WIDTH',number(w)).replace('HEIGHT',number(h))
        source = preamble + '\n'.join(definitions) + '\n\\begin{document}\n' + '\n'.join(body) + '\n\\end{document}\n'
        if len(source) > 2_000_000:
            raise ValueError('The inline illustrations exceed the 2 MB single-file source limit. Use Preserve original layout for this PDF.')
        bundle = BytesIO()
        with ZipFile(bundle,'w',ZIP_DEFLATED) as archive:
            archive.writestr('main.tex',source)
        warnings.append('Single-file output uses fixed text positions. Compile and compare before relying on the 90% visual target; it is not guaranteed for every PDF.')
        return {'tex':source,'zip':base64.b64encode(bundle.getvalue()).decode(),
                'pages':len(doc),'images':images,'ocr_pages':0,'characters':characters,
                'warnings':warnings,'mode':'portable','engine':'pdflatex','fidelity_target':90}
