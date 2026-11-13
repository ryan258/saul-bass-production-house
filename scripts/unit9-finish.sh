#!/bin/sh
# Finish an already-rendered native run; never renders shots or edits source film files.
set -eu
sbph_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$sbph_dir/src${PYTHONPATH:+:$PYTHONPATH}"
if [ "$#" -gt 1 ]; then echo "unit9: use motion-finish [RUN]" >&2; exit 1; fi
if [ "$#" -eq 1 ]; then
  config=$("$sbph_dir/.venv/bin/python" -m sbph.unit9_run config "$sbph_dir" "$1")
else
  config=$("$sbph_dir/.venv/bin/python" -m sbph.unit9_run config "$sbph_dir")
fi
reference=${UNIT9_REFERENCE:-"$sbph_dir/../nonsense/unit-9/svg-film-v01/production/motion-canvas-full/unit-9-motion-canvas-v01.mp4"}
"$sbph_dir/sbph" validate "$config"
"$sbph_dir/sbph" timeline "$config"
"$sbph_dir/sbph" assemble "$config"
"$sbph_dir/sbph" check "$config"
"$sbph_dir/sbph" conform "$config" --reference "$reference"
package_json=$("$sbph_dir/sbph" package "$config" --json)
package_path=$(printf '%s\n' "$package_json" | "$sbph_dir/.venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["package"])')
"$sbph_dir/sbph" package-check "$package_path"
printf '%s\n' "Handoff ready: $package_path" 'Human screening, first-cut review, and Resolve acceptance remain explicit separate steps.'
