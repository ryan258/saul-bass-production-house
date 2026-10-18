# Saul Bass Production House

A shared, local production toolkit for graphic films: measure the recording, render individual animated shots, build an editable timeline, and leave the final rhythm to a human editor.

The first working project is **UNIT 9**. Its artwork, story, audio, and scene code live in `../nonsense/unit-9/svg-film-v01`. This project owns the reusable production work. Earlier Big Tex, Flight 134, and Kitchen Chefs builds remain intact.

**The Signal** is the self-contained second example: a four-second, three-shot
film at 24 fps. It generates its own audio and uses plain SVG shapes, with no
Unit 9 files, fonts, browser, or external media. Run `./signal build` after setup.
See [the complete example](examples/signal/README.md).

For the review-and-resume loop, use `./signal status`, `./signal resume`,
`./signal animatic`, and `./signal revision --shot bridge`. Timecoded notes use
short IDs such as `N1`; optional intent records a shot's goal and change without
rewriting its edit. Drafts are marked and stored separately from deliveries.
See [the creative workflow](docs/creative-workflow.md).

## What is working

- **librosa 1.0.0** measures onsets and beats. Candidate accents are retained as data and timeline markers; it never decides that every detected beat deserves a cut.
- **ffmpeg-python 0.2.0** builds encoding and assembly graphs against the installed FFmpeg. The framework streams SVG rasters into it and verifies frame counts.
- **OpenTimelineIO 0.18.1** creates real clip, track, source-range, and marker objects and serializes `.otio`. The community FCP adapter supplies a legacy XML fallback.
- **Sharp 0.35.5 / librsvg** rasterizes the SVG picture, including embedded raster props. WebP assets are decoded and transported losslessly as PNG inside standalone SVG frames.
- **MoviePy 2.2.1** is installed and pinned as an optional Python composition tool. The current encoding and assembly paths use ffmpeg-python; MoviePy is not another mandatory layer in every render.
- **Motion Canvas 3.17.2** supplies native vector animation, signals, easing, a visual editor and named audio timing events. The Unit 9 shutdown proof uses this backend, alongside the original SVG proof. [Workflow and limits](docs/motion-canvas.md).

No audio or art is sent to a service. The initial installation downloads code packages. Rebuilds use local files and binaries.

## Short commands

The environment is already prepared on this machine. From this folder:

```sh
./unit9 doctor
./unit9 proof
./unit9 motion-proof
./unit9 motion-editor
./unit9 motion-film
./unit9 motion-film-editor
./unit9 analyze
./unit9 shots
./unit9 timeline
./unit9 assemble
./unit9 conform
./unit9 check
```

`shots` renders every shot with handles. A bounded iteration can use `./unit9 shots --shot 10`; refresh all shots after changing shared artwork or scene code before exporting a complete timeline. Source inventories invalidate stale partial builds; the exporter rejects mixed versions. `timeline` creates the OTIO and XML handoff without rendering again. `assemble` builds a review movie from the editorial bodies, excluding handles. `conform` compares the assembly to an explicitly selected full-frame reference at the start, midpoint, and end of every shot. `check` verifies the selected delivery, audio alignment, handled media, and decoded all-shot contact sheets. Unit 9's extra creative checks use an explicit profile.

Use `shots --resume` to continue an interrupted build. It reuses only clips whose
current build identity, record, ranges, SHA-256, frame count, rate, and dimensions
pass the shared shot gate. Missing or invalid clips are rendered; a changed build
identity requires fresh shots. Plain `shots` and `shots --shot ID` still request
fresh renders. Shared SVG shots, proofs, and assembly stage their outputs before
replacement; shot manifests and proof receipts roll back with their movies on
caught promotion failures. Source recordings may contain an unused tail: delivery
and conform audio checks compare the source-zero editorial window, and proofs
compare their selected interval, while retaining the original recording's hash.

`./unit9 validate` runs the shared production gate without writing outputs.
Assembly, timeline export, delivery checks, and conform now require the same
current shot set, build fingerprint, ranges, media hashes, and media metadata.
New renders use build schema 2. **The preserved Unit 9 shot manifest predates
that schema, so these commands now stop with a rebuild instruction.** Its
existing movies and timeline remain available. No automatic migration or
full-film rebuild was performed. See [validation and compatibility](docs/production-validation.md).

For another film:

```sh
./sbph doctor /absolute/path/to/production.json
./sbph shots /absolute/path/to/production.json
./sbph timeline /absolute/path/to/production.json
```

The actual project file is the source of paths. Production media belongs to its
film. The Signal generates its small demonstration media in ignored directories
inside its own example folder.

Generic `check` uses the configured `delivery`, the legacy explicit `master`,
or the assembled movie. It needs no pre-existing review files or geometry.
`conform` requires a separate configured `reference` (or legacy `master`), and
refuses to compare the assembly with itself. See [generic verification and
artifact roles](docs/generic-verification.md).

`motion-proof` rebuilds the 15-second Unit 9 shutdown comparison. It produces the new 1080p movie, a labeled A/B movie, and verification records while preserving the original proof. `motion-editor` starts the local Motion Canvas editor at `http://127.0.0.1:9139/`; stop it with Ctrl-C. Both pictures use the same audio track. The new source is in the film's `motion-canvas/shutdown-proof-v01/` folder.

`motion-film` rebuilds the full 239.8-second Unit 9 film using native Motion Canvas scenes. It renders resumable 600-frame sections and retains hashed section media for recovery. `motion-film-editor` opens the full narration and action timing project. The full source is in `motion-canvas/full-film-v01/`; the movie and decoded review sheets are in `production/motion-canvas-full/`. The original SVG film and shutdown A/B remain available.

Both standalone native builders now prepare complete delivery sets before
replacement, including their receipts and review images. Caught failures or
cancellation restore the previous set. They render source copies so native
metadata caches do not touch original sources. The full-film builder preserves
validated chunk progress separately and rechecks media and source-frame evidence
before reuse. Its new cache schema also binds browser/tool identity and chunk
size; older cache receipts require a fresh render. See [native recovery details](docs/motion-canvas.md).

## Working in Resolve

Native orientation is available with `./unit9 motion-status` and
`./unit9 motion-resume`. To inspect the existing complete run explicitly:

```sh
./unit9 motion-status --run full-run-ti36vxyf
./unit9 motion-resume --run full-run-ti36vxyf
```

`--run NAME` must be the first option after the native command. It also works
with `motion-shots`, `motion-validate`, `motion-check`, and the other native
handoff/planning commands. It selects only that invocation; default commands
continue to use their existing output folder. Status lists changed inventory
files and browser/tool/settings fields without launching a browser or rendering.

Unit 9's native project also has a separate handled-shot registration:
`./unit9 motion-register` checks/creates its saved timing snapshot, and
`./unit9 motion-shots --shot 31` renders one bounded shot to
`output/unit-9-motion-handled/`. The original film tree stays intact. See
[Unit 9 native handoff](docs/unit9-motion-handoff.md) for the complete workflow,
refresh guard, and verification status (shot 31 in the default output; a
complete 57-shot run in `output/unit-9-motion-handled/full-run-ti36vxyf/`
that has been rendered, validated, assembled, conformed against viewing
reference, and packaged into a verified handoff).

For a collected handoff that can move with its media, use `./signal package` or
`./sbph package /path/to/production.json`. Check it with
`./sbph package-check /path/to/handoff`, then compare a human OTIO return with
`./sbph compare-return /path/to/handoff --returned /path/to/return.otio`.
Motion Canvas handled shots use the same production gate and timeline path;
`./signal motion-shots` demonstrates them in separate output. See the
[portable editorial workflow](docs/portable-editorial.md) for configuration,
short commands, source-window/hold semantics, and comparison limits.

Import `../nonsense/unit-9/svg-film-v01/production/unit-9-human-edit.otio` using **File → Import → Timeline**. The media references point to the individual shot clips and the original WAV. If the folder moves, regenerate the timeline from its current location. The XML beside it is a fallback.

Lock the original audio track before adjusting timing. Use the extra frames at the start and end of each clip to shift cuts or hold a reaction. Some handles intentionally hold an edge pose; the frame generator keeps the same shot active and clamps its normalized action progress rather than borrowing a neighboring scene. Musical candidates and chosen action cues use separate marker colors.

Resolve import has **not** been tested on this host: the app and its scripting SDK were not found in the standard locations. OTIO read/write, frame ranges, and referenced media are checked locally. Native acceptance is a separate evidence step.

## Where to change things

| Change | Owner |
|---|---|
| Story, shot lengths, chosen actions | Film `data/edit.json` |
| Cut-paper art and animated rigs | Film `assets/svg/`, `src/art.cjs`, `src/film.cjs` |
| Source audio | Film's existing audio folder; never rewritten by this toolkit |
| Candidate sound cues | Shared `src/sbph/analyze.py` using librosa |
| Encoding, handled clips, assembly | Shared `src/sbph/media.py` using ffmpeg-python |
| Editable timeline | Shared `src/sbph/timeline.py` using OTIO |
| SVG raster transport | Shared `render/runtime.cjs` using Sharp |
| Native vector animation and audio time events | Film `motion-canvas/`; shared `motion-canvas/` launcher and `src/sbph/motion.py` |
| Final timing judgment | Human editor in Resolve |

The boundary is deliberate: SVG rigs, geometry, and effects are baked within a shot clip. OTIO carries editorial structure; it does not turn the SVG scene graph into editable Fusion nodes.

## Install elsewhere

Python 3.11–3.13, Node, FFmpeg, ffprobe, and uv are required. `requirements.lock` pins the resolved Python environment. `package-lock.json` pins the Node raster and Motion Canvas dependencies. Motion Canvas rendering also needs an installed Chromium browser; `SBPH_CHROMIUM` can select its executable.

```sh
./scripts/setup.sh
```

Setup uses a uv-managed Python 3.12 so `.venv` does not depend on another app's cache. Run the suite with `./scripts/test.sh`. Set `SBPH_PYTHON` to use a different interpreter. `SBPH_FFMPEG`, `SBPH_FFPROBE`, and `SBPH_NODE` override binary lookup. This Mac can use the existing bundled Node modules as a fallback; `npm ci` creates project-local modules on another machine.

New here? Start with the [guide](docs/guide.md), the [roadmap](roadmap.md) (and [v1.0 checklist](docs/v1.md)), then [make your own film](docs/new-film.md), the [cookbook](docs/cookbook.md), and [troubleshooting](docs/troubleshooting.md). See also [the production path](docs/happy-path.md), [Resolve handoff](docs/resolve-handoff.md), [library choices and sources](docs/library-choices.md), and [current evidence](docs/current-state.md).
