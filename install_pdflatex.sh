#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker build -t pdf3tex-pdflatex:local -f compiler/Dockerfile.pdflatex compiler
