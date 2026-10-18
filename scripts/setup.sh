#!/bin/sh
set -eu
sbph_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$sbph_dir"
# A uv-managed interpreter keeps .venv independent of any app's cache; SBPH_PYTHON may name another.
uv venv --python "${SBPH_PYTHON:-3.12}" --python-preference only-managed .venv
uv pip install --python .venv/bin/python -r requirements.lock
npm ci --ignore-scripts --no-audit --no-fund
printf '%s\n' 'Ready: ./sbph doctor /path/to/production.json'
