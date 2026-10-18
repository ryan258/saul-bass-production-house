# Current state — 2026-10-18

## Native proof acceptance — 2026-10-18

Ryan ran `./unit9 motion-proof` locally with the real Chromium renderer.
Typechecking and rendering succeeded: 450 frames at 30 fps, 15 seconds,
1920 × 1080 native delivery and 1920 × 600 labeled comparison. Native rendering
took 13.387 seconds; the recorded render/encode build took 25.377 seconds.
The Vite CJS deprecation warning did not prevent completion.

Thirty-nine bounded follow-up checks passed against the actual outputs:
receipt and movie hashes, current configured source/tool/browser fingerprint,
unchanged native source/cue and baseline identities, media stream/color/audio
metadata, all 12 inspection-frame hashes/dimensions, exact editor-WAV source
window, and identical decoded baseline/native/comparison audio. The receipt is
in the film's `production/motion-canvas/proof.json`; full render work was not
retained, matching the default retention setting.

Ryan then ran the automatic interruption check locally. It sent SIGINT at the
first rendered-frame message; the proof process exited with signal 2 and reported
its unique `.proof-build-17r1j3rg` diagnostic directory. All 37 protected files
(successful delivery/receipt/samples, baseline, original audio, native sources
and cues) remained byte-identical. The inspection-frame file set and default
retention state were unchanged. The diagnostic directory and its source copy
survived. The browser-closed error and KeyboardInterrupt traceback followed the
deliberate interrupt; this is a successful preservation check, not a successful
render. Its log/result and the baseline are saved under `/tmp/`.

Ryan retried with `./unit9 motion-proof`; the real renderer completed without
errors. Native rendering took 13.226 seconds and the recorded build took 27.513
seconds. Forty-two follow-up checks passed: new receipt/media identity and
metadata, all 12 inspection frames, current source/tool/browser identity, exact
audio equality, all 22 original input files unchanged, and the interrupted
attempt's complete diagnostic tree unchanged (19 files). A new receipt was
published, successful retry scratch was removed, and the earlier diagnostic
directory was retained. The retry log/result and comparison snapshots are under
`/tmp/`.

This establishes real native proof generation, preservation during interruption,
and successful retry while retaining earlier diagnostic evidence. Native-editor
acceptance and human screening remain pending. The full-suite result has not
been supplied.

## Full-film checkpoint acceptance — 2026-10-18

Ryan ran the automatic full-film interruption check locally with 600-frame
sections. The first section (frames 0–599) completed, verified, and saved its
schema-2 clip/QA/cache checkpoint. The helper then sent SIGINT; the build exited
with signal 2 while hashing a temporary concat link, before delivery promotion.
All 141 protected existing files remained byte-identical, source/tool identity
was unchanged, and unverified full-film scratch was cleaned up. The previous
completed full-film delivery and the proof diagnostic work were preserved.

Independent follow-up verification confirmed the first section passes the
actual reuse gate (hash, 600-frame media metadata, cut audit, and both selected
source PNGs). Cache schema 2 records exactly chunk `0`; the older unadopted
section files remain on disk. The saved checkpoint hashes and timestamps match
the interruption result. Log/result and a separate resume baseline are under
`/tmp/`, ready to prove reuse of that first section during the next local run.

Ryan resumed with `./unit9 motion-film --chunk-frames 600`. The log explicitly
reports reuse of section 1 and verification of sections 2–12; the build completed
in 317.828 seconds. Fifty-nine follow-up checks passed. Section 1's cache record,
clip and two QA PNG hashes and timestamps are unchanged. All 108 protected input
and proof-evidence files and the earlier 19-file proof diagnostic tree are intact.

The delivered movie verifies at 7,194 frames, 30 fps, 1920 × 1080, 239.8 seconds,
with all 57 native cut frames. All 12 sections pass the reuse gate. The new
receipt's 21 artifact hashes match the movie, effective edit, 14 source samples,
and exact five storyboard pages; its 57 decoded shot samples match the edit.
Decoded delivery PCM independently matches the SVG baseline and the receipt.
Recorded source-to-decoded picture errors cover all 14 samples and peak at
0.8068 RGB mean absolute error (limit 3). Current source/tool/browser identity
matches, successful scratch was removed, and human screening remains explicitly
unrecorded. The detailed result is `/tmp/sbph-native-film-resume-result.json`.

Full-film render/interruption/resumption acceptance has passed. The separate
native handled-shot run in `full-run-ti36vxyf` has now been rendered, validated,
assembled, conformed against the viewing reference, and packaged into a verified handoff.

## Unit 9 native handled run, conform, and handoff acceptance — 2026-10-18

The native handled run `output/unit-9-motion-handled/full-run-ti36vxyf/` was completed, validated, conformed, and packaged:
- **57 handled shots**: Rendered and validated against build schema 2 with 12-frame handles; hashes, ranges, and probed media match.
- **Timeline interchange**: `unit-9-motion-human-edit.otio` exported with 33 timeline markers derived from selected accents and physical impacts via `story_events()` in `validation.py`.
- **Assembly & verification**: `assembly.mp4` assembled (7,194 frames, 239.8s at 30 fps); `check` passed across all 57 cuts.
- **Conform**: Verified against native full-film viewing reference (`unit-9-motion-canvas-v01.mp4`). Using `verification.conform_first_frame_offset: 1` (accounting for the continuous reference cut showing the previous scene on the first frame), 171 boundary and midpoint samples yielded a maximum RGB MAE of 0.286/255 (mean 0.162/255). Audio alignment confirmed with mono correlation 0.999961 and zero sample difference at 16 kHz.
- **Package verification**: Handoff `handoffs/H615c266ae878` (58 media files, relative OTIO, editorial context) passed `package-check`.
- **Automated finish script**: `./scripts/unit9-finish.sh [RUN]` automates conform, packaging, and package-check.

## Final preservation review — 2026-10-18

Recovery directories and their mappings are now prepared beside final outputs
before replacement begins. A failed rollback leaves surviving old bytes outside
disposable render work and reports the recovery path. Cleanup errors report
retained temporary work without masking the original build error or turning a
completed save into a failed build.

Shared and native builders check known original input paths for collisions with
managed outputs.
Shot reuse rechecks media hashes after probing, and source identity is checked
after staging the shot/proof receipt and immediately before promotion. Audio
comparison binds its decoded samples to a stable source hash; conform refuses
to publish evidence when current build sources have changed during checking.
Malformed saved evidence remains inspectable through status/resume commands.

All 137 distinct targeted tests passed across grouped promotion/shared builders,
shot resumption, standalone native proof/full-film preservation, input collision
guards, native shot integration, audio windows/conform, and stale status/launcher
routing. One older failure fixture was corrected to reach the source check after
receipt staging; its 15-test module then passed. These checks use temporary film
trees and tiny media; native browser rendering is substituted. No production
render, browser launch, or full suite was run.

These safeguards cover caught failures and cancellation. Promotion spans several
filesystem operations and does not promise an atomic delivery across a forced
process kill or power loss. Production renders and human/editor acceptance
remain separate from the focused regression checks.

## Standalone native preservation pass — 2026-10-18

`motion-proof` now stages its native movie, comparison, receipt, source samples,
and optional retained frame sequence as one delivery. `motion-film` stages its
movie, verification, effective edit, source samples, and exact storyboard page
set together, including removal of obsolete pages. Both restore previous
artifacts on caught promotion failures or cancellation and render source copies.
Failed proof work is retained at a reported unique diagnostic path; unverified
full-film scratch is cleaned up while verified chunks remain resumable.

Full-film cache schema 2 checks current source, browser/tool, specification and
chunk-size identities plus media metadata, ranges, hashes, cuts and per-section
source-frame evidence. Old cache files remain preserved, with no automatic
adoption. New verification receipts mark human screening as not recorded.
Incomplete rollback reports surviving backups outside temporary render work.

Seventy-five distinct targeted tests passed for this pass: standalone proof and
full-film failure/recovery, native audio and timing contracts, grouped promotion,
shared output preservation, and shot resumption. Tests include tiny real FFmpeg
encoding/mux/audio checks with the native browser renderer substituted. Random
seed/metadata identity and post-promotion cleanup errors have focused coverage.
No production render, browser launch, or full suite was run.

This implementation does not rebuild Unit 9, alter its preserved native or SVG
deliveries, or establish new browser/native-editor/human acceptance.

## Recovery implementation pass

The shared production path now stages SVG shots, proofs, and assembly before
replacement; paired shot manifests/proof receipts roll back on caught promotion
failures. `shots --resume` verifies current record ranges, source identity, hashes,
frame counts, rates, and dimensions before reusing clips. Plain `shots` still
requests fresh rendering. Stale status and validation errors identify changed
files and nested browser/tool/settings fields. Native `motion-status` and
`motion-resume` support explicit `--run NAME` selection of an existing run.

Delivery/conform audio comparisons use the source-zero editorial window, and
proof comparisons use their selected frame interval. The original recording's
hash and source window are recorded; delivered audio is decoded in full so an
unintended tail is still detected. Original audio is never cropped on disk.

The complete native run below remains preserved and stale against current
framework/browser identities. This implementation does not rebuild it, relabel
its receipts, or establish new native-editor/human acceptance. The documented
earlier successful validations are historical. See [recovery and validation](production-validation.md).

This pass passed 86 distinct targeted tests, including temporary real SVG
render/assembly, copied Signal end-to-end, audio-window/conform, failure and
cancellation preservation, resume/reuse, stale diagnostics, and native launcher
checks. Browser rendering and the full suite were not run. Native movie/editor
acceptance remains separate.

## Unit 9 native handled-shot registration

All 57 native cut windows are registered separately in
`examples/unit-9-motion.json`, with a saved effective edit and a source/audio
identity guard. New output belongs to the toolkit's ignored
`output/unit-9-motion-handled/`, outside the original film tree. Shot 31 is
verified at 1920 × 1080, 30 fps: 44 body frames plus 12 held frames at each edge.
Registered renders isolate one native scene in a temporary source copy, avoiding
the preceding scene visible at the full film's saved cut boundary. Sixteen
focused tests passed. All 376 existing Unit 9 baseline files remain byte-identical
(as recorded when that pass ran; not re-measured since).

A complete 57-shot native render also exists at
`output/unit-9-motion-handled/full-run-ti36vxyf/`: build schema 2, 12-frame
handles, and a collected handoff folder (`handoffs/H270a417f925c`, 58 media
files). On 2026-10-17 `./sbph validate` on its `production.json` passed (57
current shots, ranges, hashes, source audio) and `package-check` passed on the
handoff. Its configuration is identical to `examples/unit-9-motion.json` except
for absolute root and output paths. Its collected handoff includes `edit.otio`,
but it has no separate timeline export/verification receipt, assembly,
`check`, or `conform` evidence, and no human screening. The default
`output/unit-9-motion-handled/` still holds only shot 31, so the short commands
(`./unit9 motion-validate`, `motion-timeline`, ...) still refuse that folder as
incomplete. See [Unit 9 native handoff](unit9-motion-handoff.md).

## Portable editorial pass

Motion Canvas shot bodies now use explicit isolated projects or shared-project
frame windows, edge-hold handles, and the shared production validation gate.
The Signal includes an optional three-shot native example with separate output.
Collected handoff folders contain relative OTIO references, handled media, the
original recording, notes/intent, and integrity hashes. A relocated folder can
be checked without its source project. Read-only editor-return comparison
reports timing/media/structure changes and unsupported constructs.

Unit 9 now has a separate registration for all 57 native cut windows. Shot 31
is rendered in the default output; a full 57-shot render and handoff exist in
`full-run-ti36vxyf/` but are not yet assembled, checked, or conformed. See
[Unit 9 native handoff](unit9-motion-handoff.md).
Existing Unit 9 movies, shots, timeline, and evidence remain preserved. Native
editor import remains a separate acceptance step. See [portable editorial workflow](portable-editorial.md).

Focused pass-four evidence: 22 distinct Python tests passed, including real
tiny PNG/video encoding, shared validation/assembly, relocated collected media,
CLI checking/comparison, representative human edits, and malformed inputs.
Three native Signal scene projects passed TypeScript checks. The native browser
exporter was substituted in the new shot-contract tests of that pass. A later
check ran the real path: on 2026-10-17 the native Signal rendered all three
shots in headless Chromium and passed `validate`, timeline export, assembly,
`package`/`package-check`, and generic `check` (run from a copy outside the
checkout). That earlier pass reported 102 passing tests; this is historical
evidence, not a current full-suite result. All 376 files in the Unit 9 preservation baseline
retained their SHA-256 values, with no new film files added.

## Creative workflow pass

The toolkit now provides read-only status/resume, explicit saved checkpoints,
timecoded notes with short IDs, anchor correction/history, and optional shot
intent. Full-length draft animatics use placeholder cards, supplied storyboards,
or one sampled SVG frame per shot. Revision previews render fresh SVG motion
with surrounding context and a 30-second limit. Both use matching source audio,
visible headers outside the picture, unique files, input identity, and focused
verification. Planning lives in `.sbph/`; draft output is separate from existing
production files. Native Motion Canvas preview integration remains separate.

Tests use temporary films; the current Unit 9 package is preserved. See
[the creative workflow](creative-workflow.md) for short commands and limits.

The shared toolkit is implemented, with Unit 9 as the first working integration. No earlier Big Tex, Flight 134, or Kitchen Chefs code was migrated or removed.

## First validation pass

The framework now uses a shared read-only gate for assembly, timeline export,
delivery verification, and conform. Build schema 2 records configured render
settings, actual source paths and content, shared source, dependency locks,
and local toolchain identity. Audio duration/alignment, exact editor-WAV crop,
baseline source-window, and Motion Canvas cue-metadata checks are hardened.
JSON evidence writes use atomic replacement.

The existing Unit 9 outputs and evidence remain preserved. They have not been
rebuilt or relabeled as schema 2. Their legacy shot manifest intentionally fails
the new gate until an intentional rebuild. The evidence below describes the
preserved earlier package, not a full-film run of the changed framework.
See [the validation contract](production-validation.md).

## Second-film and generic-verification pass

[The Signal](../examples/signal/README.md) is a self-contained, three-shot,
four-second example: 96 frames at 24 fps, 320 × 180, and four-frame handles.
Its generated stereo WAV and SVG shapes require no Unit 9 material, font files,
browser, or external service. The documented launcher completes the workflow
after copying the film folder outside the checkout.

Generic delivery checks no longer require Unit 9's review JSON, geometry, or
WebP assets. They verify the selected delivery, generate decoded contact sheets
for any shot count, and run only explicitly configured reference/profile checks.
Unit 9's assertions remain available through its optional profile. Delivery,
reference, proof interval, and timeline filename are explicit project settings.
Conform rejects self-comparison. See [the generic verification contract](generic-verification.md).

This pass preserves the earlier Unit 9 package and its legacy evidence. It does
not rebuild the full film or establish native editor acceptance.

## Evidence

- Unit 9: 57 shots, 7,194 frames, 1920 × 1080, 30 fps, 239.8 seconds.
- 57 handled clip files: 12 extra frames on each side; file hashes and frame counts pass.
- OTIO: 57 picture clips, one original WAV, 79 markers. Serialization round trip and frame ranges pass. FCP 7 XML fallback generated through the adapter.
- Current master audio correlation: 0.999961; sampled offset estimates are zero at 16 kHz.
- Nineteen full-resolution source/decoded comparisons: minimum luma PSNR 52.32 dB; maximum flat-interior RGB error 0.488/255.
- Shared assembly: 171 first/mid/final shot samples conform to the viewing reference; maximum mean RGB error 0.276/255 at 512 × 288. Audio alignment passes.
- Three focused contract checks pass: timeline gaps rejected, duplicate IDs rejected, and handles do not lengthen the editorial timeline.
- MoviePy v2 read smoke passes. It is available as an optional compositor; current assembly uses ffmpeg-python.
- A shared 15-second proof renderer is implemented with matching source audio.

## Boundaries

Resolve and its scripting SDK were not found in standard application locations on this host. Native import, marker appearance, project color management, and device playback are unverified; `sbph resolve-check` (Studio) and `sbph resolve-record` (Free) now exist to produce that evidence ([resolve-acceptance.md](resolve-acceptance.md)). SVG rigs and motion are baked within shot clips. Human timing decisions remain human acceptance.

The initial handled source inventory was captured after the first complete build and focused media verification, explicitly labeled as a current-state baseline. Future source changes invalidate cached partial builds. The original full-frame renderer has a byte-verified source snapshot for its render record.

## Useful next action

Follow the [v1.0 checklist](v1.md): perform DaVinci Resolve round-trip acceptance on the verified handoff (`handoffs/H615c266ae878` or `~/handoffs/signal-v1`) following [resolve-acceptance.md](resolve-acceptance.md), followed by human screening of the delivered film.

## Motion Canvas proof

Motion Canvas 3.17.2 is installed with the 2D package, UI, Vite plugin and FFmpeg exporter. The Unit 9 shutdown proof is rebuilt as a native Motion Canvas scene with signals, easing and editable time events. It uses the same 34.1–49.1-second source interval, 450 frames at 30 fps, 1920 × 1080, and four cut boundaries. A labeled 1920 × 600 comparison places the old and new pictures side by side with one audio track.

The editor WAV is an exact sample crop of the original. The new movie and comparison stream-copy the baseline AAC track, and decoded PCM equality is checked. Original proof and source-WAV hashes are checked before and after. Delivery frame counts, rates, sizes and color tags are checked. Three focused audio-window tests and a TypeScript project check cover the new integration. Decoded action and claim frames are reviewed separately from those mechanical checks.

The local visual editor and 2D inspector are checked in a fresh headless browser, including a cue metadata save and restore. This establishes local loading and persistence, not a human timing acceptance pass. `./unit9 motion-proof` rebuilds the proof; `./unit9 motion-editor` serves the editor. [Details and limits](motion-canvas.md).

The new version adds a reach, anticipation, native 30 fps motion, and a claim reveal on the spoken line. It is a creative A/B with fixed audio and cuts, not a controlled engine speed comparison. The full-film SVG master, original proof, handled clips and OTIO remain intact. Generic Motion Canvas handled-shot/OTIO integration is now available through explicit project registration; the preserved Unit 9 package has not been migrated. Remotion remains uninstalled.

## Native full film

The full recording is also rebuilt in Motion Canvas: 57 native shots, 7,194 frames, 239.8 seconds, 1920 × 1080 at 30 fps. Narration anchors choose the visual subjects and cuts; 33 selected accents reinforce physical actions and major changes. The same palette, outlined SVG type and character cutouts, lossless WebP props, and original audio are retained.

`./unit9 motion-film` renders in resumable 600-frame sections. `./unit9 motion-film-editor` serves the complete native timing project. The full source is in the film's `motion-canvas/full-film-v01/`; the movie, verification, retained source frames and decoded review sheets are in `production/motion-canvas-full/`.

The full-film SVG master, original proof, handled clips and OTIO remain intact. Generic Motion Canvas handled-shot/OTIO integration is now available through explicit project registration; the preserved Unit 9 package has not been migrated. Remotion remains uninstalled. Original proof receipts retain their historical renderer hashes; the full-film verification identifies the current native sources separately.

This independent native rebuild does not migrate the legacy SVG handled-shot manifest to build schema 2. The validation compatibility boundary described above remains in place.
