"""Recover an embedded Type 1 face as OpenType, retaining its actual glyphs."""
from io import BytesIO
import struct

from fontTools import agl
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.t1Lib import T1Font, T1Error, findEncryptedChunks
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
    font.parse()
    expected = (.001, 0, 0, .001, 0, 0)
    if any(abs(actual - target) > 1e-8 for actual, target in zip(font.font['FontMatrix'], expected)):
        raise ValueError('Nonstandard Type 1 font matrix requires an explicit transform')
    glyphs = font.getGlyphSet()
    return font, order, glyphs


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
