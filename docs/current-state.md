# Current state — 2026-10-17

## Portable editorial pass

Motion Canvas shot bodies now use explicit isolated projects or shared-project
frame windows, edge-hold handles, and the shared production validation gate.
The Signal includes an optional three-shot native example with separate output.
Collected handoff folders contain relative OTIO references, handled media, the
original recording, notes/intent, and integrity hashes. A relocated folder can
be checked without its source project. Read-only editor-return comparison
reports timing/media/structure changes and unsupported constructs.

This pass has not registered or rebuilt Unit 9 in the new native shot path.
Existing Unit 9 movies, shots, timeline, and evidence remain preserved. Native
editor import and a real browser render of the new shot path remain separate
acceptance steps. See [portable editorial workflow](portable-editorial.md).

Focused pass-four evidence: 22 distinct Python tests passed, including real
tiny PNG/video encoding, shared validation/assembly, relocated collected media,
CLI checking/comparison, representative human edits, and malformed inputs.
Three native Signal scene projects passed TypeScript checks. The native browser
exporter was substituted in the new shot-contract tests; no real render of that
new path or full suite was run. All 376 files in the Unit 9 preservation baseline
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

Resolve and its scripting SDK were not found in standard application locations. Native import, marker appearance, project color management, and device playback are unverified. SVG rigs and motion are baked within shot clips. Human timing decisions remain human acceptance.

The initial handled source inventory was captured after the first complete build and focused media verification, explicitly labeled as a current-state baseline. Future source changes invalidate cached partial builds. The original full-frame renderer has a byte-verified source snapshot for its render record.

## Useful next action

Import `../nonsense/unit-9/svg-film-v01/production/unit-9-human-edit.otio` in Resolve. Lock the audio track and make the timing pass. Keep the exported human edit as a new timeline and an OTIO copy.

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
