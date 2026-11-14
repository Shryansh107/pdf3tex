"""Infer editable document structure instead of replaying PDF coordinates.

Only extraction uses positions. Exported source contains ordinary paragraphs,
sections, lists, links and a handful of reusable layout commands.
"""
import base64
from collections import Counter
from dataclasses import dataclass, field, replace
from io import BytesIO
import re
import textwrap
import unicodedata
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf
from fontTools import agl

from font_reconstruction import FontError
from pdf_fonts import FontRegistry, visible


@dataclass
class Run:
    text: str
    x: float
    end: float
    y: float
    size: float
    bold: bool = False
    italic: bool = False
    smallcaps: bool = False
    url: str = ''
    underline: bool = False

    @property
    def style(self):
        return self.bold, self.italic, self.smallcaps, self.url, self.underline


@dataclass
class Line:
    runs: list = field(default_factory=list)
    section_rule: bool = False

    @property
    def text(self):
        return ''.join(r.text for r in self.runs).strip()

    @property
    def size(self):
        return max(r.size for r in self.runs)

    @property
    def y(self):
        return self.runs[0].y

    @property
    def x(self):
        return self.runs[0].x


SPECIAL = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
           '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
           '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
PUNCTUATION = {'\u2013': '--', '\u2014': '---', '\u2018': '`', '\u2019': "'",
               '\u201c': '``', '\u201d': "''", '\u2026': r'\ldots{}',
               '\u2022': r'\textbullet{}', '\u00a0': ' ', '\u00ad': '',
               '\u2212': '-', '\u00d7': r'\ensuremath{\times}',
               '\u2264': r'\ensuremath{\leq}', '\u2265': r'\ensuremath{\geq}'}


def escape(text, missing):
    out = []
    for char in unicodedata.normalize('NFC', text):
        if char in SPECIAL:
            out.append(SPECIAL[char])
        elif char in PUNCTUATION:
            out.append(PUNCTUATION[char])
        elif ord(char) < 128 or ('LATIN' in unicodedata.name(char, '') and ord(char) < 0x250):
            out.append(char)
        else:
            missing.add(f'U+{ord(char):04X}')
            out.append(r'\MissingGlyph{' + f'U+{ord(char):04X}' + '}')
    return ''.join(out)


def link_target(url):
    # hyperref decodes percent escapes; escape TeX syntax before writing URLs.
    url = url.strip().replace(' ', '%20').replace('\n', '%0A').replace('\r', '%0D')
    return ''.join({'%': r'\%', '#': r'\#', '&': r'\&', '_': r'\_',
                    '{': '%7B', '}': '%7D', '\\': '%5C'}.get(c, c) for c in url)


def render(runs, missing):
    """Coalesce adjacent words with the same formatting into readable commands."""
    groups = []
    for run in runs:
        if groups and groups[-1].style == run.style:
            groups[-1] = replace(groups[-1], text=groups[-1].text + run.text)
        else:
            groups.append(replace(run))
    values = []
    for run in groups:
        leading = ' ' if run.text.startswith(' ') else ''
        trailing = ' ' if run.text.endswith(' ') else ''
        value = escape(run.text.strip(), missing)
        if not value:
            values.append(' ')
            continue
        if run.smallcaps:
            value = r'\textsc{' + value + '}'
        if run.italic:
            value = r'\textit{' + value + '}'
        if run.bold:
            value = r'\textbf{' + value + '}'
        if run.underline:
            value = r'\underline{' + value + '}'
        if run.url:
            value = r'\href{' + link_target(run.url) + '}{' + value + '}'
        values.append(leading + value + trailing)
    return ''.join(values).strip()


def wrapped(value):
    # Newlines at existing word boundaries are ordinary spaces to TeX.
    return textwrap.fill(value, width=100, break_long_words=False, break_on_hyphens=False)


def horizontal_rules(page):
    """Read thin strokes and filled rectangles without rasterizing the page."""
    rules = []
    for path in page.get_drawings():
        if path.get('color') is not None and (path.get('stroke_opacity', 1) or 0) > 0:
            for item in path['items']:
                if item[0] == 'l':
                    a, b = item[1:]
                    if abs(a.y - b.y) < .3 and abs(a.x - b.x) >= 4 and 0 < path['width'] <= 2:
                        rules.append((min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2))
        if path.get('fill') is not None and (path.get('fill_opacity', 1) or 0) > 0:
            for item in path['items']:
                if item[0] == 're':
                    rect = item[1]
                    if 0 < rect.height <= 2 and rect.width >= 4:
                        rules.append((rect.x0, rect.x1, (rect.y0 + rect.y1) / 2))
    return rules


def extract_lines(page, traces, resources, warnings):
    links = [link for link in page.get_links() if link.get('uri')]
    rules = horizontal_rules(page)
    chars = []
    for trace in traces:
        if not visible(trace):
            continue
        resource = resources[trace['font_key']]
        name = resource.name.lower()
        # Icon fonts do not carry prose. Link annotations on their labels remain.
        if 'fontawesome' in name or 'dingbat' in name:
            warnings.add('Decorative icon glyphs are omitted; linked text is retained.')
            continue
        try:
            program = resource.program()
        except FontError:
            program = None
        flags = trace.get('flags', 0)
        continuations = 0
        for code, gid, origin, bbox in trace['chars']:
            if gid < 0 and continuations:
                continuations -= 1
                continue
            continuations = 0
            value = chr(code) if 0 <= code <= 0x10FFFF else '\ufffd'
            glyph_name = program.glyph_name(gid) if program else None
            glyph_text = agl.toUnicode(glyph_name) if glyph_name else ''
            # MuPDF can report replacement characters for TeX punctuation and
            # ligatures even though the embedded font retains their glyph names.
            if glyph_text and (value == '\ufffd' or unicodedata.category(value) in ('Co', 'Cc')
                               or any(tag in name for tag in ('+cm', '+lm', 'computer', 'latinmodern'))):
                value = glyph_text
                continuations = max(0, len(value) - 1)
            value = value.translate(str.maketrans({'\ufb00': 'ff', '\ufb01': 'fi', '\ufb02': 'fl',
                                                  '\ufb03': 'ffi', '\ufb04': 'ffl'}))
            if glyph_text:
                continuations = max(continuations, len(value) - 1)
            if not value or (value.isspace() and value != ' '):
                value = ' '
            x, y = origin
            uri = next((link['uri'] for link in links
                        if link['from'].contains(pymupdf.Point((bbox[0] + bbox[2]) / 2,
                                                              (bbox[1] + bbox[3]) / 2))), '')
            underlined = any(
                right - left < page.rect.width * .6 and left - .5 <= (x + bbox[2]) / 2 <= right + .5
                and .3 <= rule_y - y <= max(2.8, trace['size'] * .3)
                for left, right, rule_y in rules)
            chars.append(Run(value, x, bbox[2], y, trace['size'],
                             bool(flags & 16) or 'bold' in name or 'cmbx' in name,
                             bool(flags & 2), 'cmcsc' in name or 'smallcap' in name, uri, underlined))
    # PDF paint order often differs from reading order (especially bold runs).
    lines = []
    for char in sorted(chars, key=lambda c: (c.y, c.x)):
        candidates = [line for line in lines[-4:] if abs(line.y - char.y) < min(2, char.size * .18)]
        if candidates:
            min(candidates, key=lambda line: abs(line.y - char.y)).runs.append(char)
        else:
            lines.append(Line([char]))
    for line in lines:
        runs = sorted(line.runs, key=lambda r: r.x)
        output = []
        for run in runs:
            if (output and run.x - output[-1].end > run.size * .16
                    and run.text[0] not in ',.;:!?)]}' and output[-1].text[-1] not in '([{'):
                if not output[-1].text.endswith(' ') and not run.text.startswith(' '):
                    gap_url = run.url if output[-1].url == run.url else ''
                    output.append(replace(run, text=' ', x=output[-1].end, end=run.x, url=gap_url))
            if (output and not output[-1].text.isspace() and output[-1].style == run.style
                    and abs(output[-1].size - run.size) < .1):
                output[-1] = replace(output[-1], text=output[-1].text + run.text, end=run.end)
            else:
                output.append(run)
        line.runs = output
        line.section_rule = any(
            right - left >= page.rect.width * .6 and abs(left - line.x) <= 3
            and line.size * .2 <= rule_y - line.y <= line.size * .85
            for left, right, rule_y in rules)
    return sorted((line for line in lines if line.text), key=lambda line: line.y)


def columns(line):
    """Split a deliberate wide gutter, not normal inter-word space."""
    for index, run in enumerate(line.runs):
        if run.text == ' ' and run.end - run.x > max(24, line.size * 2.4):
            return line.runs[:index], line.runs[index + 1:]
    return line.runs, []


def without_bullet(line):
    runs = [replace(r) for r in line.runs]
    for index, run in enumerate(runs):
        stripped = run.text.lstrip()
        if not stripped:
            continue
        if stripped[0] in '\u2022\u00b7\u2013\u2014-' and (len(stripped) == 1 or stripped[1].isspace()):
            runs[index].text = stripped[1:].lstrip()
            while runs and not runs[0].text.strip():
                runs.pop(0)
            return runs, True
        break
    return runs, False


KNOWN_SECTIONS = {'experience', 'work experience', 'professional experience', 'projects',
                  'education', 'technical skills', 'skills', 'achievements', 'publications',
                  'certifications', 'summary', 'professional summary', 'interests'}


def document_body(pages, body_size, missing):
    all_lines = [line for lines in pages for line in lines]
    resume = sum(line.text.casefold() in KNOWN_SECTIONS for line in all_lines) >= 2
    body, in_list, paragraph, previous = [], False, [], None
    skills_section = False

    def flush():
        nonlocal paragraph
        if paragraph:
            body.append(wrapped(render(paragraph, missing)) + '\n')
            paragraph = []

    def close_list():
        nonlocal in_list
        flush()
        if in_list:
            body.append(r'\end{itemize}' + '\n')
            in_list = False

    def add(runs):
        if paragraph:
            # Preserve hyphens rather than guessing whether a compound was split.
            paragraph.append(replace(runs[0], text=' ', url=''))
        paragraph.extend(runs)

    for page_index, lines in enumerate(pages):
        if page_index:
            close_list()
            body.append(r'\clearpage' + '\n')
        index = 0
        while index < len(lines):
            line = lines[index]
            section = line.text.casefold() in KNOWN_SECTIONS or (
                len(line.text) < 85 and line.size > body_size * 1.14
                and (any(r.bold or r.smallcaps for r in line.runs)))
            # Large first line is a document title/name, not a section heading.
            if page_index == 0 and index == 0 and line.size > body_size * 1.5:
                close_list()
                body.extend([r'\begin{center}', r'{\Huge ' + render(line.runs, missing) + r'} \\'])
                index += 1
                while index < min(len(lines), 4) and lines[index].text.casefold() not in KNOWN_SECTIONS:
                    following = lines[index]
                    if (following.y - lines[index - 1].y > body_size * 2.1
                            or len(following.text) > 180):
                        break
                    body.append(wrapped(render(following.runs, missing)) + r' \\')
                    index += 1
                body.extend([r'\end{center}', ''])
                previous = None
                continue
            if section:
                close_list()
                body.extend([r'\section*{' + escape(line.text, missing) + '}', ''])
                if line.section_rule:
                    body.extend([r'\sectionrule', ''])
                previous = None
                skills_section = 'skills' in line.text.casefold()
                index += 1
                continue
            if skills_section and re.match(r'^[^:]{1,28}:', line.text):
                close_list()
                body.append(r'\begin{tabularx}{\linewidth}{@{}lX@{}}')
                while index < len(lines):
                    match = re.match(r'^([^:]{1,28}:)\s*(.*)$', lines[index].text)
                    if not match:
                        break
                    label, value = match.groups()
                    index += 1
                    while (index < len(lines) and not re.match(r'^[^:]{1,28}:', lines[index].text)
                           and lines[index].text.casefold() not in KNOWN_SECTIONS
                           and lines[index].y - lines[index - 1].y < body_size * 1.65):
                        value += ' ' + lines[index].text
                        index += 1
                    body.append(r'  \textbf{' + escape(label, missing) + '} & '
                                + escape(value, missing) + r' \\')
                body.extend([r'\end{tabularx}', ''])
                previous = None
                continue
            left, right = columns(line)
            runs, bullet = without_bullet(line)
            if bullet:
                flush()
                if not in_list:
                    body.append(r'\begin{itemize}')
                    in_list = True
                paragraph = runs
                body.append(r'  \item ')
            elif (in_list and previous and line.y - previous.y < body_size * 1.65
                  and line.x >= previous.x - 2):
                add(runs)
            elif resume and left and right and any(r.bold for r in left):
                close_list()
                title = render([replace(r, bold=False) for r in left], missing)
                date = render([replace(r, bold=False) for r in right], missing)
                detail_left = detail_right = ''
                if index + 1 < len(lines):
                    following = lines[index + 1]
                    if (following.y - line.y < body_size * 1.8
                            and all(r.italic or not r.text.strip() for r in following.runs)):
                        a, b = columns(following)
                        detail_left = render([replace(r, italic=False) for r in a], missing)
                        detail_right = render([replace(r, italic=False) for r in b], missing)
                        index += 1
                body.append('\\resumeSubheading\n'
                            f'  {{{title}}}{{{date}}}\n'
                            f'  {{{detail_left}}}{{{detail_right}}}\n')
            elif right:
                close_list()
                body.append(r'\entryline{' + render(left, missing) + '}{' + render(right, missing) + '}\n')
            elif previous and (line.y - previous.y < body_size * 1.65
                               and abs(line.x - previous.x) < body_size * 1.4):
                add(runs)
            else:
                close_list()
                add(runs)
            previous = line
            index += 1
        close_list()
    # Join each item prefix to its first prose line for familiar source syntax.
    return '\n'.join(body).replace('  \\item \n', '  \\item '), resume


def convert_readable(data, filename):
    warnings, missing = set(), set()
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        registry = FontRegistry(doc)
        pages = [extract_lines(page, traces, registry.resources, warnings)
                 for page, traces in zip(doc, registry.pages)]
        if any(not lines for lines in pages):
            raise ValueError('Readable LaTeX needs visible text on every page. Scanned pages can be retained as images in Preserve original layout mode.')
        counts = Counter(round(run.size, 1) for lines in pages for line in lines
                         for run in line.runs for char in run.text if char.isalpha())
        body_size = counts.most_common(1)[0][0] if counts else 10
        body, resume = document_body(pages, body_size, missing)
        # Infer broad margins once; individual words/lines have no coordinates.
        first = doc[0]
        xs = [line.x for lines in pages for line in lines]
        ends = [run.end for lines in pages for line in lines for run in line.runs]
        margin = max(18, min(72, min(xs)))
        right = max(18, min(72, first.rect.width - max(ends)))
        top = max(18, min(72, min(line.y - line.size for line in pages[0])))
        bottom = max(18, min(72, first.rect.height - pages[0][-1].y - body_size))
        font_size = min((10, 11, 12), key=lambda n: abs(n - body_size * 72.27 / 72))
        source = ('% !TeX program = pdflatex\n'
                  '% Readable reconstruction inferred from the PDF.\n'
                  '% Edit the sections, paragraphs and list items normally.\n'
                  '% Layout and document structure are inferred; review before use.\n'
                  f'\\documentclass[{font_size}pt]{{article}}\n'
                  '\\usepackage[T1]{fontenc}\n\\usepackage[utf8]{inputenc}\n\\usepackage{lmodern}\n'
                  '\\input{glyphtounicode}\n\\pdfgentounicode=1\n'
                  '\\usepackage{geometry}\n\\usepackage{tabularx}\n'
                  '\\usepackage{amsmath,amssymb,textcomp}\n'
                  '\\usepackage[hidelinks]{hyperref}\n'
                  f'\\geometry{{paperwidth={first.rect.width:.2f}bp,paperheight={first.rect.height:.2f}bp,\n'
                  f'  left={margin:.2f}bp,right={right:.2f}bp,top={top:.2f}bp,bottom={bottom:.2f}bp}}\n'
                  '\\pagestyle{empty}\n\\setlength{\\parindent}{0pt}\n'
                  '\\setlength{\\parskip}{0pt}\n\\setlength{\\tabcolsep}{0pt}\n'
                  '\\renewenvironment{itemize}{%\n'
                  '  \\begin{list}{\\textbullet}{%\n'
                  '    \\setlength{\\leftmargin}{2em}\\setlength{\\itemsep}{2pt}%\n'
                  '    \\setlength{\\parsep}{0pt}\\setlength{\\topsep}{3pt}}%\n'
                  '}{\\end{list}}\n'
                  '\\newcommand{\\MissingGlyph}[1]{\\texttt{[#1]}}\n'
                  '\\newcommand{\\entryline}[2]{%\n'
                  '  \\noindent\\begin{tabularx}{\\linewidth}{@{}Xr@{}}#1 & #2\\end{tabularx}\\par\n}\n'
                  '\\newcommand{\\resumeSubheading}[4]{%\n'
                  '  \\entryline{\\textbf{#1}}{\\textbf{#2}}%\n'
                  '  \\entryline{\\textit{#3}}{\\textit{#4}}%\n}\n')
        if resume:
            source += ('\\makeatletter\n'
                       '\\renewcommand{\\section}{\\@startsection{section}{1}{0pt}\n'
                       '  {8pt}{4pt}{\\large\\bfseries\\scshape}}\n'
                       '\\makeatother\n')
        if any(line.section_rule for lines in pages for line in lines):
            source += ('\\newcommand{\\sectionrule}{%\n'
                       '  \\par\\nobreak\\vspace{-2pt}%\n'
                       '  \\hrule height 0.4pt\\relax\n'
                       '  \\nobreak\\vspace{3pt}%\n}\n')
        source += '\n\\begin{document}\n\n' + body + '\n\\end{document}\n'
        warnings.add('Structure and line wrapping are inferred. Review headings, lists, tables and equations; visual layout can change as text reflows.')
        if missing:
            warnings.add('Unsupported characters have visible placeholders: ' + ', '.join(sorted(missing)) + '.')
        if any(page.get_images() for page in doc):
            warnings.add('Readable mode currently exports text and links; embedded images are omitted. Use layout mode to retain illustrations.')
        bundle = BytesIO()
        with ZipFile(bundle, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('main.tex', source)
        return {'tex': source, 'zip': base64.b64encode(bundle.getvalue()).decode(),
                'mode': 'readable', 'engine': 'pdflatex', 'fidelity_target': 90,
                'pages': len(doc), 'images': 0, 'ocr_pages': 0,
                'characters': sum(len(line.text) for lines in pages for line in lines),
                'warnings': sorted(warnings)}
