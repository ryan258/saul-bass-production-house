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

The CLI deletes the full PNG sequence after successful delivery, retaining twelve inspection frames. `--keep-frames` retains it. A failed render retains its working folder for diagnosis. Re-running `motion-proof` replaces only the Motion Canvas output folder's working sequence and named outputs. It never replaces the original proof.

Before rendering, the CLI now checks that the baseline sidecar and actual media
match the intended source interval, and compares baseline audio with the exact
editor-WAV crop. Cue `.meta` files are included in the source snapshot; changed,
added, or deleted cue files invalidate the render. Existing baseline media and
metadata are preserved. See [the production validation contract](production-validation.md).

Chromium must already exist. The launcher tries Playwright's configured executable, then the local Google Chrome executable; `SBPH_CHROMIUM` selects another installed binary. It does not download a browser or use the user's browser profile. A source installation still needs the normal `npm ci` package download.

The official Motion Canvas FFmpeg exporter is registered for editor use. The CLI comparison uses image export followed by shared encoding so it can keep the previous proof's exact audio track and explicit color settings. Exporter registration and the visual editor load are checked locally; an interactive human timing pass remains separate.

## Full-film rebuild

`motion-film` selects the film's `motion-canvas/full-film-v01/project.ts`; set `motion_canvas_full` in the production configuration to register another path. The full native Unit 9 edit has 57 shots, 33 selected action accents, and named events for each cut and action start/end. The edit records the narration anchor for each spoken passage, preserves transcript uncertainty, and keeps chosen sound accents distinct from the cut structure.

The renderer processes 600-frame sections, verifies and encodes each, then removes its temporary PNGs. Successful sections are hashed in `production/motion-canvas-full/chunks.json`. Re-run the same command to resume after an interruption. Source and cue changes invalidate the cache. `--chunk-frames` accepts a whole-second section size; keep it unchanged while resuming an existing render. The full PNG sequence is never accumulated on disk.

Each native cut is audited against the planned global frame. Delivery checks include complete frame count, rate, size, color tags, source identities, decoded audio equality and selected full-resolution source-to-decoded pictures. Five decoded contact sheets cover every shot. The full editor's cue save/restore check uses the registered scene and test cue from `proof.json`.

Saved `.meta` event positions drive the full rebuild. `effective-edit.json` in the delivery folder records the current cut and action frame ranges resolved from the editor; no manual transcription back into the original edit JSON is needed. Keep actions within their shot and retain the full-audio end event. Validation rejects conflicting ranges. Decoded storyboard frames and full-resolution picture samples are each extracted in one FFmpeg pass.

The original WAV is a byte-identical editor asset. The new movie stream-copies the original full film's AAC track. It retains the complete recording, order, tempo and gain. Static outlined SVG cutouts are displayed through native image nodes; the browser decodes them. Joint constraints, moving cables, network growth and transitions are native Motion Canvas geometry and signals. No original `frame()` renderer is called.

Explicit Motion Canvas shot projects and full-project frame windows can now generate handled clips and OTIO through the shared production workflow; see [portable editorial workflow](portable-editorial.md). Unit 9 has not been registered or rebuilt through that new path. The native full-film source is editable in Motion Canvas. Existing OTIO and SVG shot workflows remain available and their media inventories are preserved.

## Primary references

- [Motion Canvas time events and useDuration](https://motioncanvas.io/docs/time-events/)
- [Motion Canvas image sequence rendering](https://motioncanvas.io/docs/rendering/)
- [Official FFmpeg exporter](https://motioncanvas.io/docs/rendering/video/)
- [Motion Canvas media nodes](https://motioncanvas.io/docs/media/)
- [Motion Canvas source and license](https://github.com/motion-canvas/motion-canvas)
