#!/bin/sh
set -eu
sbph_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$sbph_dir"
uv venv --python "${SBPH_PYTHON:-python3.12}" .venv
uv pip install --python .venv/bin/python -r requirements.lock
npm ci --ignore-scripts --no-audit --no-fund
printf '%s\n' 'Ready: ./sbph doctor /path/to/production.json'
