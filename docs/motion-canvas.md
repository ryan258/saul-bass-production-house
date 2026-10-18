# Motion Canvas

Motion Canvas **3.17.2** is installed as an animation backend. The core, 2D, UI, Vite plugin and FFmpeg exporter packages use the same pinned version. Vite 5.4.21, TypeScript 5.9.3 and Playwright Core 1.64.1 are locked with them.

The first integration is the Unit 9 shutdown proof. It is a native scene with signals, generator-based tweens, cut-paper vector shapes, SVG cutouts, WebP props, and named time events. Existing film renderers continue to work.

```sh
./unit9 motion-proof
./unit9 motion-editor
./unit9 motion-film
./unit9 motion-film-editor
```

The editor serves **http://127.0.0.1:9139/** until Ctrl-C. The source and cue metadata belong to the film's `motion-canvas/shutdown-proof-v01/` directory. Moving a named endpoint retimes its tween through Motion Canvas's `useDuration`. Listen with the exact source-window WAV while adjusting cues. For another project, set `motion_canvas` in its production configuration to the relative path of its `project.ts`. Keep its `proof.json`, `audio.wav`, and TypeScript configuration beside it. An explicit `--motion-project /path/to/project.ts` override is available for a bounded experiment.

## Shared rendering path

1. TypeScript checks the film project against the installed Motion Canvas packages.
2. A loopback Vite server loads it in a fresh, headless Chromium context.
3. Motion Canvas's official `Renderer` and `ImageExporter` generate the requested PNG frame sequence. Playwright only hosts the canvas; it does not implement animation timing or take screenshots of frames.
4. ffmpeg-python encodes those PNGs using the existing H.264/sRGB-transfer/BT.709-matrix/limited-range contract. The existing proof's AAC track is stream-copied for this controlled A/B.
5. The command checks complete frame numbering, delivered count and rate, exact editor-WAV samples, identical decoded delivery audio, and the unchanged baseline hash. It writes a source inventory and a labeled comparison.

The proof stages both movies, its receipt, and source inspection frames before
replacing the previous delivery. All of those outputs promote together with
rollback on caught failures or cancellation. The normal 450-frame proof retains
twelve inspection frames; shorter proofs use only in-range samples and retain
their first/last frames. `--keep-frames` retains the complete new sequence at
`render-work/`. Without it, an older retained sequence is removed only when the
new delivery succeeds, within the same rollback operation.

A failed proof reports its unique `.proof-build-*` working directory for
diagnosis. Retry with the same command; the previous delivery and earlier
diagnostic work remain intact until intentionally replaced or removed. Source
typechecking and rendering operate on a copy, so renderer metadata writes do
not change the original project. The original SVG proof is never replaced.

Before rendering, the CLI now checks that the baseline sidecar and actual media
match the intended source interval, and compares baseline audio with the exact
editor-WAV crop. Cue `.meta` files are included in the source snapshot; changed,
added, or deleted cue files invalidate the render. Existing baseline media and
metadata are preserved. See [the production validation contract](production-validation.md).

Chromium must already exist. The launcher tries Playwright's configured executable, then the local Google Chrome executable; `SBPH_CHROMIUM` selects another installed binary. It does not download a browser or use the user's browser profile. A source installation still needs the normal `npm ci` package download.

The official Motion Canvas FFmpeg exporter is registered for editor use. The CLI comparison uses image export followed by shared encoding so it can keep the previous proof's exact audio track and explicit color settings. Exporter registration and the visual editor load are checked locally; an interactive human timing pass remains separate.

## Cut-audit contract

A shared-project scene may report where each shot actually began by setting `globalThis.sbphCutAudit = {shotId: frame}` (the older `unit9CutAudit` name is still read). `render.mjs` returns it as `cutAudit`; registered named-cut renders require `{shotId: 0}` after isolation.

## Full-film rebuild

`motion-film` selects the film's `motion-canvas/full-film-v01/project.ts`; set `motion_canvas_full` in the production configuration to register another path. The full native Unit 9 edit has 57 shots, 33 selected action accents, and named events for each cut and action start/end. The edit records the narration anchor for each spoken passage, preserves transcript uncertainty, and keeps chosen sound accents distinct from the cut structure.

The renderer processes 600-frame sections, verifies and encodes each, then removes
its temporary PNGs. Each section's clip, selected source PNGs, and `chunks.json`
receipt are staged and promoted together. Re-run the same command to resume after
an interruption. Reuse requires current source, browser, tool, render-setting and
chunk-size identity, plus checked clip hashes, ranges, media metadata, cut audit,
and source PNG evidence. Missing or corrupt evidence rebuilds its section.
`--chunk-frames` accepts a whole-second section size; keep it unchanged to reuse
an existing cache. The full PNG sequence is never accumulated on disk.

Cache schema 2 records this stronger evidence. Older cache files remain on disk,
but require a fresh render before they can be reused under the new contract.
Valid completed sections survive later render, mux, audio, picture-check, or
receipt failures. Unverified full-film scratch is cleaned up. The completed
movie, verification, effective edit, source samples and decoded storyboard pages
replace the previous delivery only as one checked set; obsolete extra pages are
removed during that same promotion. Source copies protect original cue files.
Unrelated editor exports are preserved.

These operations recover from caught errors and cancellation. They do not claim
an atomic filesystem transaction across a power loss or forced process kill.
If rollback itself cannot finish, surviving backups and their mapping remain in
a reported `.promotion-recovery-*` directory beside the final outputs.

Each native cut is audited against the planned global frame. Delivery checks include complete frame count, rate, size, color tags, source identities, decoded audio equality and selected full-resolution source-to-decoded pictures. Five decoded contact sheets cover every shot. The full editor's cue save/restore check uses the registered scene and test cue from `proof.json`.

Saved `.meta` event positions drive the full rebuild. `effective-edit.json` in the delivery folder records the current cut and action frame ranges resolved from the editor; no manual transcription back into the original edit JSON is needed. Keep actions within their shot and retain the full-audio end event. Validation rejects conflicting ranges. Decoded storyboard frames and full-resolution picture samples are each extracted in one FFmpeg pass.

The original WAV is a byte-identical editor asset. The new movie stream-copies the original full film's AAC track. It retains the complete recording, order, tempo and gain. Static outlined SVG cutouts are displayed through native image nodes; the browser decodes them. Joint constraints, moving cables, network growth and transitions are native Motion Canvas geometry and signals. No original `frame()` renderer is called.

Explicit Motion Canvas shot projects and full-project frame windows can now generate handled clips and OTIO through the shared production workflow; see [portable editorial workflow](portable-editorial.md). Unit 9 is registered through a separate configuration and output directory; shot 31 is in the default output and a complete 57-shot run is in `full-run-ti36vxyf/`. That run has been rendered, validated, assembled, conformed, and packaged into a verified handoff (`handoffs/H615c266ae878`). See [Unit 9 native handoff](unit9-motion-handoff.md). The native full-film source is editable in Motion Canvas. Existing OTIO and SVG shot workflows remain available and their media inventories are preserved.

## Primary references

- [Motion Canvas time events and useDuration](https://motioncanvas.io/docs/time-events/)
- [Motion Canvas image sequence rendering](https://motioncanvas.io/docs/rendering/)
- [Official FFmpeg exporter](https://motioncanvas.io/docs/rendering/video/)
- [Motion Canvas media nodes](https://motioncanvas.io/docs/media/)
- [Motion Canvas source and license](https://github.com/motion-canvas/motion-canvas)
