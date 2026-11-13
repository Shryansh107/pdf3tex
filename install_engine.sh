#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
version=0.17.0
if [[ "$(uname -s)-$(uname -m)" != Linux-x86_64 ]]; then
  echo 'This installer currently supports Linux x86_64.' >&2
  exit 1
fi
command -v docker >/dev/null
docker info >/dev/null
mkdir -p .tools/cache .tools/warmup
if [[ ! -x .tools/tectonic ]]; then
  curl --fail --location --connect-timeout 15 --max-time 180 \
    "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${version}/tectonic-${version}-x86_64-unknown-linux-musl.tar.gz" \
    --output .tools/tectonic.tar.gz
  tar -xzf .tools/tectonic.tar.gz -C .tools tectonic
fi
cat > .tools/warmup/main.tex <<'TEX'
\documentclass[11pt]{article}
\usepackage{iftex}
\usepackage{fontspec}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{amsmath,amssymb}
\begin{document}
Café — compiler ready. \texttt{assets/example.png} \& 50\%.
\end{document}
TEX
XDG_CACHE_HOME="$PWD/.tools/cache" .tools/tectonic .tools/warmup/main.tex
# Also cache the default 10pt article/fonts for hand-written editor contents.
cat > .tools/warmup/plain.tex <<'TEX'
\documentclass{article}
\begin{document}
Local compiler ready.
\end{document}
TEX
XDG_CACHE_HOME="$PWD/.tools/cache" .tools/tectonic .tools/warmup/plain.tex
cp compiler/layout-warmup.tex .tools/warmup/layout.tex
XDG_CACHE_HOME="$PWD/.tools/cache" .tools/tectonic .tools/warmup/layout.tex
chmod -R a+rX .tools/cache/tectonic
docker build --network=none -t pdf3tex-tectonic:0.17.0 -f compiler/Dockerfile .tools
echo 'Local PDF compiler installed.'
