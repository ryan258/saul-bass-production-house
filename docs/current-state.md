# Current state — 2026-11-13

SBPH is version **0.2.0**, a local, single-user graphic-film toolkit. The shared SVG and Motion Canvas paths produce handled shots, editable OTIO, collected handoffs, and review movies. Human timing judgment remains outside mechanical verification.

## Current implementation

The harmony repair pass changes framework source, so **every existing handled-shot build is stale by design**. Prior movies, packages, receipts, original recordings, and the sibling Unit 9 source tree remain preserved. The repaired source is verified against the full regression suite (292 tests pass). Existing production media remains preserved until an intentional rebuild is requested.

Implemented corrections cover Resolve acceptance and media identity, native full-film audio binding, source/output protection, shot filename collisions, pulse and TypeScript validation, paired registration recovery, explicit damaged-manifest/cache recovery, local writer locks, staged editorial/review artifacts, channel/level audio checks, and accurate status/evidence reporting. See [the repair ledger](harmony.md) for contracts and remaining acceptance.

## Suite verification — November 13

The full Python test suite passed: **292 tests in 46.3s** (`./scripts/test.sh`), with zero failures and zero errors. Focused modules including `test_motion_registration` (21 tests), `test_motion_shots`, `test_stale_native`, `test_workflow_harmony`, `test_editorial_preservation`, and `test_resolve` all pass cleanly. Node editor dependency tests (`tests/test_motion_editor_dependencies.mjs`, 2 tests) also passed cleanly.

Earlier in the repair cycle (October 24), Ryan ran the full suite (281 tests, 16 failures and 1 error) which identified macOS path-alias differences (`/var` vs `/private/var`) and conform wording. Follow-up corrections resolved those differences and added portable symlink regressions, after which affected-module reruns and the subsequent expanded 292-test suite verified all contracts.

GitNexus was refreshed against HEAD and current uncommitted changes (123 files, 1,380 nodes, 3,561 edges, 65 communities, 114 processes). Read-only status/preflight confirms the selected `full-run-ti36vxyf` configuration and its 63 required sources are present.

## Artifact evidence before this repair

| Artifact | Evidence observed in the read-only review | Current limit |
|---|---|---|
| Unit 9 native handled run `output/unit-9-motion-handled/full-run-ti36vxyf/` | 57 shots; source/clip hashes matched before repairs; assembly bytes matched saved media report | Framework repairs now stale this build; no new probing or rebuild |
| Same run: timeline/assembly/conform | Saved timeline, 7,194-frame assembly, check and conform receipts; 171 conform samples; max RGB MAE about 0.286/255 | Conform used first-frame offset 1 and did not establish exact first-cut fidelity |
| Handoff `H615c266ae878` inside that run | Collected package with 58 media files and matching saved build fingerprint | Historical package; native editor acceptance unrecorded |
| Default native output | Preserved partial shot 31 build | Distinct from the completed named run; stale/incomplete |
| Standalone native full film | Historical 7,194-frame, 57-shot render/interruption/resumption acceptance | Three recorded framework hashes differed even before this repair |
| Standalone native proof | Historical real render/interruption/retry acceptance | Twelve recorded framework hashes differed before this repair |
| The Signal SVG | Preserved example assembly and matching saved report bytes | Stale after prior framework changes, and again after this repair |
| Python suite | All 292 tests and Node editor tests pass cleanly on current source | Framework changes stale handled-shot builds until an intentional rebuild |
| Resolve and human screening | No Resolve acceptance receipt found under toolkit output; screening unrecorded | Explicit owner/editor work remains |

The detailed earlier logs are [historical](history/2026-10-18.md). They are retained for recovery context, not used as present-tense status.

## Short next actions

The full regression suite and registration checks are verified. The next operational steps before production release are intentional native rebuild, first-cut review, and real Resolve acceptance:

```sh
./scripts/test.sh test_motion_registration
```

This checkout now has the complete native run selected in `.local/`. To repeat or change that explicit selection after source verification:

```sh
./unit9 motion-use full-run-ti36vxyf
./unit9 motion-status
./unit9 motion-preflight
```

`motion-use` saves only a local pointer under `.local/`; it never renders or changes the run configuration. `motion-use default` restores the partial default. `--run NAME` still overrides one invocation.

After reviewing native saved cues, `./unit9 motion-register --refresh` upgrades the owned registration to semantic cue identity. It follows the saved run or a first-option `--run NAME` override, refreshes the selected run's receipt/window mapping while preserving its other settings, and retains the prior selected configuration under that run's `.registration-history/production-<sha256>.json`. The default config and shared edit refresh in the same promotion; a shared timing change can stale other named runs. It writes toolkit registration files, not the sibling film source. Run status/preflight again before rebuilding deliberately with `./unit9 motion-shots --resume`; this can take many minutes and is not started by registration, status, or preflight.

`./unit9 motion-finish` validates, exports the timeline, assembles, checks, conforms, packages, and checks the exact new package. It does not render shots. `UNIT9_REFERENCE` can select a different independent reference. First-frame exclusions remain explicit and require human cut-frame review.

Watch the complete delivered movie and inspect first cut frames before recording your own attestation:

```sh
./unit9 motion-screen-record --screened --first-cuts-reviewed --text "Reviewed complete delivery and first cut frames"
./unit9 motion-evidence
```

Use [Resolve acceptance](resolve-acceptance.md) for real import/export. Intentional supported timing edits in a manual return need `--accept-edits`; unavailable media, changed audio, or unsupported structures still block a successful measured return.

## Preservation and scope

Nothing in this pass claims power-loss atomicity, current native render acceptance, creative approval, device playback, or Resolve acceptance. Do not rerender merely to remove a stale message before the source changes are reviewed and tested. Source backup/restoration, human screening, real Resolve round trip, and any release remain deliberate separate actions.
