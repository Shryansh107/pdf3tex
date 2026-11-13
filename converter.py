"""Text-first adapter for pdf2tex, with EasyOCR for image-only pages."""
import base64
from io import BytesIO
from functools import lru_cache
import re
from zipfile import ZipFile, ZIP_DEFLATED

import pymupdf
from pdf2tex import Utils

MAX_PAGES = 50


@lru_cache(maxsize=1)
def ocr_reader():
    import easyocr
    import torch
    torch.set_num_threads(4)
    return easyocr.Reader(["en"], gpu=False, verbose=False)


def read_scan(page):
    import numpy as np
    # Bound raster dimensions, including unusually large PDF page sizes.
    scale = min(2, 2400 / max(page.rect.width, page.rect.height))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB)
    pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return ocr_reader().readtext(pixels, detail=0, paragraph=True)


def convert_pdf(data: bytes, filename: str, mode: str = 'text'):
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("This file could not be opened as a PDF. It may be damaged.") from exc
    with doc:
        if doc.needs_pass:
            raise ValueError("This PDF is password protected. Upload an unlocked copy.")
        if not 1 <= len(doc) <= MAX_PAGES:
            raise ValueError(f"Upload a PDF with 1–{MAX_PAGES} pages.")
        if mode == 'portable':
            from portable_converter import convert_portable
            return convert_portable(data, filename)
        if mode == 'layout':
            from layout_converter import convert_layout
            return convert_layout(data, filename)
        body, assets, warnings = [], {}, []
        ocr_pages = 0
        text_chars = 0
        for index, page in enumerate(doc):
            body.append(f"% Page {index + 1}")
            blocks = page.get_text("blocks", sort=True)
            paragraphs = [b[4].strip() for b in blocks if b[6] == 0 and b[4].strip()]
            scanned = not paragraphs
            if scanned:
                ocr_pages += 1
                paragraphs = read_scan(page)
            for paragraph in paragraphs:
                text_chars += len(paragraph)
                body.append(Utils.escape_special_chars(" ".join(paragraph.split())) + "\n")
            if not paragraphs:
                warnings.append(f"No readable text was found on page {index + 1}.")
                body.append("% No readable text detected on this page.")
            # A scan's full-page bitmap would duplicate OCR text. Only export
            # embedded images on pages with a text layer.
            if not scanned:
                seen = set()
                for image in page.get_images(full=True):
                    xref = image[0]
                    if xref in seen:
                        continue
                    seen.add(xref)
                    try:
                        pix = pymupdf.Pixmap(doc, xref)
                        if pix.colorspace is None:
                            continue
                        if pix.colorspace.n > 3:
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                        name = f"assets/page_{index + 1}_image_{xref}.png"
                        assets[name] = pix.tobytes("png")
                        body.append("\\begin{figure}[htbp]\n\\centering\n"
                                    + rf"\IfFileExists{{{name}}}{{" + "\n"
                                    + rf"\includegraphics[width=0.8\linewidth,height=0.8\textheight,keepaspectratio]{{{name}}}"
                                    + "\n}{\\fbox{\\parbox{0.8\\linewidth}{"
                                    + "Image omitted. Download and extract the project ZIP to include "
                                    + rf"\texttt{{\detokenize{{{name}}}}}."
                                    + "}}}\n\\end{figure}\n")
                    except Exception:
                        warnings.append(f"An image on page {index + 1} could not be extracted.")
            if index < len(doc) - 1:
                body.append(r"\clearpage" + "\n")
        title = Utils.escape_special_chars(doc.metadata.get("title") or re.sub(r"\.pdf$", "", filename, flags=re.I))
        source = ("% Reconstructed from a PDF. Review equations and layout.\n"
                  "% Compile with XeLaTeX or LuaLaTeX for Unicode support.\n"
                  "% !TeX program = xelatex\n"
                  "\\documentclass[11pt]{article}\n\\usepackage{iftex}\n"
                  "\\ifPDFTeX\n"
                  "  \\usepackage[utf8]{inputenc}\n"
                  "  \\usepackage[T1]{fontenc}\n"
                  "\\else\n"
                  "  \\usepackage{fontspec}\n"
                  "\\fi\n"
                  "\\usepackage[margin=1in]{geometry}\n\\usepackage{graphicx}\n"
                  "\\usepackage{amsmath,amssymb}\n"
                  f"\\title{{{title}}}\n\\author{{}}\n\\date{{}}\n"
                  "\\begin{document}\n" + "\n".join(body) + "\n\\end{document}\n")
        bundle = BytesIO()
        with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
            archive.writestr("main.tex", source)
            archive.writestr("README.txt", "Extract the entire ZIP, then compile main.tex with XeLaTeX or LuaLaTeX.\npdfLaTeX supports basic Latin text; use XeLaTeX for Unicode documents.\nA standalone .tex uses placeholders for missing images.\nReview equations, image placement, tables and layout after conversion.\n")
            for name, content in assets.items():
                archive.writestr(name, content)
        return {"tex": source, "zip": base64.b64encode(bundle.getvalue()).decode(),
                "pages": len(doc), "images": len(assets), "ocr_pages": ocr_pages,
                "characters": text_chars, "warnings": warnings}
