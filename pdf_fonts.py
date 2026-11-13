"""Associate text traces with the exact font program used by MuPDF.

A PDF can reuse a PostScript/subset name for different font programs, even on
one page. Names are useful for family selection, never as font identities.
"""
from collections import deque
from dataclasses import dataclass
import hashlib

import pymupdf

from font_reconstruction import FontError, load_font


def visible(trace):
    return trace['type'] != 3 and trace.get('opacity', 1) > 0


@dataclass
class FontResource:
    identity: str
    name: str
    data: bytes
    _program: object = None
    _error: str = ''

    def program(self):
        if self._error:
            raise FontError(self._error)
        if self._program is None:
            try:
                self._program = load_font(self.data)
            except FontError as error:
                self._error = str(error)
                raise
        return self._program


class _FontDevice(pymupdf.mupdf.FzDevice2):
    """A small second device pass records font identity, without rasterizing."""
    def __init__(self, registry):
        super().__init__()
        self.registry = registry
        self.seqno = 0
        self.entries = {}
        self.pointers = {}
        self.images = []
        for name in ('fill_path', 'stroke_path', 'fill_text', 'stroke_text',
                     'ignore_text', 'fill_shade', 'fill_image', 'fill_image_mask'):
            getattr(self, 'use_virtual_' + name)()

    def advance(self, *args):
        self.seqno += 1

    fill_path = stroke_path = fill_shade = advance

    def image(self, ctm, color, alpha):
        rect = pymupdf.mupdf.ll_fz_transform_rect(pymupdf.mupdf.fz_unit_rect, ctm)
        self.images.append({'seqno': self.seqno, 'bbox': (rect.x0, rect.y0, rect.x1, rect.y1),
                            'color': color, 'opacity': alpha})
        self.seqno += 1

    def fill_image(self, ctx, image, ctm, alpha, params):
        self.image(ctm, None, alpha)

    def fill_image_mask(self, ctx, image, ctm, colorspace, color, alpha, params):
        rgb = pymupdf.mupdf.fz_convert_color(
            pymupdf.mupdf.FzColorspace(pymupdf.mupdf.ll_fz_keep_colorspace(colorspace)),
            color, pymupdf.mupdf.fz_device_rgb(), pymupdf.mupdf.FzColorspace(),
            pymupdf.mupdf.FzColorParams())[:3] if colorspace else (0, 0, 0)
        self.image(ctm, rgb, alpha)

    def text(self, text, kind):
        span = text.head
        entries = deque()
        while span:
            item = pymupdf.mupdf.FzTextSpan(span)
            font = item.font()
            pointer = font.m_internal_value()
            if pointer not in self.pointers:
                raw = font.m_internal.buffer
                data = bytes(pymupdf.mupdf.ll_fz_buffer_storage_memoryview(raw, False)) if raw else b''
                name = pymupdf.mupdf.fz_font_name(font)
                identity = hashlib.sha256(data if data else name.encode()).hexdigest()
                self.registry.resources.setdefault(identity, FontResource(identity, name, data))
                self.pointers[pointer] = identity
            if span.len:
                entries.append(self.pointers[pointer])
            span = span.next
        self.entries[(self.seqno, kind)] = entries
        self.seqno += 1

    def fill_text(self, ctx, text, *args):
        self.text(text, 0)

    def stroke_text(self, ctx, text, *args):
        self.text(text, 1)

    def ignore_text(self, ctx, text, *args):
        self.text(text, 3)


class FontRegistry:
    def __init__(self, document):
        self.resources = {}
        self.pages = []
        self.images = []
        for page in document:
            traces = page.get_texttrace()
            device = _FontDevice(self)
            try:
                pymupdf.mupdf.fz_run_page(page.this, device, pymupdf.mupdf.FzMatrix(), pymupdf.mupdf.FzCookie())
            finally:
                pymupdf.mupdf.fz_close_device(device)
            for trace in traces:
                entries = device.entries.get((trace['seqno'], trace['type']))
                if not entries:
                    raise ValueError('Could not associate a text span with its PDF font resource.')
                trace['font_key'] = entries.popleft()
            self.pages.append(traces)
            self.images.append(device.images)
