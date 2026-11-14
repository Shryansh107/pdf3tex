"""Named LaTeX icons with embedded-outline fallbacks for unknown icon fonts."""
from functools import lru_cache
import json
from pathlib import Path
import re

from fontTools import agl

from font_reconstruction import FontError
from portable_converter import OutlinePen, letters, number


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name('icon_fonts.json').read_text(encoding='utf-8'))['icons']


def icon_font(name):
    return any(tag in name.lower() for tag in ('fontawesome', 'dingbat', 'icons'))


class IconExporter:
    def __init__(self, warnings):
        self.warnings = warnings
        self.definitions = {}
        self.names = set()
        self.fontawesome = False
        self.vectors = False

    def command(self, resource, program, gid, code, size, rise):
        # Ignore subpixel baseline noise from PDF arithmetic when sharing macros.
        key = (resource.identity, gid, round(size, 2), round(rise * 20) / 20)
        if key in self.definitions:
            return '\\' + self.definitions[key][0]
        glyph_name = program.glyph_name(gid) if program else None
        resolved = glyph_name
        known = None
        if any(family in resource.name.lower() for family in ('fontawesome5free', 'fontawesome5brands')):
            icons = catalog()
            if resolved not in icons:
                unicode_name = agl.toUnicode(glyph_name) if glyph_name else ''
                codepoint = ord(unicode_name) if len(unicode_name) == 1 else code
                resolved = next((name for name, value in icons.items() if value['unicode'] == codepoint), None)
            if resolved in icons:
                known = icons[resolved]
        if known:
            self.fontawesome = True
            if 'regular' in resource.name.lower() and known['family'] != 'brands':
                graphic = r'\faIcon[regular]{' + resolved + '}'
            else:
                graphic = known['command']
            graphic = r'{\fontsize{' + number(round(size, 2)) + 'bp}{' + number(round(size, 2)) + r'bp}\selectfont ' + graphic + '}'
        elif program and glyph_name and glyph_name != '.notdef':
            try:
                pen = OutlinePen(program.glyphs, program.units)
                program.glyphs[glyph_name].draw(pen)
                width = number(program.width(gid) * size)
                scale = number(size)
                content = f'q {scale} 0 0 {scale} 0 0 cm ' + ' '.join(pen.commands) + ' f Q'
                graphic = r'\IconVector{' + width + '}{' + content + '}'
                self.vectors = True
                self.warnings.add(f'Icon {glyph_name} in {resource.name} uses a named vector fallback.')
            except (FontError, KeyError, ValueError, IndexError):
                graphic = r'\fbox{\scriptsize icon}'
                self.warnings.add(f'An icon in {resource.name} could not be recovered; a visible placeholder was added.')
        else:
            graphic = r'\fbox{\scriptsize icon}'
            self.warnings.add(f'An icon in {resource.name} could not be recovered; a visible placeholder was added.')
        stem = resolved or glyph_name or 'unknown'
        name = 'Icon' + ''.join(part[0].upper() + part[1:] for part in re.findall('[A-Za-z]+', stem))[:48]
        stem_name, index = name, 0
        while name in self.names:
            name = stem_name + letters(index).upper()
            index += 1
        self.names.add(name)
        graphic = r'\raisebox{' + number(round(rise, 2)) + 'bp}{' + graphic + '}'
        self.definitions[key] = (name, '\\newcommand{\\' + name + '}{%\n  ' + graphic + '%\n}\n')
        return '\\' + name

    def preamble(self):
        source = ''
        if self.fontawesome:
            source += '\\usepackage{fontawesome5}\n'
        if self.vectors:
            source += (r'''\usepackage{pgf}
\makeatletter
% Vector details are defined once; use the named icon commands in the body.
\newcommand{\IconVector}[2]{%
  \begin{pgfpicture}%
  \pgfpathrectangle{\pgfpointorigin}{\pgfpoint{#1bp}{0bp}}%
  \pgfusepath{use as bounding box}%
  \pgfsysprotocol@flushcurrentprotocol\pgfsys@invoke{#2}%
  \end{pgfpicture}%
}
\makeatother
''')
        return source + ''.join(definition for _, definition in self.definitions.values())
