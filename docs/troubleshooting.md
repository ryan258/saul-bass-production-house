# Troubleshooting

Every failure is one line starting `sbph:` (exit 1). Find yours by its text. Most are the gate protecting you; the fix is usually "rebuild", not "work around".

## Setup and environment

| Message contains | Cause → fix |
|---|---|
| `Run scripts/setup.sh once` | no `.venv` → `./scripts/setup.sh` (needs `uv`, Python 3.11–3.13, Node) |
| `ffmpeg is missing` / `ffprobe` / `node` | not on `PATH` → install, or set `SBPH_FFMPEG`, `SBPH_FFPROBE`, `SBPH_NODE` |
| `No Chromium found` | Motion Canvas only → install Chrome/Chromium, or `SBPH_CHROMIUM=/path/to/binary`. Nothing is auto-downloaded |
| `Cannot find module 'sharp'` | Node packages missing → `npm ci --ignore-scripts` (or set `SBPH_NODE_MODULES`) |
| `Raster contract mismatch` | your SVG's `width`/`height` ≠ the edit's → make them equal |
| `Port 9139 is already in use` | another `motion-editor` or render is running → stop it; the port is fixed |

## Edit and project errors

| Message contains | Cause → fix |
|---|---|
| `Timeline has a gap or overlapping shots` / `Edit must cover the whole timeline` | scenes must tile `0 … frames` exactly; first `start` is 0, last `end` is `frames` |
| `H.264 delivery requires even width and height` | use even dimensions |
| `Unsafe shot ID` / `Unsafe shot kind` | only letters, digits, `-`, `_` |
| `Shot IDs must be unique` | duplicate `id` |
| `Source audio is missing` | `audio` path wrong (relative to `root`), or audio not generated yet |
| `Source audio is shorter than the editorial timeline` | recording must last ≥ `frames / fps` |
| `missing required field 'x'` | a required key is absent from the edit or config |
| `Declared source is missing` | a `source_files` entry doesn't exist |

## Build and gate errors

| Message contains | Cause → fix |
|---|---|
| `Shot manifest is missing; render shots first` | → `sbph shots` |
| `Stale shot build` | the error and `status` list changed inventory files and browser/tool/settings fields. Review those changes, then use `sbph shots /path/to/production.json --resume`; a new identity requires fresh shots, while later retries reuse verified clips |
| `Shot set is incomplete or contains unexpected shots` | you rebuilt with `--shot` after a source change, or added/removed a scene → render every shot |
| `Legacy shot manifest: rebuild all shots with build schema 2` | built before schema 2 → rebuild deliberately; old files aren't relabeled. (Unit 9's original SVG build is in this state on purpose) |
| `Missing or changed media` | a clip was edited or deleted after the build → rebuild that build |
| `Sources changed during render` | source/tool identity changed while `shots` ran; the candidate is rejected and the previous clip/manifest are preserved. Review changes before retrying |
| `Project configuration or edit changed; reload the project` | config/edit edited while a command ran → re-run |
| `Shot manifest does not match the current edit or renderer` | switched `renderer` or driver after building → rebuild |
| `Motion registration is stale` | Unit 9: native cues/plan/audio changed → review, then `./unit9 motion-register --refresh` |
| `Keep isolated Motion shot sources in a separate folder` | a `motion_shots` project sits at the film root or inside `output` → move it to its own folder |
| `Shared Motion projects require explicit startFrame windows` | several shots point at one `project.ts` as plain strings → use `{"project":…, "startFrame":…}` for each |
| `Audio changed; rerun analysis` | `audio-cues.json` is for different audio → `sbph analyze`, then `timeline` |

`shots --resume` skips only clips that pass the production record/media gate.
It is safe to retry an interrupted current build; an unused source-audio tail is
allowed and final audio checks compare only the editorial window. Delivered
extra audio beyond codec-padding tolerance remains an error.

Use `./unit9 motion-status --run full-run-ti36vxyf` to inspect the existing native
complete run. `--run` must be first after the native command and names an existing
native run folder. Omitting it retains the default partial output. No status or
resume command launches a browser or begins rendering.

## Verification errors

| Message contains | Cause → fix |
|---|---|
| `Delivery movie is missing` | → `sbph assemble`, or pass `--delivery` / set `"delivery"` |
| `Delivery frame count or rate differs from edit` | the movie isn't this edit → reassemble |
| `Audio correlation failed` / `Audio alignment failed` | delivery audio ≠ source, or shifted > 1 sample at 16 kHz → find what re-encoded or trimmed it |
| `Conform requires an explicit reference movie` | set `"reference"` or `--reference`; for the SVG driver, `sbph proof` makes `production/proof.mp4` to use |
| `Conform reference must be a separate movie from the assembly` | reference can't be the assembly (or a link to it) |
| `Assembly picture differs from reference at frame N` | the two render paths disagree at that frame → check your driver's `frame()` vs `shotFrame()` |
| `unverified_media … relink` (compare-return) | returned OTIO sits outside the package → export it into the package folder or relink |
| `Media identity is unknown, conflicting, or ambiguous` (compare-return) | clip media bytes match no collected file; names are never trusted |

## Workflow records

| Message contains | Cause → fix |
|---|---|
| `Another workflow edit holds …/.write.lock` | a command is running, or crashed. Confirm nothing is running, then delete that one file |
| `Unsupported or malformed workflow record` | `.sbph/*.json` was hand-edited wrongly; reads fail loudly rather than drop your notes → fix the JSON |
| `Time must fall inside the selected shot` | `--at` is **global** time; it must land within `--shot` |
| `Use seconds, MM:SS, HH:MM:SS:FF, or frames such as 48f` | bad time; timecode frames must be `< fps` |
| `Note anchor needs review: orphaned / rate_changed / outside_shot` | shot removed, fps changed, or frame trimmed away → `sbph reanchor --note N1 --shot ID --at …` |
| `Revision previews are limited to 30 seconds` | add `--start S --duration D` |
| `Handoff destination already exists` / `Report destination already exists` | by design, never overwritten → choose a new path |

## Diagnose first

```sh
sbph doctor production.json                          # tools found? versions?
sbph status production.json                          # build state + next action, read-only
sbph status production.json --json | python3 -m json.tool | less    # full detail incl. errors[]
sbph validate production.json                        # the exact reason a build is rejected
```
