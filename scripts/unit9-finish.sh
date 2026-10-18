#!/bin/sh
# Conform, package, and package-check the Unit 9 native run (default: full-run-ti36vxyf).
# Run after: ./unit9 motion-shots --run R --resume && motion-validate/timeline/assemble/check.
set -eu
sbph_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
run=${1:-full-run-ti36vxyf}
base="$sbph_dir/output/unit-9-motion-handled/$run"
reference=${UNIT9_REFERENCE:-"$HOME/Projects/nonsense/unit-9/svg-film-v01/production/motion-canvas-full/unit-9-motion-canvas-v01.mp4"}
"$sbph_dir/sbph" conform "$base/production.json" --reference "$reference"
"$sbph_dir/unit9" motion-package --run "$run"
newest=$(ls -t "$base/handoffs" | head -1)
"$sbph_dir/sbph" package-check "$base/handoffs/$newest"
echo "Handoff ready: $base/handoffs/$newest"
