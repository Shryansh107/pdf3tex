"""Recover an embedded Type 1 face as OpenType, retaining its actual glyphs."""
from io import BytesIO
from dataclasses import dataclass, field
import struct

from fontTools import agl
from fontTools.misc import eexec, psCharStrings
from fontTools.cffLib import CFFFontSet
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.basePen import NullPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.t1Lib import T1Font, T1Error, findEncryptedChunks
from fontTools.ttLib import TTFont, newTable
from matplotlib.ft2font import FT2Font


def load_type1(data):
    # PDF font streams commonly omit the PFA trailer. Restore the container,
    # without changing the encrypted font program or its character outlines.
    if data.startswith(b'\x80\x01'):
        chunks, offset = [], 0
        while offset + 2 <= len(data) and data[offset] == 128:
            kind = data[offset + 1]
            if kind == 3:
                break
            if kind not in (1, 2) or offset + 6 > len(data):
                raise ValueError('Malformed Type 1 PFB segment')
            length = struct.unpack('<I', data[offset + 2:offset + 6])[0]
            if offset + 6 + length > len(data):
                raise ValueError('Truncated Type 1 PFB segment')
            chunks.append(data[offset + 6:offset + 6 + length])
            offset += 6 + length
        data = b''.join(chunks)
    trailer = data.rfind(b'cleartomark')
    if trailer >= 0:
        data = data[:trailer + len(b'cleartomark')] + b'\n'
    try:
        chunks = findEncryptedChunks(data)
    except T1Error:
        chunks = findEncryptedChunks(data + b'\n' + b'0' * 512 + b'\ncleartomark\n')
    normalized = b''.join(chunk for _, chunk in chunks)
    pfb = b''.join(b'\x80' + bytes([2 if encrypted else 1]) + struct.pack('<I', len(chunk)) + chunk
                   for encrypted, chunk in chunks) + b'\x80\x03'
    face = FT2Font(BytesIO(pfb))
    order = [face.get_glyph_name(index) for index in range(face.num_glyphs)]
    font = T1Font.__new__(T1Font)
    font.data = normalized
    font.encoding = 'ascii'
    try:
        font.parse()
    except KeyError as error:
        if error.args != ('Subrs',):
            raise
        # Subrs is optional in Type 1; fontTools' parser assumes it exists.
        subrs = font.font['Private'].setdefault('Subrs', [])
        length = font.font['Private'].get('lenIV', 4)
        for name, charstring in font.font['CharStrings'].items():
            value = eexec.decrypt(charstring, 4330)[0][length:] if length >= 0 else charstring
            font.font['CharStrings'][name] = psCharStrings.T1CharString(value, subrs=subrs)
    expected = (.001, 0, 0, .001, 0, 0)
    if any(abs(actual - target) > 1e-8 for actual, target in zip(font.font['FontMatrix'], expected)):
        raise ValueError('Nonstandard Type 1 font matrix requires an explicit transform')
    glyphs = font.getGlyphSet()
    return font, order, glyphs


class FontError(ValueError):
    """An embedded font program cannot be reconstructed safely."""


@dataclass
class FontProgram:
    data: bytes
    order: list
    glyphs: object
    units: float
    encoding: dict = field(default_factory=dict)
    cmap: dict = field(default_factory=dict)
    sfnt: object = None
    cff: object = None
    cid_names: dict = field(default_factory=dict)
    widths: dict = field(default_factory=dict)

    def glyph_name(self, gid):
        if self.cid_names:
            return self.cid_names.get(gid)
        return self.order[gid] if 0 <= gid < len(self.order) else None

    def glyph_id(self, name):
        if self.cid_names:
            return 0 if name == '.notdef' else int(name[3:])
        return self.order.index(name)

    def width(self, gid):
        if gid not in self.widths:
            name = self.glyph_name(gid)
            if name is None:
                raise FontError(f'Glyph index {gid} is outside the embedded font.')
            glyph = self.glyphs[name]
            # Type 1/CFF widths are populated by executing their charstring.
            if not hasattr(glyph, 'width'):
                glyph.draw(NullPen())
            self.widths[gid] = glyph.width / self.units
        return self.widths[gid]


def load_font(data):
    """Read Type 1, raw CFF, TrueType or OpenType with real glyph indices."""
    try:
        if data[:4] in (b'\x00\x01\x00\x00', b'true', b'OTTO'):
            font = TTFont(BytesIO(data), recalcTimestamp=False)
            try:
                cmap = font.getBestCmap() or {}
            except Exception:
                # PDF subset cmaps can be truncated; trace pairs repair them.
                cmap = {}
                del font['cmap']
                table = newTable('cmap')
                table.tableVersion, table.tables = 0, []
                font['cmap'] = table
            return FontProgram(data, font.getGlyphOrder(), font.getGlyphSet(),
                               font['head'].unitsPerEm, cmap=cmap, sfnt=font,
                               cff=font['CFF '].cff if 'CFF ' in font else None)
        if data[:1] in (b'\x01', b'\x02'):
            cff = CFFFontSet()
            cff.decompile(BytesIO(data), None, isCFF2=False)
            top = cff[0]
            top.rawDict.setdefault('charset', 0)
            matrix = top.FontMatrix
            if matrix[0] <= 0 or abs(matrix[0] - matrix[3]) > 1e-8 or any(abs(matrix[i]) > 1e-8 for i in (1, 2, 4, 5)):
                raise FontError('Nonstandard CFF font matrix requires an explicit transform.')
            encoding = top.Encoding if isinstance(top.Encoding, list) else []
            order = list(top.charset)
            cid_names = {0 if g == '.notdef' else int(g[3:]): g for g in order} if hasattr(top, 'ROS') else {}
            return FontProgram(data, order, top.CharStrings, 1 / matrix[0],
                               encoding={g: i for i, g in enumerate(encoding) if g != '.notdef'}, cff=cff, cid_names=cid_names)
        font, order, glyphs = load_type1(data)
        return FontProgram(data, order, glyphs, 1000,
                           encoding={g: i for i, g in enumerate(font.font['Encoding']) if g != '.notdef'})
    except Exception as error:
        raise FontError(f'{type(error).__name__}: {error}') from error


def recover_font(program, name, observed):
    """Repair Unicode mappings while retaining glyph IDs, outlines and metrics.

    TrueType outlines and hinting stay in TrueType. PostScript outlines become
    an OpenType/CFF font. No shaping tables can move explicitly placed glyphs.
    """
    order = list(program.order)
    cmap, pairs = {}, {}
    private = 0xF0000
    for unicode, gid in sorted(observed):
        glyph = program.glyph_name(gid)
        if glyph is None or (0 <= unicode <= 0x10FFFF and chr(unicode).isspace()):
            continue
        code = unicode
        if not 32 <= code <= 0x10FFFF or 0xD800 <= code <= 0xDFFF or code == 0xFFFD or (code in cmap and cmap[code] != glyph):
            while private in cmap or any(u == private for u, _ in observed):
                private += 1
            code = private
            private += 1
        cmap[code] = glyph
        pairs[(unicode, gid)] = code
    # Keep unobserved characters available for ordinary source edits.
    for code, glyph in program.cmap.items():
        if 32 <= code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF:
            cmap.setdefault(code, glyph)
    for glyph in order:
        value = agl.toUnicode(glyph)
        if len(value) == 1 and ord(value) >= 32:
            cmap.setdefault(ord(value), glyph)
    space = cmap.get(32)
    if space not in program.glyphs:
        space = 'space' if 'space' in program.glyphs else 'pdfSpace'
        if space == 'pdfSpace' and program.cid_names:
            space = 'cid' + format(max(program.cid_names) + 1, '05d')
    cmap[32] = space
    space_width = program.width(program.glyph_id(space)) if space in order else 1 / 3
    advances = {gid: program.width(gid) * 1000 for _, gid in observed if program.glyph_name(gid) is not None}
    names = {'familyName': name, 'styleName': 'Regular', 'uniqueFontIdentifier': name,
             'fullName': name, 'psName': name}
    if program.sfnt is not None and 'glyf' in program.sfnt:
        font = TTFont(BytesIO(program.data), recalcTimestamp=False)
        font.sfntVersion = '\x00\x01\x00\x00'
        font.setGlyphOrder(order)
        if space not in order:
            order.append(space)
            font['glyf'][space] = TTGlyphPen(None).glyph()
            font['hmtx'].metrics[space] = (round(space_width * program.units), 0)
            font.setGlyphOrder(order)
        copyright = font['name'].getDebugName(0) if 'name' in font else None
        if copyright:
            names['copyright'] = copyright
        builder = FontBuilder(font=font)
        builder.setupCharacterMap(cmap)
        builder.setupNameTable(names)
        builder.setupPost()
        if 'OS/2' not in font:
            builder.setupOS2(sTypoAscender=font['hhea'].ascent, sTypoDescender=font['hhea'].descent,
                             usWinAscent=max(0, font['hhea'].ascent), usWinDescent=max(0, -font['hhea'].descent))
        for tag in ('GSUB', 'GPOS', 'kern', 'DSIG'):
            if tag in font:
                del font[tag]
        extension = 'ttf'
    elif program.cff is not None:
        # Keep the CFF hints, subroutines and CID font dictionaries. Redrawing
        # the outlines would change rasterization at normal text resolutions.
        source = program.sfnt.reader['CFF '] if program.sfnt is not None else program.data
        cff = CFFFontSet()
        cff.decompile(BytesIO(source), None, isCFF2=False)
        cff.fontNames = [name]
        top = cff[0]
        top.rawDict.setdefault('charset', 0)
        top.FullName = top.FamilyName = name
        metrics = {glyph: (round(program.width(program.glyph_id(glyph)) * program.units), 0) for glyph in order}
        if space not in order:
            order.append(space)
            empty = T2CharStringPen(round(space_width * program.units), None).getCharString()
            empty.private = top.Private if hasattr(top, 'Private') else top.FDArray[0].Private
            empty.globalSubrs = cff.GlobalSubrs
            if top.CharStrings.charStringsAreIndexed:
                index = top.CharStrings.charStringsIndex
                top.CharStrings.charStrings[space] = len(index)
                index.append(empty)
            else:
                top.CharStrings.charStrings[space] = empty
            top.charset = order
            if hasattr(top, 'ROS'):
                top.FDSelect.gidArray.append(0)
                top.CIDCount = max(program.cid_names) + 2
            metrics[space] = (round(space_width * program.units), 0)
        builder = FontBuilder(round(program.units), isTTF=False)
        builder.font.sfntVersion = 'OTTO'
        builder.setupGlyphOrder(order)
        builder.setupCharacterMap(cmap)
        table = newTable('CFF ')
        table.cff = cff
        builder.font['CFF '] = table
        builder.setupHorizontalMetrics(metrics)
        builder.setupHorizontalHeader(ascent=round(program.units), descent=-round(program.units * .4))
        builder.setupNameTable(names)
        builder.setupOS2(sTypoAscender=round(program.units), sTypoDescender=-round(program.units * .4), usWinAscent=round(program.units), usWinDescent=round(program.units))
        builder.setupPost()
        font, extension = builder.font, 'otf'
    else:
        charstrings, metrics = {}, {}
        for gid, glyph in enumerate(order):
            outline = program.glyphs[glyph]
            bounds = BoundsPen(program.glyphs)
            outline.draw(bounds)
            width = round(program.width(gid) * 1000)
            pen = T2CharStringPen(width, program.glyphs, roundTolerance=0)
            outline.draw(TransformPen(pen, (1000 / program.units, 0, 0, 1000 / program.units, 0, 0)))
            charstrings[glyph] = pen.getCharString()
            metrics[glyph] = (width, round(bounds.bounds[0] * 1000 / program.units) if bounds.bounds else 0)
            if gid in advances:
                advances[gid] = width
        if space not in charstrings:
            order.append(space)
            charstrings[space] = T2CharStringPen(round(space_width * 1000), None).getCharString()
            metrics[space] = (round(space_width * 1000), 0)
        builder = FontBuilder(1000, isTTF=False)
        builder.setupGlyphOrder(order)
        builder.setupCharacterMap(cmap)
        builder.setupCFF(name, {'FullName': name, 'FamilyName': name, 'Weight': 'Regular'}, charstrings, {})
        builder.setupHorizontalMetrics(metrics)
        builder.setupHorizontalHeader(ascent=1000, descent=-400)
        builder.setupNameTable(names)
        builder.setupOS2(sTypoAscender=1000, sTypoDescender=-400, usWinAscent=1000, usWinDescent=1000)
        builder.setupPost()
        font = builder.font
        extension = 'otf'
    output = BytesIO()
    font.save(output)
    return output.getvalue(), pairs, advances, space_width, extension


def recover_type1(data, name, observed):
    font, order, glyphs = load_type1(data)
    original_count = len(order)
    cmap, code_for_gid = {}, {}
    # PDF text tracing supplies both Unicode and the real FreeType glyph ID,
    # even when /ToUnicode is absent. Preserve that relationship in the OTF.
    for unicode, gid in sorted(observed):
        if not 0 <= gid < len(order):
            continue
        code = unicode
        if code < 32 or code == 0xFFFD or (code in cmap and cmap[code] != order[gid]):
            code = 0xF0000 + gid
        cmap[code] = order[gid]
        code_for_gid.setdefault(gid, code)
    for gid, glyph in enumerate(order):
        value = agl.toUnicode(glyph)
        if len(value) == 1:
            cmap.setdefault(ord(value), glyph)
        if gid not in code_for_gid:
            code = 0xF0000 + gid
            cmap[code] = glyph
            code_for_gid[gid] = code
    if 32 not in cmap:
        order.append('pdfSpace')
        cmap[32] = 'pdfSpace'
    charstrings, metrics, advances = {}, {}, {}
    for gid, glyph in enumerate(order):
        if gid >= original_count:
            charstrings[glyph] = T2CharStringPen(333, None).getCharString()
            metrics[glyph] = (333, 0)
            continue
        outline = glyphs[glyph]
        bounds = BoundsPen(glyphs)
        outline.draw(bounds)
        width = round(outline.width)
        pen = T2CharStringPen(width, glyphs, roundTolerance=0)
        outline.draw(pen)
        charstrings[glyph] = pen.getCharString()
        metrics[glyph] = (width, round(bounds.bounds[0]) if bounds.bounds else 0)
        advances[gid] = width
    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    builder.setupCFF(name, {'FullName': name, 'FamilyName': name, 'Weight': 'Regular'}, charstrings, {})
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=1000, descent=-400)
    builder.setupNameTable({'copyright': str(font.font.get('FontInfo', {}).get('Notice', '')),
                            'familyName': name, 'styleName': 'Regular', 'uniqueFontIdentifier': name,
                            'fullName': name, 'psName': name})
    builder.setupOS2(sTypoAscender=1000, sTypoDescender=-400, usWinAscent=2000, usWinDescent=1000)
    builder.setupPost()
    output = BytesIO()
    builder.save(output)
    return output.getvalue(), code_for_gid, advances
