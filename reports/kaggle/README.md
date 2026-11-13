# Kaggle PDF conversion evaluation

Dataset: [https://www.kaggle.com/datasets/manisha717/dataset-of-pdf-files](https://www.kaggle.com/datasets/manisha717/dataset-of-pdf-files)

Converter revision: `27e0bf67ce273ef999e71174445d4a3fb53312de`; pipeline fingerprint: `e6d52fafb7ad16e7fd455c0ed4945fa610a589c1e0b303d798ba74c667c02ae7`.

Evaluated 1076 PDF files (1075 distinct SHA-256 hashes).

| Mode | Compiled | Meets target | Dataset score | Grade | Successful mean minimum-page SSIM |
| --- | ---: | ---: | ---: | :---: | ---: |
| layout | 855/1076 | 8/1076 (target 95%) | 26.161% | F | 32.923% |
| portable | 242/1076 | 119/1076 (target 90%) | 17.932% | F | 79.732% |

## Method

All PDFs are inventoried. Unlocked, readable inputs within the application 20 MiB/50-page limits are submitted to the real `/api/convert` and `/api/compile` endpoints. Preflight rejections count as zero. Portable output compiles from only its generated `.tex`; layout output includes its extracted assets. No converter fallback, source repair, page splitting, registration or score-threshold changes are applied. Each conversion/comparison phase is bounded by the recorded phase timeout; compilation retains its existing 90-second timeout.

Visual similarity uses the existing foreground SSIM at up to 144 dpi with a 2200-pixel cap and a two-pixel foreground halo. The document score is its lowest page score; missing pages score zero. Blank margins cannot increase the score. A document passes only when every page meets the existing mode target (90% portable, 95% layout).

The **dataset score** is the arithmetic mean of document scores across all evaluated files, with every rejected/failed document assigned zero. Grades: A >= 90, B >= 80, C >= 70, D >= 60, F < 60. This is an explicit benchmark rubric, not a standardized assessment. The JSON also reports a score limited to unlocked, readable inputs within the application upload/page limits.

Token precision/recall/F1 compare case-folded Unicode word multisets extracted from the original and compiled PDFs. Image-only originals have no text ground truth, so their text scores are null. These scores do not establish reading order, semantic LaTeX quality, equation correctness or OCR accuracy. Layout can reproduce scanned images without recovering editable text; image-only successes are counted separately.

This dataset supplies PDFs, not paired original TeX sources. The evaluation measures visual reconstruction and extracted-text retention, not recovery of original macros. Repeated files remain in the file-weighted score; the manifest includes hashes so duplication is visible.

## Reproduce

```bash
mkdir -p data/kaggle
curl -L --fail "https://www.kaggle.com/api/v1/datasets/download/manisha717/dataset-of-pdf-files" -o data/kaggle/pdfs.zip
python -m zipfile -e data/kaggle/pdfs.zip data/kaggle/pdfs
python scripts/evaluate_dataset.py --inputs data/kaggle/pdfs --output output/kaggle --report-dir reports/kaggle
```

Install the Python dependencies and both compiler images using the README instructions first. Rerunning resumes only matching input hashes and pipeline fingerprints; use a fresh output directory for a separate experiment. Input PDFs and generated sources/PDFs/logs remain in ignored directories.

## Failures

### layout

- 112: LaTeX compilation failed. Check the compiler log and edit the source.
- 42: Exceeds the application 50-page limit.
- 25: Conversion failed. For scans, check the server's OCR model download and try again.
- 13: [{'type': 'string_too_long', 'loc': ['body', 'tex'], 'msg': 'String should have at most 2000000 characters'}]
- 8: Exceeds the application 20 MiB upload limit.
- 7: Upload a PDF with 1–50 pages.
- 4: Invalid project ZIP: Too many files in the project ZIP.
- 3: [{'type': 'string_too_long', 'loc': ['body', 'project_zip'], 'msg': 'String should have at most 70000000 characters'}]
- 2: bad image data
- 1: Password protected PDF.
- 1: bad xref
- 1: This file is not a valid PDF.
- 1: conversion exceeded 240s.
- 1: The compiled PDF exceeds the 20 MB download limit.

### portable

- 160: Page 1 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 83: Portable mode currently supports horizontal text. Use Preserve original layout for rotated text.
- 42: Exceeds the application 50-page limit.
- 37: The inline illustrations exceed the 2 MB single-file source limit. Use Preserve original layout for this PDF.
- 35: Cannot export glyph U+0027 in FreeSans without an external font. Use Preserve original layout for this PDF.
- 34: Portable mode does not embed full-page scan images. Use Reflow / OCR for a scanned PDF.
- 30: Cannot export glyph U+00A7 in AvantGarde-Demi without an external font. Use Preserve original layout for this PDF.
- 30: Cannot export glyph U+FFFD in Helvetica without an external font. Use Preserve original layout for this PDF.
- 29: Cannot export glyph U+2022 in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 20: Conversion failed. For scans, check the server's OCR model download and try again.
- 19: Cannot export glyph U+0022 in FreeSans without an external font. Use Preserve original layout for this PDF.
- 12: Cannot export glyph U+2022 in SourceSansPro-Regular without an external font. Use Preserve original layout for this PDF.
- 12: Cannot export glyph U+0027 in FreeSansBold without an external font. Use Preserve original layout for this PDF.
- 10: Cannot export glyph U+00C9 in OpenSans-SemiBold without an external font. Use Preserve original layout for this PDF.
- 9: Cannot export glyph U+0014 in ZapfDingbats without an external font. Use Preserve original layout for this PDF.
- 8: Cannot export glyph U+00D3 in OpenSans-SemiBold without an external font. Use Preserve original layout for this PDF.
- 8: Cannot export glyph U+2022 in Symbol without an external font. Use Preserve original layout for this PDF.
- 8: Exceeds the application 20 MiB upload limit.
- 7: Page 2 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 7: LaTeX compilation failed. Check the compiler log and edit the source.
- 7: Upload a PDF with 1–50 pages.
- 6: Cannot export glyph U+0027 in Arial without an external font. Use Preserve original layout for this PDF.
- 6: Cannot export glyph U+0022 in FreeSansBold without an external font. Use Preserve original layout for this PDF.
- 5: Cannot export glyph U+FFFD in Wingdings-Regular without an external font. Use Preserve original layout for this PDF.
- 4: Cannot export glyph U+00A7 in TimesNewRoman without an external font. Use Preserve original layout for this PDF.
- 4: Cannot export glyph U+F0B7 in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 4: Cannot export glyph U+005F in Arial without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+0027 in TimesNewRoman without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+005F in TimesNewRoman without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+0022 in Arial without an external font. Use Preserve original layout for this PDF.
- 3: images do not match
- 3: Cannot export glyph U+00B7 in SourceSansPro-Semibold without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+0022 in CourierNewPSMT without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+007C in FreeSansBold without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+00E1 in FreeSansBold without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+00A7 in Melior without an external font. Use Preserve original layout for this PDF.
- 3: Page 4 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 3: Cannot export glyph U+00A7 in CenturySchoolbook without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+0022 in TimesNewRoman without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+0022 in Times New Roman without an external font. Use Preserve original layout for this PDF.
- 3: Cannot export glyph U+0027 in Verdana without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+2022 in OpenSans-Regular without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+0027 in Tahoma without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+003E in DejaVuSansCondensed without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+005F in FreeSans without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+00AD in Minion-Regular without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+FFFD in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+005F in Symbol without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+2026 in Arial,Bold without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+00A7 in NewCenturySchlbk-Bold without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+0022 in FreeSansOblique without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+007C in FreeSans without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+005F in Calibri,Bold without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+200B in Gautami without an external font. Use Preserve original layout for this PDF.
- 2: Cannot export glyph U+007C in OpenSans-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FB02 in Roboto-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in AdvP4C4E74 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00F3 in FreeSans without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0629 in TimesNewRomanPS-BoldMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in Arial,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in FreeSansBold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FB01 in Roboto-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Password protected PDF.
- 1: Cannot export glyph U+2010 in Calibri-Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in Aldine721BT-Roman without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+F0D8 in Wingdings-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in DejaVuSans-Bold without an external font. Use Preserve original layout for this PDF.
- 1: This file is not a valid PDF.
- 1: Page 8 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+0022 in Times New Roman,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in Garamond-Italic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00B7 in Arial without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00C9 in BrandonGrotesque-Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+25A2 in MS-Gothic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+003C in Cambria,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+003E in Bookman Old Style,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2026 in Calibri without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2264 in Arial-ItalicMT without an external font. Use Preserve original layout for this PDF.
- 1: Page 22 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+F074 in Wingdings-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in Perpetua without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+25CF in Arial+1 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2500 in CourierNewPSMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in Univers without an external font. Use Preserve original layout for this PDF.
- 1: Page 10 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+005F in CGTimes without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in FakeFont-00006B3A without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2044 in TimesLDC-Italic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00AD in TimesNewRomanPSMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2026 in Arial without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0001 in T2 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in Futura without an external font. Use Preserve original layout for this PDF.
- 1: Page 17 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+005F in CGTimes-Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FB01 in AdvP6975 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in ArialNarrow-BoldItalic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in MyriadPro-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in TT8A9o00 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+003C in Calibri without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+F0A7 in Wingdings-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in Helvetica-Narrow without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00A7 in MIonic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in Webdings without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in NewCenturySchlbk-Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00D7 in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+F0A7 in Wingdings without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+20AC in Helvetica without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00B0 in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in Arial,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Page 31 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+005F in CourierStd without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in Arial,Italic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in Calibri without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in MyriadPro-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+F0B7 in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FB01 in Clearface-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in Arial without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in TT26Dt00 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00A7 in CourierNewPSMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in Times New Roman without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2026 in BookmanOldStyle-BoldItal without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00B6 in Melior without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00B0 in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FB00 in CMBX12 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in TTE4BD3270t00 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+007B in FreeSans without an external font. Use Preserve original layout for this PDF.
- 1: Page 21 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+25CA in BGsddV01 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+221A in TimesNewRomanPS-BoldMT without an external font. Use Preserve original layout for this PDF.
- 1: Page 33 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+005F in Verdana-Italic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in WPTypographicSymbols without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FB01 in AdvTTe45e47d2+fb without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+007E in Times New Roman without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in Tahoma without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in AGaramond-Semibold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2032 in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00F1 in PalatinoLinotype-Roman without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FB01 in TimesNewRomanPSMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00AD in CourierNewPSMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+F0B0 in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in CGTimes,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in A without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in TimesNewRoman,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in Bookman-LightItalic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in DejaVuSans without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+007C in LucidaConsole without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00C9 in Palatino without an external font. Use Preserve original layout for this PDF.
- 1: Page 36 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+00A7 in ZapfDingbats without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+F096 in Wingdings2 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0022 in Tahoma without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+003C in FreeSansBold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in FreeSansOblique without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in TimesNewRoman,BoldItalic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in Times New Roman without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2026 in DejaVuSerifCondensed-Bol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2212 in ArialNarrow without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+F02A in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2725 in ZapfDingbats without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in CGTimes without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00B1 in SymbolMT without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00AD in Cambria-Italic without an external font. Use Preserve original layout for this PDF.
- 1: Page 16 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+F8EA in Symbol,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+2022 in Hiroshige-Medium without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00D3 in Symbol without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00E9 in TimesNewRoman without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00A5 in BGsddV01 without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+003E in TimesNewRoman,Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+005F in ArialNarrow without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0022 in CenturySchoolbook without an external font. Use Preserve original layout for this PDF.
- 1: Page 3 has no visible text layer. Portable reconstruction currently supports text PDFs; use Reflow / OCR for scans. A scan image alone would not be editable LaTeX.
- 1: Cannot export glyph U+005C in NewCenturySchlbk-Roman without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0142 in FreeSans without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in Calibri-Italic without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+FFFD in Wingdings without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+007C in SourceSansPro-Regular without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+041F in SourceSansPro-Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00F3 in Stag-Book without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+0027 in BrandonGrotesque-Bold without an external font. Use Preserve original layout for this PDF.
- 1: Cannot export glyph U+00C9 in BrandonGrotesque-Medium without an external font. Use Preserve original layout for this PDF.
