#!/bin/sh
# Full Python suite, or pass unittest arguments: scripts/test.sh test_resolve
set -eu
sbph_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$sbph_dir/src:$sbph_dir/tests${PYTHONPATH:+:$PYTHONPATH}"
if [ "$#" -eq 0 ]; then set -- discover -s "$sbph_dir/tests"; fi
exec "$sbph_dir/.venv/bin/python" -m unittest "$@"
