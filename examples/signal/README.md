# The Signal — a complete second-film example

A signal reaches a broken track. A link closes, and the signal reaches the
waiting receiver. This wordless, four-second film demonstrates the shared
production path without Unit 9, downloaded art, font files, a browser, or an
external service.

The picture is 320 × 180 at 24 fps: three shots, 96 editorial frames, and four
handle frames at each edge of each shot. The small format keeps iteration fast.
All geometry is ordinary SVG authored in `src/film.cjs`. Python's standard
library generates an original 48 kHz stereo PCM recording from sine tones.

## Build and view

From the toolkit root, after the normal one-time `./scripts/setup.sh` installation:

```sh
./signal build
```

The default `./signal` command also builds. It prepares the audio, renders a
full-film proof, renders handled shots, exports the timeline, assembles the
editorial bodies, checks the delivery, and conforms it against the separate
full-film proof. All media stays inside this example's ignored `audio/` and
`production/` folders.

Open `production/assembly.mp4` to watch. Other useful outputs are:

| File | Purpose |
|---|---|
| `production/proof.mp4` | Independently rendered, full-frame viewing reference. |
| `production/shots/` | Three separate clips, each 40 frames including handles. |
| `production/human-edit.otio` | Three picture clips with source in-point 4; one original WAV; three action markers. |
| `production/human-edit.xml` | XML fallback when the installed adapter is available. |
| `production/shots.json` | Build identity and handled-media records. |
| `production/review/decoded-storyboard-1.jpg` | A decoded midpoint picture from every shot. |
| `production/media-verification.json` | Generic delivery and audio evidence. |
| `production/assembly-verification.json` | First/middle/final shot sample conform against the full-frame proof. |

The conform checks consistency between the handled-shot and full-frame rendering
paths at sampled frames. Both pictures come from the current source. This is a
technical example, not an independently approved artistic reference or native
editor acceptance.

## Individual steps

From the toolkit root:

```sh
./signal prepare
./signal doctor
./signal proof
./signal shots
./signal timeline
./signal assemble
./signal validate
./signal check
./signal conform
```

`./signal analyze` optionally adds librosa onset candidates. It is not needed
to complete this example; the authored action markers are already in the edit.
Preparation is repeatable. It will refuse to replace an existing, different
`audio/source.wav`. Rendering commands intentionally replace their named
example outputs when rerun.

## Copy it to another folder

The film owns all its source material and generated audio. Copy this folder
without its generated `audio/` and `production/` directories, then point its
launcher at the installed toolkit:

```sh
SBPH_HOME=/absolute/path/to/saul-bass-production-house ./make build
```

No special Node module path or font cache is required. The scene driver uses
only Node built-ins; rasterization uses the toolkit's installed Sharp package.

## Edit and resume

- Change story actions and frame ranges in `data/edit.json`.
- Change the palette there, and the geometry/choreography in `src/film.cjs`.
- Change generated sound in `scripts/prepare.py`, preserving the existing audio
  before intentionally replacing it.
- `frame(n)` selects a shot from the full editorial timeline. `shotFrame(id,n)`
  receives a local frame, including negative handle frames, and clamps poses
  inside that same shot. The editorial body is identical through either path.
- After source changes, rerun `./signal build` to refresh both rendering paths
  and their evidence together.

For a new project, keep the framework reference outside the film, declare any
new external inputs, and preserve the existing film as its own completed example.

## Plan, review, and pause

The example also exercises the creative workflow without a full build:

```sh
./signal status
./signal prepare
./signal intent --shot bridge --goal "Connect the track" --change "The crossing becomes possible"
./signal animatic --render-stills
./signal note --shot bridge --kind t --text "Give this a longer hold"
./signal resume --note N1
./signal revision --note N1
```

Those commands are run from the toolkit root; use `./make` in a copied film
folder. Bare `status` and `resume` are read-only. Notes and intent stay in
`.sbph/`; new draft movies and sidecars go in `production/drafts/`. Existing
proof, assembly, and handled clips are not replaced by a draft. Labels sit above
the picture, so a 320 × 180 picture has a 320 × 232 draft movie.

See [notes, intent, animatics, and revision previews](../../docs/creative-workflow.md)
for timecodes, checkpoint history, reanchoring notes, and the draft's evidence
limits. In a copied project, find that guide in the installed toolkit.
# Optional native animation and collected handoff

`./signal motion-shots` (from the toolkit root) selects `production-motion.json`
and three self-contained Motion Canvas scenes. It uses installed headless
Chromium and writes to `production-motion/`; the existing SVG example remains
in `production/`. Use `motion-timeline`, `motion-assemble`, `motion-validate`,
and `motion-package` for the corresponding native workflow. `./signal package`
collects the SVG build. See [portable editorial commands](../../docs/portable-editorial.md)
for moving either package and comparing an editor's OTIO return.

