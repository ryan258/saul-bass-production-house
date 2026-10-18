# Saul Bass Production House — Roadmap

`sbph` is a local production toolkit for graphic films: recording + shot list + frame generator → separately rendered shots with handles, OpenTimelineIO (OTIO) timeline, and verified review movie. Single-user, local-first, deterministic.

Current version: `0.2.0`.  
Target milestone: `v1.0.0` — **End-to-end evidence of a complete native graphic film (Unit 9) from generation through real DaVinci Resolve round-trip editorial and back from a clean checkout.**

For the concrete delivery checklist and run orders, see the [v1.0 Checklist](docs/v1.md).

---

## Core Pillars & Current State

### 1. Media & Generation Engine
- **librosa 1.0.0**: Audio onset, beat, and tempo detection; non-destructive marker candidate generation.
- **ffmpeg-python 0.2.0**: High-integrity video encoding, audio stream extraction, and editorial assembly.
- **OpenTimelineIO 0.18.1**: Lossless editorial exchange with track, clip, marker, and source-range modeling. Includes FCP XML fallback adapter.
- **Sharp 0.35.5 / librsvg**: High-speed SVG rasterization with lossless embedded asset handling (WebP -> PNG transport).
- **Motion Canvas 3.17.2**: Vector procedural animation, signals, easing, and timing cues driven by headless Chromium.

### 2. Validation & Fingerprint Engine (Schema 2)
- **Deep Fingerprinting**: Invalidation across edit lists, source assets, toolchains, browser versions, and render settings.
- **Strict Verification Gates**: Media duration, sample rates (48 kHz stereo), frame counts, color tags, decoded contact sheets, and temporal audio alignment.
- **Editorial Windows**: Precise frame ranges and audio windows; source recordings can retain tails without corrupting comparison metrics.

### 3. Fault Tolerance & Output Preservation
- **Staged Promotion & Rollback**: SVG shots, proofs, and assemblies stage artifacts beside target destinations and roll back on caught failures or SIGINT.
- **Resumable Builds**: `shots --resume` and `motion-film --chunk-frames` verify existing media hashes, frame metadata, and cut audits before reusing work.
- **Diagnostic Retention**: Interrupted or failed render attempts isolate diagnostic directories without overwriting prior valid deliveries or corrupting input sources.
- **Collision Protection**: Output managers verify and reject overlapping paths between input assets and output folders.

### 4. Portable Editorial & Return Verification
- **Self-Contained Packages**: `sbph package` bundles relative OTIO timelines, original master audio, handled shot media, and SHA-256 integrity manifests.
- **Offline Integrity**: `sbph package-check` verifies relocated packages without source repo access.
- **Editorial Round-Trip**: `sbph compare-return` computes diffs between master and editor OTIO files, reporting slip, cut changes, retimed clips, and unsupported structures.
- **Resolve Acceptance**: Tooling for both DaVinci Resolve Studio (API automated) and Free (operator-recorded) acceptance checks ([docs/resolve-acceptance.md](docs/resolve-acceptance.md)).

---

## Milestones

### Milestone 1: Core Foundation & SVG Pipeline (Completed)
- [x] Initial architecture, ffmpeg-python pipeline, and OpenTimelineIO integration.
- [x] Sharp-based SVG frame streaming and render runtime.
- [x] Unit 9 SVG film proof of concept and full-film baseline.
- [x] Delivery conformance checks and audio correlation metrics.

### Milestone 2: Native Motion Canvas & Fingerprinting (Completed)
- [x] Motion Canvas runtime, proof scenes, and visual editor integration.
- [x] Build Schema 2 fingerprinting and input collision protection.
- [x] The Signal reference film (three-shot SVG and native Motion Canvas reference).
- [x] Resumable chunk rendering and staged promotion safeguards.
- [x] Non-destructive creative workflows: notes (`N1`), intent, animatics, and revision drafts.

### Milestone 3: Road to v1.0 (In Progress)
Tracked in detail in [docs/v1.md](docs/v1.md).

- [x] **Test suite integrity**: Full Python suite passes (213 tests passing).
- [x] **Unit 9 native full film proof**: 15s shutdown proof rendered and interruption-tested.
- [x] **Unit 9 native full film assembly**: 7,194-frame 239.8s film rendered and checkpointed.
- [x] **Unit 9 handled shots**: 57 native handled shots rendered and validated (`full-run-ti36vxyf`).
- [x] **Native timeline & assembly validation**: Timeline with 33 accent/impact markers, assembly (7,194 frames), `check`, and `conform` (171 samples, max RGB error 0.286) passed.
- [x] **Package verification**: Collected handoff built and verified with `package-check` (`handoffs/H615c266ae878`, 58 media files).
- [ ] **DaVinci Resolve round-trip acceptance**: Import OTIO into real DaVinci Resolve, perform editorial cuts, export OTIO return, and run `resolve-check` / `compare-return`.
- [ ] **Human screening**: Human editorial screening of delivered review assembly.
- [ ] **v1.0.0 Release**: Version bump, tag, and publish documentation.

---

## Post-v1.0 Roadmap

### Milestone 4: Granular Invalidation (v1.1)
- **Targeted Fingerprinting**: Narrow fingerprint invalidation so changes in docs or non-rendering CLI commands do not invalidate existing shot caches.
- **Selective Re-renders**: Dependency graph tracing between scenes and shared assets to invalidate only affected shots.

### Milestone 5: Expanded NLE Support (v1.2)
- **Final Cut Pro & Premiere**: Native testing and acceptance harnesses for FCP XML and Premiere Pro exchange.
- **Marker Color & Metadata Mapping**: Standardized marker coloring and notes translation across multiple NLE environments.

### Milestone 6: Film Authoring Tooling (v1.3+)
- **Interactive Scaffolding**: `sbph init` wizard to generate production boilerplate from an audio track and script.
- **Dynamic Animatic Editor**: Browser-based preview tool to adjust cuts and audition timing before rendering heavy frames.
