# Milestone 1 findings

Re-evaluated all **1,076 PDFs** with the font and visibility improvements. Input hashes, archive, compiler image IDs, installed packages, SSIM metric, and visual targets match the baseline.

| Mode | Compiled before → after | Meets target before → after | Overall score before → after | Current grade |
| --- | ---: | ---: | ---: | :---: |
| layout | 855 → 883 | 8 → 492 | 26.161% → 67.391% | D |
| portable | 242 → 589 | 119 → 275 | 17.932% → 41.688% | F |

Overall score averages every PDF’s lowest page foreground SSIM, assigning zero to rejected and failed inputs. Grades: A ≥90, B ≥80, C ≥70, D ≥60, F <60. This is a declared benchmark rubric, not semantic TeX accuracy.

## Implemented

- Font programs are keyed by content identity and associated with each native MuPDF text span; same-named subsets remain distinct.
- Layout repairs observed Unicode/glyph maps for TrueType, OpenType, CFF and Type 1 fonts. TrueType programs and CFF hinting are retained. Sparse CIDs and conflicting Unicode/glyph pairs are handled explicitly.
- Portable mode chooses a suitable standard family/style and supports common punctuation, accents and ligatures. Rare outline symbols use the source font units.
- Layout text comes from visible traces. Invisible OCR and zero-opacity text are omitted. Explicit TeX spaces retain leading and repeated spaces.
- Stencils retain color/transparency; supported vector rules, images and text keep paint order. Image masks of different dimensions are resampled consistently.
- Mixed-size layout PDFs update the page builder dimensions to preserve page counts and paper sizes.

## Gains and regressions

- **layout:** 126 new compiles and 98 lost compiles; 484 new visual passes and 0 visual passes lost. Among 757 inputs compiled in both versions, mean minimum-page SSIM changes from 34.737% to 81.536%. 20 of these regress by over 1 percentage point.
- **portable:** 347 new compiles and 0 lost compiles; 157 new visual passes and 1 visual passes lost. Among 242 inputs compiled in both versions, mean minimum-page SSIM changes from 79.732% to 83.288%. 16 of these regress by over 1 percentage point.

The 98 lost layout compiles comprise 76 CFF compiler failures (74 Type 2 charstring parser errors and 2 unsupported predefined CFF charsets), 21 font reconstruction rejections, and 1 image decoding failure. Normalizing these font programs for compiler compatibility is the next priority; the aggregate improvement does not remove these regressions.

All status transitions and per-input changes are in [comparison.json](comparison.json). Lost compile diagnostics are listed in [diagnostics.json](diagnostics.json), with the largest score regressions in [COMPARISON.md](COMPARISON.md).

## Examples

- `2A2C2V4WI5YRDJHR26XUD4IAULIYGTMA.pdf`: layout minimum-page SSIM 31.349% → 99.921% (success).
- `3I3G2ZKLILXKCZTX77LVBWNF5IR2ZM7E.pdf`: layout minimum-page SSIM 0% → 86.262% (success).
- `ESIAEQENN4LMSOASECP7GLHB4TQ6IDPB.pdf`: layout minimum-page SSIM 99.998% → 99.998% (success).

The hidden-OCR example now has no exported text traces; the original contains 400 invisible traces. Its scan is reproduced as an image, so this fix improves visibility without claiming editable OCR.

## Remaining limits

- Font identity and visibility fixes improve coverage and appearance, but do not recover original semantic macros, equations, table structures, or reading order.
- Some CFF programs still fail in xdvipdfmx, and malformed fonts or nonstandard font matrices can be rejected. Embedded subsets may lack new characters required for edits.
- Portable mode still rejects scans, rotated text, unsupported glyphs/writing systems, and oversized inline illustrations. Layout still has unsupported drawing/transparency/transform cases.
- Malformed image streams and differences between image decoders can still cause extraction errors.
- The original 20 MiB/50-page input limits, 2-million-character source limit, asset limits, and compiler timeout remain in force. Fifty oversized inputs and one password-protected input count as zero.
- Text F1 includes invisible source OCR in its reference. Omitting invisible OCR can lower F1 while correcting visible appearance. F1 is a word-multiset measure and does not validate semantic recovery.
- Compilation rate and compiled-only means use different cohorts after the change. Paired measurements in comparison.json address this; timing was not controlled as a speed benchmark.

## Validation and reproduction

**53 tests passed, 6 skipped**; Docker compiler integration tests ran. Skipped tests require standalone compilers or private reference PDFs. Generated fixtures cover duplicate font names on/across pages, 2048-unit outlines, CFF wrapping, Unicode map repair, common glyphs, hidden text, stencils, paint order, CID re-export, source edits, leading/repeated spaces and mixed paper sizes.

All 2,152 records are complete and use one run fingerprint. Aggregate scores, finite metrics, page-minimum scores, original pass thresholds, archive/compiler/package identity, duplicate-file consistency and source pipeline hash were checked. Page-count mismatches among compiled outputs: **0**.

Evaluated code revision: `8a6eed67845077447c4477e1ccf9d7bade305fa2`. Pipeline SHA-256: `d8f1ff4e240e8f891fee9569954edaddae01f972d7269296fb592946327266d5`. Generated projects and compiler logs are local under ignored `output/kaggle-milestone1-verified/`.

A page-count audit caught 25 mixed-size inputs gaining blank pages during the first pass. The page-builder repair is emitted only for mixed-size layout PDFs. All eligible mixed-size layout inputs were re-evaluated. 1442 unaffected measurements were reused: portable code was unchanged, uniform-size layout TeX was unchanged, and input rejection rules were unchanged. Original fingerprints remain on reused records, and every canonical measurement checksum is preserved. See [geometry-cache-audit.json](geometry-cache-audit.json) and [the migration script](geometry-cache-migration.py). Timing includes resumed records and must not be treated as a controlled speed comparison.

```bash
python scripts/evaluate_dataset.py --inputs data/kaggle/pdfs --output output/kaggle-milestone1-verified --report-dir reports/kaggle-milestone1 --archive data/kaggle/pdfs.zip --workers 4
python scripts/compare_evaluations.py --before reports/kaggle/results.json --after reports/kaggle-milestone1/results.json --output reports/kaggle-milestone1
```

See [all records and page scores](results.json), [interactive before/after chart](comparison.html), [metric procedure](README.md), and [baseline findings](../kaggle/FINDINGS.md).
