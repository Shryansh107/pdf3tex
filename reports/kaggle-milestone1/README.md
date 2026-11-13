# Kaggle PDF conversion evaluation

Dataset: [https://www.kaggle.com/datasets/manisha717/dataset-of-pdf-files](https://www.kaggle.com/datasets/manisha717/dataset-of-pdf-files)

Converter revision: `8a6eed67845077447c4477e1ccf9d7bade305fa2`; pipeline fingerprint: `d8f1ff4e240e8f891fee9569954edaddae01f972d7269296fb592946327266d5`.

Evaluated 1076 PDF files (1075 distinct SHA-256 hashes).

| Mode | Compiled | Meets target | Dataset score | Grade | Successful mean minimum-page SSIM |
| --- | ---: | ---: | ---: | :---: | ---: |
| layout | 883/1076 | 492/1076 (target 95%) | 67.391% | D | 82.121% |
| portable | 589/1076 | 275/1076 (target 90%) | 41.688% | F | 76.156% |

## Method

All PDFs are inventoried. Unlocked, readable inputs within the application 20 MiB/50-page limits are submitted to the real `/api/convert` and `/api/compile` endpoints. Preflight rejections count as zero. Portable output compiles from only its generated `.tex`; layout output includes its extracted assets. No converter fallback, source repair, page splitting, registration or score-threshold changes are applied. Each conversion/comparison phase is bounded by the recorded phase timeout; compilation retains its existing 90-second timeout.

Visual similarity uses the existing foreground SSIM at up to 144 dpi with a 2200-pixel cap and a two-pixel foreground halo. The document score is its lowest page score; missing pages score zero. Blank margins cannot increase the score. A document passes only when every page meets the existing mode target (90% portable, 95% layout).

The **dataset score** is the arithmetic mean of document scores across all evaluated files, with every rejected/failed document assigned zero. Grades: A >= 90, B >= 80, C >= 70, D >= 60, F < 60. This is an explicit benchmark rubric, not a standardized assessment. The JSON also reports a score limited to unlocked, readable inputs within the application upload/page limits.

Token precision/recall/F1 compare case-folded Unicode word multisets extracted from the original and compiled PDFs. Image-only originals have no text ground truth, so their text scores are null. These scores do not establish reading order, semantic LaTeX quality, equation correctness or OCR accuracy. Layout can reproduce scanned images without recovering editable text; image-only successes are counted separately.

This dataset supplies PDFs, not paired original TeX sources. The evaluation measures visual reconstruction and extracted-text retention, not recovery of original macros. Repeated files remain in the file-weighted score; the manifest includes hashes so duplication is visible.

## Reproduce

```bash
curl -L --fail "https://www.kaggle.com/api/v1/datasets/download/manisha717/dataset-of-pdf-files" -o data/kaggle/pdfs.zip
python -m zipfile -e data/kaggle/pdfs.zip data/kaggle/pdfs
python scripts/evaluate_dataset.py --inputs data/kaggle/pdfs --output output/kaggle --report-dir reports/kaggle
```

Install the Python dependencies and both compiler images using the README instructions first. Rerunning resumes only matching input hashes and pipeline fingerprints; use a fresh output directory for a separate experiment. Input PDFs and generated sources/PDFs/logs remain in ignored directories.

## Failures

### layout

- 78: LaTeX compilation failed. Check the compiler log and edit the source.
- 42: Exceeds the application 50-page limit.
- 13: [{'type': 'string_too_long', 'loc': ['body', 'tex'], 'msg': 'String should have at most 2000000 characters'}]
- 8: Exceeds the application 20 MiB upload limit.
- 7: Upload a PDF with 1–50 pages.
- 3: Invalid project ZIP: Too many files in the project ZIP.
- 3: The compiled PDF exceeds the 20 MB download limit.
- 2: Compilation exceeded 90 seconds. Simplify the source and try again.
- 2: Conversion failed. For scans, check the server's OCR model download and try again.
- 2: Cannot reconstruct font Helvetica-Oblique: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 2: [{'type': 'string_too_long', 'loc': ['body', 'project_zip'], 'msg': 'String should have at most 70000000 characters'}]
- 1: Password protected PDF.
- 1: Cannot reconstruct font Helvetica-Narrow-Bold: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: This file is not a valid PDF.
- 1: Invalid project ZIP: Project assets exceed the 48 MB compilation limit.
- 1: Cannot reconstruct font MCUQAC+Roboto-Bold: ValueError: Nonstandard Type 1 font matrix requires an explicit transform
- 1: Cannot reconstruct font QSWINA+Cambria: TTLibError: not enough 'hmtx' table data: expected 11336 bytes, got 3796
- 1: Cannot reconstruct font GXXEHC+Univers-Oblique: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: Cannot reconstruct font MPLHEP+Helvetica-Oblique: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: Cannot reconstruct font RRTVUI+Calibri: TTLibError: not enough 'hmtx' table data: expected 4184 bytes, got 3970
- 1: Cannot reconstruct font KPSHBO+Symbol: TTLibError: not enough 'hmtx' table data: expected 626 bytes, got 484
- 1: Cannot reconstruct font GFEDCB+MinionPC: ValueError: Nonstandard Type 1 font matrix requires an explicit transform
- 1: Cannot reconstruct font GLCGOG+Helvetica-Narrow-Bold: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: Cannot reconstruct font T3: RuntimeError: FT_Open_Face (ft2font.cpp line 200) failed with error 0x55: invalid stream operation
- 1: Cannot reconstruct font ArialNarrow-BoldItalic: TTLibError: not enough 'glyf' table data
- 1: Cannot reconstruct font T1: RuntimeError: FT_Open_Face (ft2font.cpp line 200) failed with error 0x55: invalid stream operation
- 1: conversion exceeded 240s.
- 1: Cannot reconstruct font VNZQXL+Tahoma,Bold: TTLibError: not enough 'hmtx' table data: expected 4250 bytes, got 356
- 1: Cannot reconstruct font ASIQSV+Calibri: TTLibError: not enough 'hmtx' table data: expected 4184 bytes, got 3970
- 1: Cannot reconstruct font CHMRMR+Arial,Bold: TTLibError: not enough 'hmtx' table data: expected 7200 bytes, got 716
- 1: Cannot reconstruct font EJJVUC+TT26Et00: TTLibError: not enough 'hmtx' table data: expected 652 bytes, got 376
- 1: Cannot reconstruct font UKDQUU+Helvetica-Condensed-Bold: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: Cannot reconstruct font CNIOJD+Courier-Oblique: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: Cannot reconstruct font THKMZX+TTE196E3A0t00: TTLibError: not enough 'hmtx' table data: expected 4406 bytes, got 4328
- 1: Cannot reconstruct font KPSHBO+TimesNewRoman: TTLibError: not enough 'hmtx' table data: expected 3356 bytes, got 16
- 1: Cannot reconstruct font CIYRPL+TTE1AE4008t00: TTLibError: not enough 'hmtx' table data: expected 888 bytes, got 736
- 1: Cannot reconstruct font A: RuntimeError: FT_Open_Face (ft2font.cpp line 200) failed with error 0x55: invalid stream operation
- 1: Cannot reconstruct font HDHABL+Courier-Oblique: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: Cannot reconstruct font AHDPDF+BroadbandICGRegular: UnicodeDecodeError: 'ascii' codec can't decode byte 0xa9 in position 1: ordinal not in range(128)
- 1: Cannot reconstruct font KPSHBO+Cambria: TTLibError: not enough 'hmtx' table data: expected 13990 bytes, got 16
- 1: Cannot reconstruct font SDMWJR+LubalinGraph-DemiOblique: FontError: Nonstandard CFF font matrix requires an explicit transform.
- 1: Cannot reconstruct font LLIMEA+BritannicBold: ValueError: Nonstandard Type 1 font matrix requires an explicit transform

### portable

- 160: Page 1 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 99: Portable mode currently supports horizontal text. Use Preserve original layout for rotated text.
- 78: The inline illustrations exceed the 2 MB single-file source limit. Use Preserve original layout for this PDF.
- 42: Exceeds the application 50-page limit.
- 34: Portable mode does not embed full-page scan images. Use Reflow / OCR for a scanned PDF.
- 13: LaTeX compilation failed. Check the compiler log and edit the source.
- 8: Exceeds the application 20 MiB upload limit.
- 7: Page 2 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 7: Upload a PDF with 1–50 pages.
- 3: Cannot export glyph U+03BC in SourceSansPro-Semibold without an external font. Use Preserve original layout for this PDF.
- 3: images do not match
- 3: Page 4 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 3: Conversion failed. For scans, check the server's OCR model download and try again.
- 1: Cannot export glyph U+0629 in TimesNewRomanPS-BoldMT without an external font. Use Preserve original layout for this PDF.
- 1: Password protected PDF.
- 1: This file is not a valid PDF.
- 1: Page 8 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+2265 in Cambria without an external font. Use Preserve original layout for this PDF.
- 1: Page 22 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+0391 in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 1: Page 10 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+03B1 in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+03A3 in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0001 in T2 without an external font. Use Preserve original layout for this PDF.
- 1: Page 17 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+03C4 in CMMI8 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+25CB in T1 without an external font. Use Preserve original layout for this PDF.
- 1: conversion exceeded 240s.
- 1: Page 31 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+00AD in TT26Dt00 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in TTE4BD3270t00 without an external font. Use Preserve original layout for this PDF.
- 1: Page 21 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Page 33 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+03BC in AdvTT182ff89e+03 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+03C1 in TimesNewRomanPS-ItalicMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in A without an external font. Use Preserve original layout for this PDF.
- 1: Page 36 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Page 16 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Page 3 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+041F in SourceSansPro-Bold without an external font. Use Preserve original layout for this PDF.
