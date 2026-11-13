# Cookbook

Recipes for a film at `production.json` (`./signal …` or `./unit9 …` work the same; they just fill in the path). Output shown is real, trimmed.

- [Know where you are](#know-where-you-are)
- [Look at one shot without rebuilding](#look-at-one-shot-without-rebuilding)
- [Run a review loop](#run-a-review-loop)
- [Change a shot and get back to a valid build](#change-a-shot-and-get-back-to-a-valid-build)
- [Put audio onsets on the timeline](#put-audio-onsets-on-the-timeline)
- [Hand off to an editor and read the return](#hand-off-to-an-editor-and-read-the-return)
- [Use Motion Canvas for shots](#use-motion-canvas-for-shots)
- [Script it](#script-it)
- [Move or copy a film](#move-or-copy-a-film)

## Know where you are

```sh
sbph status production.json
```
```
TWO DOTS — 2 shots / 4.00s at 24 fps
Next: Hold the touch
…/sbph revision …/production.json --note N1
Handled build: matches — Source fingerprint and clip hashes checked; ranges and media metadata require validate.
Open notes: 1
```

`status` is read-only and never runs the command it suggests. Build states: `missing` (no manifest), `legacy` (old schema), `stale` (inputs changed), `incomplete` (shots missing), `changed` (a clip's bytes differ), `unverified` (couldn't be read), `matches`. `matches` is hash evidence only; `validate` is the real gate.

## Look at one shot without rebuilding

Two tools, different jobs:

| | `revision` | `shots --shot ID` |
|---|---|---|
| Output | labeled **DRAFT** movie in `production/drafts/` | the real handled clip |
| Speed | seconds, low-res (`--width 160–1280`) | full quality |
| Touches production files | never | replaces that clip; stales the set if sources changed |
| Renderer | SVG driver only | SVG or Motion Canvas |

```sh
sbph revision production.json --shot meet                 # shot + 0.5 s context each side, matching audio
sbph revision production.json --shot meet --before 0.25 --after 0.25
sbph revision production.json --shot meet --start 2 --duration 1.5   # explicit window; max 30 s
sbph animatic production.json --width 320                 # whole film as placeholder cards
sbph animatic production.json --render-stills             # one real frame per shot, held
```

Cards use `scene.storyboard` (a path) when present, else the shot's name, action, and `goal`/`change` intent. Drafts are never promoted to production.

## Run a review loop

`--at` is **global** time inside the shot. Accepted forms: `2.75` (seconds), `0:02.75`, `00:00:02:18` (frame field < fps), `66f`.

```sh
sbph note     production.json --shot meet --at 2.75 --kind t --text "Hold the touch"
sbph note     production.json --at 1.0 --kind c --text "Too fast"     # shot found from the time
sbph resume   production.json --note N1       # save a checkpoint; status now points at N1
sbph revision production.json --note N1       # preview exactly that spot
sbph resolve  production.json --note N1 --text "Fixed in v3"
sbph reanchor production.json --note N2 --shot drift --at 30f          # moved shot? keep the text, move the anchor
sbph notes    production.json --all
```

Kinds: `t`iming `c`larity `v` continuity `a`ction `s`ound `n`ote. Notes anchor to *shot + local frame*, so retiming a shot moves its notes with it; changing fps or trimming the frame away flags the note instead of guessing. State lives in `.sbph/`; keep it with the film and back it up.

Add intent where it helps, skip it where it doesn't:

```sh
sbph intent production.json --shot meet --goal "Two things become one" --exit-condition "They touch"
```

## Change a shot and get back to a valid build

```
$ sbph validate production.json
sbph: Stale shot build: configuration, sources, or tools changed; refresh all shots
$ sbph shots production.json --shot drift          # rebuilding one shot discards the other records…
$ sbph validate production.json
sbph: Shot set is incomplete or contains unexpected shots; render all required shots
$ sbph shots production.json --shot meet           # …so finish the set
$ sbph validate production.json
Production valid: 2 current shots, ranges, hashes, and source audio.
```

Rule of thumb: while the sources are unchanged, `--shot` is a safe partial refresh (other records are kept). After a source change, rebuild every shot, then `timeline` → `assemble` → `check`.

## Put audio onsets on the timeline

Run `analyze` **before** `timeline`. The OTIO is built from whatever evidence exists at that moment.

```sh
sbph analyze  production.json     # librosa: onset candidates, strongest ~48, ≥ 0.5 s apart
sbph timeline production.json     # red audio-track markers = candidates; green/cyan video markers = your events
```

Candidates are measurements, not cuts. Spoken passages and tempo changes fool beat tracking. Cue positions come from stored seconds, so changing fps later re-places them correctly; changing the audio makes `timeline` demand a fresh `analyze`.

## Hand off to an editor and read the return

```sh
sbph package production.json --out ~/handoffs/twodots-v1   # new folder only; existing paths refused
sbph package-check ~/handoffs/twodots-v1                   # re-run anywhere, after any move
```
```
Portable handoff valid: 4 media files; collected hashes and relative references passed.
```

The folder holds `edit.otio` (relative media refs), the handled clips, the original WAV, `editorial-context.json` (actions, events, notes, intent), `handoff.json` (hashes), and a README. Keep it together. Send the whole folder.

Have the editor export an OTIO **into that folder** (relative references resolve from the file's location), then:

```sh
sbph compare-return ~/handoffs/twodots-v1 --returned ~/handoffs/twodots-v1/return.otio
```
```
Editor return: needs_review / 96 → 96 frames at 24 fps
Original audio placement and bytes: preserved
- meet: edit / {'sourceStart': {'before': 6, 'after': 9}}
```

Statuses: `unchanged`, `needs_review`. It reports timing, source-start (slip), duration, track moves, gaps, markers, disabled clips, handle overruns, and whether the original audio is untouched. Clips are matched by **media hash + shot id**, never by name. Anything it cannot reason about (transitions, retimes, nested stacks, off-frame times) is flagged and `comparisonComplete` goes false. `--json` for a machine report, `--out report.json` to save one. It never applies changes.

Common gotcha: a return exported elsewhere shows `unverified_media … relink`. Move it into the package folder or relink the media.

## Use Motion Canvas for shots

Same pipeline, different frame source. Add to `production.json`, using a separate `output` if you want to keep the SVG build:

```json
{
  "renderer": "motion-canvas",
  "output": "production-motion",
  "motion_shots": {
    "approach": "motion/approach/project.ts",
    "bridge":   "motion/bridge/project.ts"
  }
}
```

Each project folder needs `project.ts`, a scene, `tsconfig.json`, and `env.d.ts`; copy one from [`examples/signal/motion/`](../examples/signal/motion/approach/). A string path renders that project from frame 0. For **one shared project** cut into shots, give every shot a window:

```json
"motion_shots": {
  "opening": {"project": "motion/full/project.ts", "startFrame": 0},
  "answer":  {"project": "motion/full/project.ts", "startFrame": 48}
}
```

```sh
sbph shots production.json --shot approach   # type-checks, then renders in headless Chromium; no downloads
sbph validate production.json && sbph timeline production.json && sbph assemble production.json
sbph motion-editor production.json --motion-project motion/approach/project.ts   # printed local URL; prefers 9139, Ctrl-C to stop
```

Handles are edge-holds of the first and last body frame (they cannot reveal a neighbor). Needs Chromium or Chrome (`SBPH_CHROMIUM` to choose). The source folder is copied to a temp dir for each render, so Motion Canvas's `.meta` caching never edits your files. Sources must sit outside `output`. Details and limits: [portable-editorial.md](portable-editorial.md).

SVG-driver previews (`revision`, `animatic --render-stills`) are refused on Motion configs; render a real shot instead.

## Script it

```sh
sbph status production.json --json | python3 -c \
 "import json,sys; d=json.load(sys.stdin); print(d['build']['status'], d['nextAction']['text'], [n['id'] for n in d['openNotes']])"
# matches Hold the touch ['N1', 'N2']
```

Exit code is `0` on success and `1` with a one-line `sbph: …` on failure (`2` for a bad flag). `--json` works on status, notes, intent, package, compare-return, and draft commands. Gate in CI or a render script:

```sh
sbph shots production.json && sbph validate production.json && sbph timeline production.json && sbph assemble production.json && sbph check production.json
```

## Move or copy a film

A film folder is self-contained. Keep generated folders (`production/`, `audio/` if generated) out of copies and point at the toolkit:

```sh
SBPH_HOME=/path/to/saul-bass-production-house ./make build        # examples/signal pattern
```

After moving a film, re-run `timeline`: OTIO files reference media by absolute path. A collected handoff, by contrast, uses relative paths and survives moving untouched.

Environment overrides: `SBPH_FFMPEG`, `SBPH_FFPROBE`, `SBPH_NODE`, `SBPH_PYTHON` (setup), `SBPH_CHROMIUM`, `SBPH_NODE_MODULES`.

## Resume the complete Unit 9 run with less typing

```sh
./unit9 motion-use full-run-ti36vxyf
./unit9 motion-status
./unit9 motion-preflight
```

Selection is explicit and local; neither status nor preflight renders. After a deliberate shot rebuild, `./unit9 motion-finish` runs the downstream gates and returns the exact package path. Use `motion-use default` to restore the partial output.

After watching the full delivery and exact first cut frames, record your own screening with `motion-screen-record --screened --first-cuts-reviewed --text "Reviewed"`. `motion-evidence` lists saved evidence without implying current verification.
