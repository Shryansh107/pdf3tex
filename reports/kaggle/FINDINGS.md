# Kaggle evaluation findings

Evaluated all **1,076 PDFs** (1,075 distinct hashes). The archive passed ZIP CRC checks, and all 1,000 PDF checksums listed in its bundled metadata were found. The remaining 75 distinct PDFs are additional inputs in the Kaggle archive.

Both modes receive **F** under the declared coverage-adjusted visual rubric. Successful compilation often retains words without preserving the appearance of every page.

| Mode | Compiled | Every page meets target | Overall score | Grade | Mean score among compiled PDFs | Text F1 among compiled text PDFs |
| --- | ---: | ---: | ---: | :---: | ---: | ---: |
| layout | 855/1076 | 8/1076 | 26.161% | F | 32.923% | 95.662% |
| portable | 242/1076 | 119/1076 | 17.932% | F | 79.732% | 97.761% |

The overall score averages the lowest page SSIM for each input and assigns zero to every rejected or failed document. Grades are A >=90, B >=80, C >=70, D >=60, F <60. This is a transparent benchmark rubric, not a standardized grade or a measure of semantic TeX recovery.

## What limits the result

Portable mode has a relatively narrow range of supported text/font combinations. Layout mode accepts more documents, but font/glyph handling, spacing, hidden OCR layers and compiler limits prevent broad visual fidelity.

| Outcome | Layout | Portable |
| --- | ---: | ---: |
| Compiled below visual target | 847 | 123 |
| Conversion phase timeout (240s) | 1 | 0 |
| Generated asset bundle exceeds compile limits | 4 | 0 |
| Generated source/project exceeds compile limits | 16 | 37 |
| Invalid PDF header | 1 | 1 |
| LaTeX/compiler failure | 113 | 7 |
| Meets visual target | 8 | 119 |
| Other conversion failure | 10 | 10 |
| Password protected | 1 | 1 |
| Rotated text | 0 | 83 |
| Scan/no supported visible text layer | 0 | 214 |
| Unhandled converter error | 25 | 20 |
| Unsupported glyph/font | 0 | 411 |
| Upload/page limit | 50 | 50 |

## Concrete examples

- **Font/spacing fidelity:** `2A2C2V4WI5YRDJHR26XUD4IAULIYGTMA.pdf` retains 100% word-token F1 in both modes, but portable scores 99.895% and layout 31.349%. Both outputs keep all three pages.
- **Visual pass without editable text:** `ESIAEQENN4LMSOASECP7GLHB4TQ6IDPB.pdf` reaches 99.998% in layout mode while both original and output have zero extractable text tokens. Its 13-page scan is preserved rather than transcribed.
- **Hidden OCR becomes visible:** `3I3G2ZKLILXKCZTX77LVBWNF5IR2ZM7E.pdf` scores 0% in layout mode. The original has 400 invisible text traces (type 3), while the compiled PDF has 83 visible traces (type 0). Its two-page count and page dimensions are preserved.

These cases are recorded in `diagnostics.json`; generated source and compiled PDFs are retained locally under the ignored `output/kaggle/` directories identified by each input ID in `results.json`.

## Scope and limitations

- The existing converter algorithms, foreground SSIM metric, and mode thresholds were used without source repair or converter fallback. The compiler launcher was adjusted to support Windows Docker Desktop.
- Fifty PDFs exceed the existing upload/page limits, and one is password protected. Those inputs count as zero in the full-dataset score. `results.json` also gives the score for the 1,025 inputs within those limits.
- This dataset supplies PDFs, not paired original TeX sources. Text F1 measures word retention, not reading order, mathematical correctness or semantic macro recovery. Reflow/OCR mode was not benchmarked.
- The `image_only_successes` field means zero extractable original word tokens; it can include scans or vector-only documents. A visual pass in layout mode does not establish editability.
- Four isolated processes ran the evaluation; completed initial measurements were resumed. Recorded durations include concurrent load and are not a controlled speed comparison.
- A logging-only patch removed echoed request payloads from validation failures. All 682 already completed status/metric records were preserved with matching checksums; see `log-normalization.json`.

## Next work suggested by the evidence

Broaden font/glyph encoding support, preserve text rendering visibility in layout mode, reconstruct font metrics and spacing consistently, and validate generated projects against compiler limits before returning successful conversion. Preserve this dataset run as the baseline for measuring those changes.

## Validation

The test suite completed with **36 passed, 6 skipped**. The skipped cases require standalone compiler executables or private reference PDFs; the installed Docker compiler integration tests ran successfully. All 2,152 benchmark records were checked for completeness, score aggregation, original pass thresholds, finite metrics, and duplicate-file consistency. No successfully compiled document changed its page count.

See the [metric and reproduction procedure](README.md), [every input and page score](results.json), [installed package versions](requirements-evaluation.txt), and [interactive chart](chart.html).
