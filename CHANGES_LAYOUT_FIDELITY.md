# What changed to improve PDF fidelity

The application uses the upstream `pdf2tex` 0.1.2 utility pinned to Git
commit `a5d6f7c62ae6f8922bfffb2a5e38dae6a365c7cb` through `requirements.txt`.
The utility itself is unmodified; the features described here are provided by
the PDF3TeX application around it.

## Changes that produced the résumé fidelity improvement

| File | Behavior added |
| --- | --- |
| `layout_converter.py` | Places editable text at its original PDF coordinates, with original page dimensions, baselines, sizes and colors. Preserves supported Computer Modern font encodings, extracts embedded TrueType/OpenType fonts, redraws horizontal rules, and places images/pictograms at their original positions. Replaces the earlier paragraph reflow for layout mode. |
| `font_reconstruction.py` | Recovers embedded Type 1/PFA/PFB fonts as OpenType with the original glyph outlines, widths and glyph-ID-to-Unicode relationships. Handles absent `ToUnicode` maps without dropping math symbols or replacing Times-family fonts. |
| `converter.py` | Routes layout-mode requests to the new converter while keeping the earlier text/OCR converter available. |
| `app.py` | Accepts the original PDF during compilation for comparison. Layout was the initial default; the later portable export is now the default. |
| `comparison.py` | Renders both PDFs at up to 144 dpi, measures foreground structural similarity while excluding blank margins, detects missing pages, and reports whether every page reaches 95%. |
| `compiler.py` | Compiles the edited source with its images and extracted fonts, then compares the actual compiled PDF against the original. Compilation remains isolated in Docker. |
| `compiler/layout-warmup.tex`, `install_engine.sh` | Cache the layout packages and fonts required by the generated LaTeX, including Computer Modern fonts and fixed Latin Modern fallback faces. |
| `static/index.html`, `static/app.js`, `static/style.css` | Expose preserve-layout versus text/OCR modes, compilation, PDF preview/download, compiler logs, visual match score and per-page results. |
| `tests/test_layout.py` | Tests dimensions/coordinates/editable text, comparison behavior, missing pages, and an optional private-reference regression requiring at least 95%. |

The rest of the application files provide upload validation, OCR, compiler
limits, setup, documentation, and earlier compilation fixes. They are included
in the upstream-to-app diff but are not all newly invented fidelity changes.

## Verified results and limits

- The one-page résumé reference initially reached **99.146%** foreground SSIM,
  retaining its original one-page layout and editable body text.
- The initial attention-paper reconstruction did **not** reach 95%. After caching missing math fonts,
  its local output scored **23.432% mean page similarity**, with a worst-page
  score of **15.870%**.
- The subsequent Type 1 font/glyph fixes preserve actual glyph outlines and
  encodings, restore per-word kerning and exact advances, and redraw the filled
  title rule. Figure transparency masks are preserved. The paper now reaches **98.68% mean similarity**, with **97.38%**
  on its lowest-scoring page. Every one of its 11 pages passes 95%, using the
  original unchanged comparison metric. The résumé also improves to **99.32%**.
  No original PDF pages or rendered page screenshots are embedded as a shortcut.
- Text remains selectable. Tests edit generated words and verify that the edits
  appear in the compiled PDF. Layout mode keeps absolute positions; it does not
  recover the original document's semantic macros or automatic paragraph flow.
- `scripts/benchmark.py` and its README instructions were added later to compare
  the other MCP project against this app. They measure results; they did not
  produce the résumé fidelity improvement.
- `pytest.ini` scopes the app's tests to `tests/`.
- Later imported-project compatibility adds `compiler/Dockerfile.pdflatex`,
  `install_pdflatex.sh`, an explicit pdfLaTeX API engine option and staging for
  Lattedit's `background.pdf`. This compiles supplied exports unchanged; it is
  separate from the earlier résumé reconstruction improvement.

Private reference PDFs, compiled artifacts, caches and the virtual environment
are excluded from the repository.

## Later single-file portability change (90% target)

- `portable_converter.py` adds the default `portable` mode. It uses standard
  TeX fonts, groups editable text by baseline, and keeps words intact with a
  `Spaced` macro whose separate second argument stores original letter spacing.
  Nonstandard symbols become inline outlines; illustrations become inline vector
  contours. The export has no `fontspec`, font/image files, original-page PDFs,
  full-page screenshots, binary payloads or shell escape requirements.
- `portable_fonts.json` records standard TeX font encodings and metrics only.
  `scripts/build_portable_fonts.py` reproducibly refreshes this metadata from our
  TeX Live image. `font_reconstruction.py` shares its Type 1 parsing helper with
  both converters; the existing asset-based export remains available.
- `converter.py`, `app.py` and the UI route the new mode and choose pdfLaTeX.
  The UI sends only the editor source for portable compilation, with no ZIP.
  It displays a 90% pass/fail target for portable mode; the SSIM algorithm and
  asset-based 95% regressions remain unchanged. The portable ZIP contains only
  `main.tex` as an optional convenience.
- `compiler/layout-warmup.tex` caches PGF and standard fonts for the additional
  XeTeX portability checks. `tests/test_portable.py` verifies single-file ZIP
  contents, actual source-only compilation, edits that lengthen a word, scan
  rejection and each reference page reaching 90% without supplied assets.
- Source-only pdfLaTeX results: résumé **99.461%**; attention paper **95.314%**
  lowest page. All 11 paper pages pass. The exact same source also passes in
  XeTeX (résumé **95.124%**, paper **95.250%**) and LuaLaTeX (**99.479%** and
  **95.131%**). These measure worst-page foreground SSIM, not blank-page area.
- Portable mode targets supported text PDFs. Scans/invisible OCR overlays are
  explicitly rejected, rather than exporting their page image as editable
  LaTeX. OCR reflow is still available, without a 90% fidelity guarantee. Text
  positions remain fixed; original semantic math/template macros are not recovered.

The full suite passes **40 tests**. Sources, compiled PDFs, per-page metrics,
live-server verification and a report are under ignored `output/portable/`.
All application changes remain **unstaged**, including this portability work.
