# Unit 9 native handled shots and portable handoff

Current readiness is recorded in [current-state.md](current-state.md). The October 18 results below are historical; the harmony framework repairs stale existing shot builds. Select the complete run once with `./unit9 motion-use full-run-ti36vxyf`; `motion-use default` restores the partial default. An explicit `--run NAME` still overrides one invocation.

Unit 9's existing native full-film project is registered in
`examples/unit-9-motion.json`. Its effective edit snapshot lives in
`examples/unit-9-motion/data/edit.json`. The registration resolves all 57 shot
windows from the full-film `edit.json` and saved `film.meta` cut cues. It retains
7,194 body frames at 30 fps, 1920 × 1080, the original recording, and 12-frame
handles at each edge.

New media and packages go to **`output/unit-9-motion-handled/` in this toolkit**,
or the selected named run beneath that directory.
That ignored directory is outside the original film tree. The legacy config,
SVG shots, full native movie, proof, timelines, source project, and audio remain
in their existing locations. The new configuration uses generic production
checks; it does not apply the legacy SVG-specific verification profile.

## Short commands

```sh
./unit9 motion-register
./unit9 motion-status
./unit9 motion-resume
./unit9 motion-shots --shot 31
```

The native status/resume commands inspect this configuration and its workflow
records without rendering. Native `motion-note`, `motion-notes`, `motion-resolve`,
`motion-reanchor`, `motion-intent`, and `motion-check` use the same configuration.
Bare `./unit9 status` and `resume` retain the legacy SVG target.

All of these routed native commands accept `--run NAME` as their first option to
select an existing run's `production.json`. For the complete run described below:

```sh
./unit9 motion-status --run full-run-ti36vxyf
./unit9 motion-resume --run full-run-ti36vxyf
```

This selection applies only to that invocation. `motion-use NAME` saves a
selection for later invocations. `motion-register` follows the same selection;
only an explicit `--refresh` replaces an existing differing registration.
Selection alone never refreshes registration or relabels media. Stale status and validation
show the changed inventory files and browser/tool/settings fields. The shared
framework still fingerprints all toolkit Python files, so these recovery changes
invalidate older shot receipts. The saved handoff remains independently checkable.

Registration alone starts no render. Running it again with identical inputs
leaves the registered files untouched. The bounded verification shot is **31,
“A glance behind”**, native source frames 3776–3819: 44 body frames plus 12-frame
edge holds at each side, for a 68-frame clip. The shared renderer uses a temporary
source copy so browser metadata caches do not modify Unit 9's sources. For this
registered named-cut project, it isolates the selected scene and rebases its
animation/cut events to local time before rendering, then restores global frame
numbering. This prevents a preceding scene's cached cut frame from entering the
body or held head frames. Arbitrary unregistered frame windows retain their
existing rendering behavior.

The default output folder holds only shot 31, so the full gate, timeline,
assembly, and package commands deliberately reject it as incomplete. The
preserved full-film movie and legacy shot files are not silently adopted as
newly rendered shot evidence.

**An existing complete run.** `output/unit-9-motion-handled/full-run-ti36vxyf/`
holds all 57 handled shots (schema 2, 12-frame handles), `shots.json`, timeline
interchange (`unit-9-motion-human-edit.otio` with 33 derived accent/impact markers),
assembly (`assembly.mp4`, 7,194 frames), passing `check` and `conform` verification
(`assembly-verification.json`, 171 boundary/midpoint samples, max RGB error 0.286),
and a verified collected handoff (`handoffs/H615c266ae878`, 58 media files).
Its `production.json` matches `examples/unit-9-motion.json` (including
`verification.conform_first_frame_offset: 1`) except for absolute `root` and `output` paths.
The finishing sequence is automated via `./scripts/unit9-finish.sh [RUN]`:

```sh
./scripts/unit9-finish.sh full-run-ti36vxyf
```

After intentionally accepting the current source/toolchain for a new render,
`./unit9 motion-shots --run full-run-ti36vxyf --resume` renders the required shots
and can continue after interruption. It reuses only current records whose ranges,
hashes, and probed media pass the shared gate. It will rerender the entire set if
the build identity changed. Omitting `--run` uses the explicitly saved active run, or the partial default when no run is selected.
Plain `motion-shots` without `--resume` always requests fresh selected shots.

`conform` additionally needs a separate `reference` movie in the configuration.

A complete render already exists (see below). To make a new one in the default
output, run these explicitly:

```sh
./unit9 motion-shots --run default
./unit9 motion-validate --run default
./unit9 motion-timeline --run default
./unit9 motion-assemble --run default
./unit9 motion-package --run default
```

The first command renders the complete film as separate handled shots. It has
not been run against the default output. Packaging collects all handled clips, the
original recording, relative-reference OTIO, and editorial context into a new
folder under `output/unit-9-motion-handled/handoffs/`. Check or compare that
folder using `./sbph package-check /path/to/handoff` and
`./sbph compare-return /path/to/handoff --returned /path/to/return.otio`.
See [portable editorial workflow](portable-editorial.md) for package contents
and comparison limits.

## Saved timing changes

The configuration records the native plan, cue metadata, render specification,
and original audio identities. Its registered edit and explicit source windows
must match that saved native plan. A source change that affects these identities
blocks rendering and production export, with a stale-registration message.
After reviewing intended native cue changes:

```sh
./unit9 motion-register --refresh
```

This follows the saved active run; `--run NAME` overrides it and `--run default`
targets the default. A selected named run receives the refreshed registration
and source-window mapping while retaining its other configuration, including
root, output, and delivery. Refresh also keeps the default registration and shared
edit snapshot together; other named runs can become stale when shared timing
changes. The prior selected configuration is retained for recovery.

It preserves native sources and existing media and starts no render. Old shot records fail
the current fingerprint; rebuild the required complete shot set before export.
Keep the original recording's duration and bytes. Audio replacement or shortened
native timelines are rejected rather than silently registered.

The generated edit snapshot retains native scene actions, narration anchors,
animation information, and selected accents for handoff context. The native
plan has no top-level `events` array, so timeline export and packaging derive
markers from it: each selected accent becomes a green marker named
`<shot> / <meaning>`, and each physical impact (pulse) not already at an accent
frame becomes a cyan `<shot> / impact` marker. Animation start/end events are
deliberately left out (generic names like `a-0`, 83 of them). An edit that
defines `events` itself is used as written. The legacy SVG timeline's markers
remain in the original timeline.

## Verification scope

One real native shot was rendered, decoded, and checked for frame counts, rate,
dimensions, color tags, file identity, current build fingerprint, and held edges.
The original full-film frame 3776 still shows the preceding scene. Its first
visible operator frame is 3777; the isolated first body pose was compared with
that frame. The middle and last body poses were compared at 3798 and 3819.
Mean RGB errors at 480 × 270 were 0.704, 0.136, and 0.109 out of 255. Both held
edges differ by less than 0.011 mean RGB levels after decoding. Sixteen focused
registration/render contract tests passed. The full 57-shot run historically passed
timeline export, assembly, check, conform, and packaging; native editor import/export
in Resolve remains the pending acceptance gate.
