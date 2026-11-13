# Harmony repair ledger — 2026-10-21 (Verified 2026-11-13)

All rows below describe source changes prepared and verified against the full regression suite. The full Python suite passes **292 tests** (`./scripts/test.sh`) and Node editor dependency checks pass 2 tests cleanly. Existing production media and historical receipts remain preserved until an intentional rebuild is requested. Run the focused follow-up in [current state](current-state.md) locally before rebuilding production media.

October 24 follow-up: Ryan supplied an initial 281-test result with 16 failures and 1 error. The log identified path-alias handling in native source-copy validation/test fixtures and a conform-message compatibility mismatch. After the corrections and portable symlink regressions, Ryan's affected-module rerun passed **34 tests** in 21.154 seconds. The receipt is `.local/review/harmony-followup.log`; [current state](current-state.md) distinguishes this pass from subsequent source changes and pending full-suite acceptance. Subsequent expansion to 292 tests verified registration and editorial preservation across the entire suite.

## Corrections

| Review issue | Implemented contract | Focused regression modules |
|---|---|---|
| Resolve could pass failed return | Scripted acceptance gates measured return identity, audio, timing, structure; manual timing changes need explicit `--accept-edits` | `test_resolve` |
| Offline basename could certify media | Presumed associations remain unverified; baseline bytes never prove remote returned bytes | `test_handoff_return`, `test_resolve` |
| Disabled root stack ignored | Root enabled state affects comparison and audio preservation | `test_handoff_return` |
| Baseline audio not bound to source | Full-film preflight checks audio source/window/format before rendering; final audio metadata checked | `test_motion_native_preflight`, `test_motion_film_preservation` |
| Stereo/level changes could pass | 48 kHz stereo-mix per-channel correlation and RMS bounds supplement timing | `test_audio_comparison`, `test_audio_windows` |
| Declared source could be replaced | Pure shared source enumeration protects declared originals, including originals explicitly inside output | `test_core_harmony`, `test_shared_output_inputs` |
| Joined shot names could collide | Shared filename function; preflight rejects collisions including case-insensitive names | `test_core_harmony` |
| Broad globs included outputs | Generated trees excluded; output-targeting globs rejected; explicit originals stay explicit | `test_core_harmony` |
| Competing local writers | Exclusive per-output locks with owner metadata, no automatic stale-lock removal | `test_core_harmony` |
| Pulse cues escaped shot bounds | Pulse schema/events/duration/containment/competing-signal validation | `test_motion_film_contract` |
| Registration pair could split | Staged paired promotion and rollback | `test_motion_registration` |
| TypeScript config diagnostics omitted | Config read errors and requested project inclusion are part of typecheck | `test_motion_native_preflight` |
| Corrupt manifests blocked resumption | Explicit preserving `--repair-manifest` / `--repair-cache`; no silent adoption | `test_shot_resumption`, `test_motion_film_preservation` |
| Editorial artifacts could mix generations | Timeline/XML/receipt and review/report promote together; drafts pair movie/sidecar | `test_editorial_preservation`, `test_generic_verification`, `test_draft_workflow` |
| Evidence/version/CLI errors drifted | Derived version, package-bound acceptance, unique exports, failure exit statuses, concise operator errors, configured binary diagnostics | `test_resolve`, `test_workflow` |
| Status repeated shot 01 after completion | Saved current timeline/delivery/reference evidence advances toward screening/package/Resolve | `test_workflow_harmony` |
| Long run names repeated | Explicit `motion-use NAME`; invocation override remains available | `test_workflow_harmony`, `test_stale_native` |
| Registration ignored active run | Selected-run refresh preserves settings, retains prior config, and promotes its registration with the shared default/edit pair | `test_motion_registration` |
| Native cache opaque | Read-only receipt/hash status, diagnostics and repair hints; no reuse/probe claim | `test_motion_native_preflight` |
| Native cue saves caused churn | Semantic cue identity; legacy guards upgrade explicitly on refresh | `test_motion_registration` |
| Fixed native port conflict | Available local ports for rendering; optional `SBPH_MOTION_PORT` | `test_motion_native_preflight` |
| Documentation contradicted itself | One current evidence table; prior chronology marked historical | Source review |

## Remaining human/native acceptance

The continuous native reference's first-cut lag originates in film scheduling outside this repository. It was not fixed by changing thresholds or removing frame-range rounding safeguards. New native receipts retain exact first-cut/preceding-frame evidence; conform records exclusions and pending review. Correcting original film choreography requires a deliberate source edit and native render acceptance.

The content screening remains focused: repeated matrix/city/radio/tower compositions, bench/cable/socket escalation, physical grips/contact/release, narration versus on-screen labels, and uncertain transcript words. These are viewing judgments, not outcomes an agent can attest from contact sheets.

`screen-record` creates a new hash-bound explicit owner attestation under the run's `evidence/`; it never infers viewing or approval. `evidence` lists saved receipts without blessing their currency. Keep evidence and source backups outside volatile `/tmp/`.

## Deliberate scope

Selective fingerprint invalidation, new NLE adapters, a browser authoring application, and additional renderer dependencies are future decisions. The current conservative invalidation protects personal work. The owner SVG archive is retained and the old root package inventory retired; neither is used at runtime.
