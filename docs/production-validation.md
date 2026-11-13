# Production validation — build schema 2

`./sbph validate /path/to/production.json` is a read-only production gate.
`timeline`, `assemble`, `check`, and `conform` use that same gate before writing
outputs or decoding review pictures. It requires a complete, current shot set.

## What the gate establishes

- The configured edit has the required shot fields and in-range story events.
- The manifest uses build schema 2 and matches the current build fingerprint.
- Every editorial shot is present, with no extra shots or mixed fingerprints.
- Body lengths, timeline starts, source starts, handles, total frames, and rates
  agree with the edit and configuration.
- Each local clip exists and matches its SHA-256. Its actual video frame count,
  frame rate, width, and height match the record.
- The source audio has a verifiable duration long enough for the edit.

These checks do not establish human timing acceptance, native Resolve import,
full-stream decoding, or the creative correctness of the picture.

## Recovery and output preservation

`shots --resume` applies the same per-shot record/media checks before reusing a
clip, including a second hash check after media probing. It does not trust
existence or a matching source fingerprint alone. Current
clips are left untouched; missing, corrupt, malformed-range, or unverifiable clips
are rendered. A different schema, source inventory, edit, or renderer prevents
reuse. Plain `shots` continues to render fresh selected shots. An interrupted
build retains each completed shot's manifest record for the next resume.

Shared SVG shot rendering, shared proof generation, and assembly write temporary
candidates beside their destination and validate before promotion. Shot movies
and manifests, and proof movies and receipts, are staged as pairs with rollback
on caught replacement failures or cancellation. This is recovery from handled
process errors; it is not a filesystem transaction across a power loss or forced
process kill.

Known original input paths are checked against managed output paths. Source identity
is rechecked after staging receipts, before replacement. Scratch cleanup reports
any retained work without masking the original failure or failing a completed
save. Recovery storage and its mapping are prepared beside final outputs before
the previous delivery is detached, so an incomplete rollback needs no additional
disk allocation to preserve its surviving backups.

Standalone `motion-proof` and `motion-film` also stage complete delivery sets.
The proof promotes its native movie, comparison movie, receipt, source samples,
and optional retained frame directory together. A successful build without
`--keep-frames` removes an older retained sequence within that same rollback
operation. Failed proof attempts report a unique diagnostic staging directory;
retrying does not erase it or the previous delivered version.

The full-film builder publishes the movie, verification, effective edit, source
samples, and exact decoded storyboard page set together. Obsolete pages are
removed only during successful promotion. Its verified chunks, per-chunk QA,
and cache receipt are a separate resumable cache: each completed section is
saved to that cache as a recoverable set before proceeding. A later failure
does not discard verified sections or publish partial delivery artifacts.
Unverified full-film scratch is cleaned up. Both builders typecheck and render
source copies, and reject overlapping source/output folders before copying.

Full-film cache schema 2 binds current source/rendering-tool/browser identity,
render settings, scene seeds and saved metadata, and chunk size. Known computed
event cache fields are excluded from identity. Reuse checks ranges, hashes, media metadata,
native cut audit, and exact source-frame evidence. Older cache files stay on
disk but are not silently adopted as new evidence. Failed restoration reports
a `.promotion-recovery-*` directory beside the outputs with surviving backups
and a recovery mapping, outside temporary render work.

`status` and a stale `validate` error list added, removed, and changed inventory
members. Build-specification details identify browser paths/hashes, tool versions,
and settings. Missing historical inventories are reported as unavailable evidence.
These explanations do not waive freshness requirements or relabel older media.

The generic `check` command adds delivery metadata, full-video decoding, audio
comparison, and generated all-shot contact sheets after this gate. Optional
picture comparisons and creative profiles are documented in
[generic verification](generic-verification.md).

## Build identity

New shot manifests and SVG proof sidecars use `schemaVersion: 2`. Their inventory
always includes the actual configured driver, edit, and original audio, even
when those files are outside the default source patterns. Defaults recursively
include files in `src/`, `assets/`, and `data/`. A custom `source_globs` list
replaces those defaults. Missing explicitly declared sources fail the build.

Declare other dependencies using `source_files`, relative to the film root or
as absolute paths. This includes external fonts and helper modules, and files
read dynamically by a driver. For example:

```json
{
  "source_globs": ["src/**/*", "assets/**/*", "data/**/*"],
  "source_files": ["../shared/character.cjs", "/path/to/font.ttf"]
}
```

The fingerprint also includes normalized render settings (including handles,
dimensions, and rate), shared Python/render source, dependency manifests and
locks, resolved Node/FFmpeg/ffprobe executable hashes and versions, Python
package versions, installed Node package metadata, Sharp's native library
versions, and relevant Node module-resolution settings. Output locations,
delivery/reference roles, proof-window defaults, and verification settings do
not change handled picture identity. Changing configuration or the edit
after loading a project requires reloading it before continuing.

This identifies configured inputs and the recorded toolchain. It does not
discover arbitrary undeclared file reads or attest every installed dependency
byte. Declare external inputs explicitly. Dependency installations are expected
to follow the lock files.

Managed planning records in `.sbph/` are excluded from source globs, so notes,
checkpoint history, and optional intent overrides do not invalidate production
shots. Drafts have their own identity, including planning text actually used.
See [the creative workflow](creative-workflow.md).

## Audio checks

Delivery audio comparison enforces decoded sample counts. Lossless deliveries
require equal counts; AAC permits at most one 1024-sample packet at the encoded
sample rate. Correlation and energetic alignment windows scale to the actual
editorial audio window. The full source may be longer than the edit: assembly,
delivery checks, and conform use source frames `[0, frames)`, and a proof uses its
selected frame interval. Only the comparison source is cropped; delivered audio
is decoded in full so an unintended tail remains detectable. Reports retain the
original recording's hash and record the compared frame/sample window.
The comparison checks that the original recording's hash remains stable during
decoding. Conform also rechecks the current build identity before saving its
report, preserving the previous report when checking fails.
Offset windows avoid the codec-padding boundary. Silence is
reported as silence with unmeasurable temporal alignment, rather than a numeric
correlation claim. Non-finite audio and recordings too short to measure fail.

Audio-onset markers are placed from their canonical `seconds` values at export
time, so changing project fps cannot reuse obsolete cue frame numbers. Analysis
still requires the current original-audio hash.

## Motion Canvas baseline and cue identity

Before typechecking or starting a browser, `motion-proof` checks the exact source
and editor-WAV sample counts, crop bounds, and sample equality. It then requires
the baseline MP4 and its adjacent JSON sidecar to agree on source start frame,
length, rate, file hash, and actual media size. The baseline audio duration and
decoded audio must match the verified editor crop. New SVG proof sidecars also
record the original audio hash, dimensions, and build identity.

An original baseline sidecar without an audio hash is usable only after those
actual media/audio checks pass. It is never upgraded or rewritten implicitly.
The baseline picture can remain an earlier creative version for the A/B.

Motion Canvas snapshots include `.meta` timing events and project metadata.
Additions, deletions, or changes during rendering fail before encoding begins;
the inventory is checked again before writing the final proof record. Shared
build and Motion Canvas framework identity are also recorded and checked.
The selected Chromium executable is hashed without launching it and included
in Motion Canvas's build fingerprint.

## Existing Unit 9 package

The first implementation pass preserves the existing film, proofs, shot media,
timelines, manifests, review files, and original WAV. Those shot manifests predate
schema 2. The new gate deliberately rejects them with a rebuild instruction;
it does not claim that their existing output is corrupt or rewrite evidence to
make an old build appear freshly verified.

Do not run a full rebuild simply to clear that message while preserving the
current package. A future intentional rebuild will generate schema-2 evidence.
Successful rendering/export commands retain their existing output destinations.

## Focused checks

The regression fixtures create media only in temporary directories. They cover
stale/legacy/missing/mixed shot sets, range and media mismatches, build identity,
short or shifted audio, exact WAV windows, wrong baseline intervals, cue metadata
changes, and a real six-frame/two-shot SVG → OTIO → FFmpeg assembly.

Run only the relevant test module when changing one boundary:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_production_validation.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p test_audio_comparison.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_motion_*.py'
```

## Native shot backend

`renderer: motion-canvas` selects explicit registered source projects/windows.
Its fingerprint includes source folders and cue metadata, the shared native
launcher, browser identity, and normal runtime/edit/audio/settings identity.
The manifest identifies the native renderer instead of requiring an SVG driver.
Frame counts, handles, hashes, dimensions, and audio pass the same downstream
gate. Default SVG builds retain their driver identity field. See
[portable editorial workflow](portable-editorial.md).

## Harmony source/output and recovery additions

Source enumeration is shared by fingerprints and output protection. Broad globs omit generated output, temporary work and locks; a glob aimed directly at output is rejected. Use `source_files` for deliberate originals within an output tree: they remain protected from replacement. Generated shot filenames are checked for collisions, including case-insensitive portability. Relative `deliver_root` uses the film root, matching other project paths.

A local writer lock protects each resolved output. Its sibling `.OUTPUT.sbph-build-lock/owner.json` records PID/command; other writers fail immediately. Nested same-thread production calls share ownership. There is no automatic stale-lock removal.

`shots --repair-manifest` is explicit: malformed original bytes are retained under a unique `shots.damaged-*.json`, and unverifiable progress is rebuilt rather than adopted. Inspect `status`, the diagnostic path, and the original error before choosing recovery.
