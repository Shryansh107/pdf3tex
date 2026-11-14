# PDF3TeX

A local web app to upload a PDF, view and edit reconstructed LaTeX, compile it into a PDF, copy the source, and download the `.tex`, PDF, or a ZIP with extracted images.

## Readable LaTeX (default)

Choose **Readable LaTeX · pdfLaTeX** to generate source organized into sections,
paragraphs, lists, bold/italic text and hyperlinks. Resume-like documents use
reusable `\resumeSubheading` commands and skills tables. Words and ligatures are
recovered from visible text and embedded font metadata; PDF links become
`\href` commands. The exported `main.tex` compiles with Overleaf's default
**pdfLaTeX** engine and does not need external fonts or assets.

Structure is inferred from font sizes, formatting and alignment. This does not
recover the original author's macros. Text reflows after edits; the output does
not promise a visual similarity threshold. Review reading order, multi-column
content, equations and tables. Font Awesome 5 icons use named commands with their original size and baseline
rise. Unknown icon fonts use named inline vector fallbacks; unrecoverable icons
and unsupported characters have visible placeholders and warnings. This mode currently exports
text and links, with a warning for omitted embedded images. Use Preserve original layout to retain
scanned images. Use a layout mode to retain illustrations.

`POST /api/convert` defaults to `mode=readable` and returns `engine=pdflatex`.
The available conversion modes are `readable` and `layout`.

## Icons in readable source

Recognized Font Awesome 5 icons become reusable commands such as
`\IconExternalLinkAlt`, defined once using `\faExternalLink*`. Solid, regular and
brand styles are retained, along with the source font size and baseline rise.
The body stays readable; no per-icon drawing coordinates appear among the prose.
Unknown icon fonts use named vector macros in the preamble, keeping the export
self-contained. If an icon cannot be decoded, it gets a visible placeholder and
a warning instead of disappearing.

The pdfLaTeX compiler image installs Font Awesome 5 Free 5.15.4 from a pinned,
SHA-256-verified CTAN archive. Rebuild an older image with `./install_pdflatex.sh`
or `docker build -t pdf3tex-pdflatex:local -f compiler/Dockerfile.pdflatex compiler`.
Overleaf already provides `fontawesome5`; local TeX installations need that
package (and `pgf` for unknown-icon vector fallbacks).

The icon catalog contains names, Unicode values and command mappings, with no
font programs. Regenerate it from the pinned archive with
`python scripts/build_icon_catalog.py /path/to/fontawesome5.zip`.

## Layout and visual verification

**Preserve original layout** is the optional asset-based mode (`mode=layout`). It reconstructs editable text at its original coordinates, preserving font sizes, font encodings, horizontal rules, filled rectangles, embedded images and small pictograms. Embedded Type 1 fonts are reconstructed as OpenType fonts using their actual glyph outlines and PDF glyph IDs, including fonts without a `ToUnicode` map. Original glyph advances and kerning are preserved with explicit spacing corrections. Figure soft masks are preserved so transparent drawings keep their original appearance. Embedded TrueType/OpenType fonts are also extracted when available; unsupported fonts are substituted with a warning. The source contains `PDFtext` / `PDFunicode` calls whose final argument is the editable text, sometimes with explicit `kern` commands. Longer edits retain the fixed original positions and may need manual spacing changes. This mode requires XeLaTeX and its project assets. It does not embed the original PDF or turn text pages into screenshots. Scanned pages remain images in this mode; scanned text is not editable.

**Compile PDF** compares its output against the original selected upload and reports a visual match percentage, a 95% pass/fail target for layout mode, and each page's score. It renders both PDFs with the same PyMuPDF renderer at up to 144 dpi (a 2200-pixel dimension cap), computes structural similarity over foreground regions with a two-pixel halo, and reports the lowest page score. Blank margins cannot inflate the score; missing pages score zero. The metric itself is unchanged. This is a visual measurement, not a guarantee of recovered original macros or semantic correctness.

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

PDF3TeX compiles readable output with **pdfLaTeX (TeX Live)** and asset-based output with **Tectonic 0.17.0 (XeTeX)**. Convert a document, then click **Compile PDF** below the editor. Readable mode compiles only your current editor contents with pdfLaTeX; asset-based modes also supply their extracted assets to Tectonic. The resulting PDF appears below the source, with a **Download PDF** button and an expandable compiler log. Compilation errors appear with their log so you can edit and retry. Editing the source clears the previous preview/download until you compile again.

For imported pdfLaTeX projects (including Lattedit's TikZ layout exports), `/api/compile` also accepts `engine: "pdflatex"` and a base64 project ZIP containing `background.pdf`; `tex` remains the exact supplied source. This engine runs twice for TikZ remember-picture positioning under the same overall 90-second limit and container isolation. No source rewriting or local PDF-to-LaTeX conversion is needed to compile an imported export.

The engine runs in a fresh Docker container for each compilation, with no network, no host files outside the temporary project directory, no shell escape, a read-only engine/cache, a 768 MB memory limit, and a 90-second timeout. Temporary source, images, logs and PDFs are removed after each request. The container is also removed after success, error or timeout. One compilation runs at a time. This requires a running local Docker daemon accessible to your user.

To install or rebuild the compiler on another **Linux x86_64** machine:

```bash
./install_engine.sh
```

The installer downloads the pinned official Tectonic binary, warms its package/font cache, and builds `pdf3tex-tectonic:0.17.0`. Compiler runtime files are stored in ignored `.tools/`, independently of the Python environment. No sudo or system TeX installation is needed. Installation needs internet; compilation uses only cached resources. The generated document's packages are preloaded. If you add a package not already cached, the compiler log reports it; add the package to the installer's warm-up document and rerun the installer to cache it before rebuilding the image.

## Install on another machine

Requires Python 3.11+ and Git:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
./run.sh
```

Alternatively, use `python3 -m venv .venv` and `.venv/bin/python -m pip install` in place of `uv pip install`.

## Conversion behavior

Readable mode extracts visible text, formatting, links, section rules and
underlines into ordinary LaTeX commands. Layout mode reconstructs
text at its original positions. Text extraction and font reconstruction run
locally with PyMuPDF and fontTools. OCR/reflow mode has been removed; no OCR
models or PyTorch installation are required. Scans can be retained as images in
layout mode, with no editable text recovered from those images.

PDF conversion cannot restore the original macros. Review equations, tables,
columns and reading order after conversion.

## Limits and privacy

20 MB and 50 pages per upload. One conversion runs at a time; simultaneous requests receive a retry message. Uploads and results are processed in memory (the multipart framework may temporarily spool uploads to disk, which are closed after each request). No application upload history or database is maintained. Documents are not sent to a cloud conversion API. The interface requests fonts from Google Fonts, with local fallbacks.

Compilation accepts up to 2 million source characters and 48 MB of extracted image assets. Compiled PDF downloads are limited to 20 MB. Compiler sources and results temporarily use disk inside a per-request directory and are deleted when the request finishes.

The original PDF is sent back to the local server during compilation for comparison, then discarded. Generated artifacts under `output/`, private reference PDFs, local engines/caches, and the virtual environment are excluded from Git.

The server binds to localhost by default. This is a personal local tool, with no authentication or production deployment configuration.

## Font reconstruction and editable source

Layout mode associates every visible text trace with its actual MuPDF font
program, identified by SHA-256. Different subsets with the same PostScript name
remain separate, including on the same page. Observed Unicode/glyph pairs repair
the exported font's character map. TrueType outlines and CFF hinting are retained;
Type 1 programs are converted to OpenType. Damaged or unsupported fonts produce
a conversion error.

Invisible OCR and zero-opacity text are omitted from visible reconstruction.
Image stencils retain their paint color and transparency, and supported drawings,
images, and text keep their paint order. Image-only layout exports remain scans.

Words stay editable in the source. `\Spaced{word}{corrections}` keeps original
letter spacing beside the word; edit its first argument normally. Fixed positions
can overlap after longer edits, and embedded subsets may lack new letters.
Fonts with missing or conflicting Unicode mappings use explicit character codes;
these glyphs do not establish semantic text recovery.

## Tests

```bash
uv pip install --python .venv/bin/python pytest httpx
.venv/bin/python -m pytest -q
```

Tests cover text and image extraction, readable document structure, rules and underlines, ZIP contents, escaping, page ordering, upload validation, encrypted documents and rejection of the removed OCR mode.

With the compiler image installed, the suite also exercises the real `/api/compile` flow, edited source and image inclusion, compiler errors, filesystem isolation, timeout cleanup, and ZIP validation. The Docker integration cases skip when the image is not installed.

For real compilation regression tests, install Tectonic and run `LATEX_COMPILER=/path/to/tectonic .venv/bin/python -m pytest tests/test_compilation.py -q`. You can also point `LATEX_COMPILER` at `pdflatex`; the Unicode-only test is skipped for that engine.

## Evaluate a PDF dataset

The historical [milestone 1 evaluation](reports/kaggle-milestone1/FINDINGS.md) compares the former portable mode and layout mode across all
1,076 PDFs with the [preserved baseline](reports/kaggle/FINDINGS.md).

| Mode | Compiled before → after | Every page meets target before → after | Overall score before → after | Current grade |
| --- | ---: | ---: | ---: | :---: |
| layout | 855 → 883 | 8 → 492 | 26.161% → 67.391% | D |
| portable | 242 → 589 | 119 → 275 | 17.932% → 41.688% | F |

The overall score averages each PDF’s lowest page foreground SSIM, counting
failures and rejections as zero. Targets remain 90% portable and 95% layout.
The report includes paired gains and regressions, text retention, remaining
compiler/font limitations, and the checksum audit for reused measurements.

For a dataset evaluation of this app alone, install both compiler images, put
the input PDFs under the ignored `data/` directory, and run:

```bash
python scripts/evaluate_dataset.py --inputs data/kaggle/pdfs --output output/new-evaluation --report-dir reports/new-evaluation
```

This evaluates every PDF recursively in readable and layout modes using the
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
