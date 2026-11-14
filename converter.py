"""Validate PDF input and dispatch the supported reconstruction modes."""
import pymupdf

MAX_PAGES = 50


def convert_pdf(data: bytes, filename: str, mode: str = 'readable'):
    if mode not in ('readable', 'layout'):
        raise ValueError('Choose Readable LaTeX or Preserve original layout.')
    try:
        doc = pymupdf.open(stream=data, filetype='pdf')
    except Exception as exc:
        raise ValueError('This file could not be opened as a PDF. It may be damaged.') from exc
    with doc:
        if doc.needs_pass:
            raise ValueError('This PDF is password protected. Upload an unlocked copy.')
        if not 1 <= len(doc) <= MAX_PAGES:
            raise ValueError(f'Upload a PDF with 1-{MAX_PAGES} pages.')
    if mode == 'readable':
        from readable_converter import convert_readable
        return convert_readable(data, filename)
    from layout_converter import convert_layout
    return convert_layout(data, filename)
