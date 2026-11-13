# PDF3TeX

A local web app to upload a PDF, view and edit reconstructed LaTeX, compile it into a PDF, copy the source, and download the `.tex`, PDF, or a ZIP with extracted images.

## Portable single-file export (default)

Choose **Portable single .tex · 90% target**, convert, then copy the **entire** source or download `.tex`. Paste it into `main.tex` in Overleaf, TeX Live or MiKTeX and compile with **pdfLaTeX**. No ZIP, original PDF, image files, custom fonts, shell escape or external service is needed. Standard packages `iftex`, `pgf`, `xcolor` and `geometry`, plus the standard Computer Modern/AMS, PSNFSS and Latin Modern fonts, must be installed. This mode does not use `fontspec` and also supports XeLaTeX and LuaLaTeX.

The converter groups editable text by baseline, uses standard TeX fonts and preserves glyph positioning/spacing. Words stay intact in the source: edit the first argument of `\\Spaced{word}{spacing corrections}` normally. Nonstandard symbols use inline vector outlines; raster illustrations become quantized inline vector contours. It never embeds original pages, full-page screenshots or binary file payloads. The resulting source is larger for illustrated documents: about 34 KB for the résumé and 1.24 MB for the attention paper. Illustrations are represented as vector drawing commands, not recovered editable figure text.

This is a fixed-layout reconstruction, not the original semantic LaTeX template. Longer edits can overlap adjacent material. Equations remain positioned glyphs rather than recovered `\\frac` or equation environments. Scanned pages and invisible OCR overlays are rejected in portable mode: choose **Reflow editable text / OCR** to transcribe scans. Fonts outside the supported standard families may be substituted with a warning, and unsupported glyphs, rotated text or excessive inline graphics produce an explicit error. A 90% match is a measured target, not a guarantee for arbitrary input PDFs.

Install the local default compiler with `./install_pdflatex.sh`. The UI compiles portable source using pdfLaTeX **without passing the project ZIP**. `/api/convert` defaults to `mode=portable` and returns `engine=pdflatex` and `fidelity_target=90`; send these fields, `tex` and optionally `original_pdf` to `/api/compile`. The ZIP for this mode contains only `main.tex`.

Tests compile just the source in an isolated temporary directory, verify visible source edits, and require every private reference page to reach 90%. Standard font encoding/advance metadata lives in `portable_fonts.json`; regenerate it using `.venv/bin/python scripts/build_portable_fonts.py` after building the TeX Live image. The metadata contains no embedded fonts or outlines.

Measured single-file pdfLaTeX results: résumé **99.461%**, attention paper **95.314% lowest page** (all 11 pages pass). The exact same files also pass in Tectonic/XeTeX and LuaLaTeX. These are results for those reference inputs, not an arbitrary-PDF guarantee.

## Layout and visual verification

**Preserve original layout** is the optional asset-based mode (`mode=layout`). It reconstructs editable text at its original coordinates, preserving font sizes, font encodings, horizontal rules, filled rectangles, embedded images and small pictograms. Embedded Type 1 fonts are reconstructed as OpenType fonts using their actual glyph outlines and PDF glyph IDs, including fonts without a `ToUnicode` map. Original glyph advances and kerning are preserved with explicit spacing corrections. Figure soft masks are preserved so transparent drawings keep their original appearance. Embedded TrueType/OpenType fonts are also extracted when available; unsupported fonts are substituted with a warning. The source contains `PDFtext` / `PDFunicode` calls whose final argument is the editable text, sometimes with explicit `kern` commands. Longer edits retain the fixed original positions and may need manual spacing changes. This mode requires XeLaTeX and its project assets. It does not embed the original PDF or turn text pages into screenshots. Scanned pages remain images in this mode; select **Reflow editable text / OCR** to transcribe scans into paragraphs instead.

**Compile PDF** compares its output against the original selected upload and reports a visual match percentage, a pass/fail result (90% portable, 95% layout), and each page's score. It renders both PDFs with the same PyMuPDF renderer at up to 144 dpi (a 2200-pixel dimension cap), computes structural similarity over foreground regions with a two-pixel halo, and reports the lowest page score. Blank margins cannot inflate the score; missing pages score zero. The metric itself is unchanged. This is a visual measurement, not a guarantee of recovered original macros or semantic correctness.

The résumé reference exceeds 99% foreground SSIM. The 11-page attention-paper reference, formerly at 23.43% mean similarity, now exceeds 95% on every page (about 98.68% mean, 97.38% lowest page) after font/glyph reconstruction and spacing fixes. Both retain selectable text and their original page counts. Regression tests verify that editing the source changes the compiled text. These are measured results for the tested documents, not a guarantee for arbitrary PDFs. Font substitutions, unusual vector paths, rotated text, nonstandard font matrices and mixed page sizes may need additional reconstruction. Equations are reconstructed from positioned glyphs; original semantic math macros are not recovered. Original PDF hyperlinks are not currently reconstructed.

Run the private reference regression without adding your PDF to Git:

```bash
PDF3TEX_REFERENCE=/path/to/reference.pdf .venv/bin/python -m pytest tests/test_layout.py -q
```

Test several private references together with `PDF3TEX_REFERENCES=/path/resume.pdf:/path/paper.pdf`. Each reference must independently exceed 95% on every page. The comparison metric and threshold have not been relaxed.

## Run

After installing the dependencies below:

```bash
./run.sh
```

Open **http://127.0.0.1:8000**. Set `PORT=8001 ./run.sh` to use another port.

## Compile the generated LaTeX

PDF3TeX compiles portable output with **pdfLaTeX (TeX Live)** and asset-based output with **Tectonic 0.17.0 (XeTeX)**. Convert a document, then click **Compile PDF** below the editor. Portable mode compiles only your current editor contents with pdfLaTeX; asset-based modes also supply their extracted assets to Tectonic. The resulting PDF appears below the source, with a **Download PDF** button and an expandable compiler log. Compilation errors appear with their log so you can edit and retry. Editing the source clears the previous preview/download until you compile again.

For imported pdfLaTeX projects (including Lattedit's TikZ layout exports), `/api/compile` also accepts `engine: "pdflatex"` and a base64 project ZIP containing `background.pdf`; `tex` remains the exact supplied source. This engine runs twice for TikZ remember-picture positioning under the same overall 90-second limit and container isolation. No source rewriting or local PDF-to-LaTeX conversion is needed to compile an imported export.

The engine runs in a fresh Docker container for each compilation, with no network, no host files outside the temporary project directory, no shell escape, a read-only engine/cache, a 768 MB memory limit, and a 90-second timeout. Temporary source, images, logs and PDFs are removed after each request. The container is also removed after success, error or timeout. One compilation runs at a time. This requires a running local Docker daemon accessible to your user.

To install or rebuild the compiler on another **Linux x86_64** machine:

```bash
./install_engine.sh
```

The installer downloads the pinned official Tectonic binary, warms its package/font cache, and builds `pdf3tex-tectonic:0.17.0`. Compiler runtime files are stored in ignored `.tools/`, independently of the Python environment. No sudo or system TeX installation is needed. Installation needs internet; compilation uses only cached resources. The generated document's packages are preloaded. If you add a package not already cached, the compiler log reports it; add the package to the installer's warm-up document and rerun the installer to cache it before rebuilding the image.

## Install on another machine

Requires Python 3.11+ and Git. CPU-only PyTorch avoids unnecessary GPU packages:

```bash
uv venv .venv
uv pip install --python .venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r requirements.txt
./run.sh
```

Alternatively, use `python3 -m venv .venv` and `.venv/bin/python -m pip install` in place of `uv pip install`.

## Utility and conversion behavior

The screenshot matches [p3nGu1nZz/pdf2tex](https://github.com/p3nGu1nZz/pdf2tex), version 0.1.2. This app pins Git commit `a5d6f7c62ae6f8922bfffb2a5e38dae6a365c7cb`. The newer PyPI package named `pdf2tex` has a different CLI and infrastructure requirements.

The original utility is installed and accessible through `.venv/bin/pdf2tex --help`. Its unmodified OCR pipeline has upstream defects (including missing string conversions and nested semaphore acquisition). The app therefore uses `converter.py` to route portable, layout and text/OCR requests. The text/OCR adapter uses the installed utility's LaTeX escaping, PyMuPDF extraction and EasyOCR. It does not invoke the defective upstream conversion pipeline. The following details apply to text/OCR and asset-based modes:

- Selectable text is extracted directly, keeping paragraphs and page order.
- Pages with no text layer use English EasyOCR on CPU. Initial use downloads OCR weights into `~/.EasyOCR`; this requires internet. Later conversions use the cached models.
- Embedded images on text pages are exported as PNG assets and included after that page's text. Full scan bitmaps are omitted to avoid duplicating OCR output. Mixed text-and-scan pages only extract their text layer; text inside figures is not transcribed.
- Compile `main.tex` using **XeLaTeX or LuaLaTeX** for Unicode support. The preamble also supports pdfLaTeX for basic Latin text. Install a TeX distribution or upload the ZIP to Overleaf and select XeLaTeX in the project settings.
- Extract the entire ZIP before compiling to include images and any embedded fonts. A `.tex` file alone cannot reproduce those assets. Reflow mode supports pdfLaTeX for basic text; layout mode requires XeLaTeX.
- **Download .tex** includes editor changes. **Original project ZIP** contains the original conversion and images; replace `main.tex` inside the ZIP with your edited `.tex` if needed.
- PDF conversion cannot restore the original macros or exact layout. Equations, tables, columns, reading order and figure placement need review. This is a text/OCR converter, not a mathematical expression recognition model.

## Limits and privacy

20 MB and 50 pages per upload. One conversion runs at a time; simultaneous requests receive a retry message. Uploads and results are processed in memory (the multipart framework may temporarily spool uploads to disk, which are closed after each request). No application upload history or database is maintained. Documents are not sent to a cloud conversion API. The interface requests fonts from Google Fonts, with local fallbacks.

Compilation accepts up to 2 million source characters and 48 MB of extracted image assets. Compiled PDF downloads are limited to 20 MB. Compiler sources and results temporarily use disk inside a per-request directory and are deleted when the request finishes.

The original PDF is sent back to the local server during compilation for comparison, then discarded. Generated artifacts under `output/`, private reference PDFs, local engines/caches, and the virtual environment are excluded from Git.

The server binds to localhost by default. This is a personal local tool, with no authentication or production deployment configuration. OCR may take several minutes for large scans.

## Tests

### Font reconstruction and editable source

Layout mode associates every visible text trace with its actual MuPDF font
program, identified by SHA-256. Different subsets with the same PostScript name
remain separate, including on the same page. Observed Unicode/glyph pairs repair
the exported font's character map. TrueType outlines and CFF hinting are retained;
Type 1 programs are converted to OpenType. Damaged or unsupported fonts produce
a conversion error rather than a silent substitution.

Invisible OCR and zero-opacity text are omitted from visible reconstruction.
Image stencils retain their paint color and transparency, and supported drawings,
images, and text keep their paint order. Image-only layout exports remain scans.

Words stay editable in the source. `\Spaced{word}{corrections}` keeps original
letter spacing beside the word; edit its first argument normally. Fixed positions
can overlap after longer edits, and embedded subsets may lack new letters.
Fonts with missing or conflicting Unicode mappings use explicit character codes;
these glyphs do not establish semantic text recovery.

Portable mode selects standard Times, Helvetica, Courier, or known TeX faces
using the original family and style. Common punctuation, accents, and ligatures
remain text. Rare supported symbols can use inline outlines, normalized to the
original font's units. Portable exports still contain only `main.tex`; scans,
rotated text, and unsupported writing systems can require another mode.

### Run the suite

```bash
uv pip install --python .venv/bin/python pytest httpx
.venv/bin/python -m pytest -q
```

Tests cover real text and image extraction, ZIP contents, escaping, page ordering, upload validation, encrypted documents and OCR routing. OCR routing is mocked in the test suite to avoid downloading models during tests.

With the compiler image installed, the suite also exercises the real `/api/compile` flow, edited source and image inclusion, compiler errors, filesystem isolation, timeout cleanup, and ZIP validation. The Docker integration cases skip when the image is not installed.

For real compilation regression tests, install Tectonic and run `LATEX_COMPILER=/path/to/tectonic .venv/bin/python -m pytest tests/test_compilation.py -q`. You can also point `LATEX_COMPILER` at `pdflatex`; the Unicode-only test is skipped for that engine.

## Evaluate a PDF dataset

The [full Kaggle evaluation](reports/kaggle/FINDINGS.md) covers all 1,076 PDFs.
Portable mode scores **17.932% (F)** and layout mode **26.161% (F)** across the
dataset, averaging each document's lowest page SSIM and counting failures and
rejections as zero. Portable compiles 242 inputs and meets its 90% target on 119;
layout compiles 855 and meets its 95% target on 8. See the report for successful
document scores, text retention, limitations, and concrete failure examples.

For a dataset evaluation of this app alone, install both compiler images, put
the input PDFs under the ignored `data/` directory, and run:

```bash
python scripts/evaluate_dataset.py --inputs data/kaggle/pdfs --output output/kaggle --report-dir reports/kaggle
```

This evaluates every PDF recursively in portable and layout modes using the
real conversion and compilation APIs. It keeps generated sources, PDFs and logs
under `output/` and writes a compact report and JSON results under `reports/`.
Failed and rejected documents count as zero in the overall score; successful
document scores and text token retention are also reported separately. Two
isolated worker processes run by default; use `--workers 1` for a serial run.
Matching completed results resume automatically. Use fresh output and report
directories for a separate experiment. See `--help` for options.

Docker compilation supports Linux and Windows with Docker Desktop using Linux
containers. The shell compiler installers require Linux; on Windows the
pdfLaTeX image can be built with `docker build -t pdf3tex-pdflatex:local -f compiler/Dockerfile.pdflatex compiler`.

## Benchmark another MCP project

`scripts/benchmark.py` compares PDFs in a folder using this running server and the separate Lattedit MCP CLI project. It writes sources, compiled PDFs, logs, per-page foreground SSIM, token recall/precision/F1, and failure details under an output directory. Neither converter is edited. Use a new output directory per benchmark:

```bash
.venv/bin/python scripts/benchmark.py --workflow local --inputs pdfs --mcp-project /path/to/mcp-project --output output/new-benchmark
.venv/bin/python scripts/benchmark.py --workflow mcp --inputs pdfs --mcp-project /path/to/mcp-project --output output/new-benchmark
.venv/bin/python scripts/benchmark.py --workflow control --inputs pdfs --mcp-project /path/to/mcp-project --output output/new-benchmark
```

The MCP workflow uploads reconstructed source/assets to Lattedit through the other project's real MCP client. It preserves a default-engine failure and, when necessary, records a separate XeLaTeX retry. The control compiles our generated source through MCP to separate reconstruction differences from compiler differences. `local-warmed` records an additional local run after runtime font-cache repair, without overwriting the initial local failure. Visual score means page-aligned image similarity, not semantic accuracy; token metrics do not validate mathematical expressions or reading order.
