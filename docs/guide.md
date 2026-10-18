# Guide — start here

SBPH turns a **recording + a shot list + a frame generator** into separately rendered shots, an editable OTIO timeline, and a verified review movie. It measures and checks; a human edits the rhythm.

```
 audio.wav ─┐
 edit.json ─┼─► shots ─► validate ─► timeline (OTIO) ─► Resolve / any NLE
 film.cjs  ─┘     │          │            └─► package ─► compare-return
 (or Motion       │          └─► assemble ─► check ─► conform
  Canvas scenes)  └─ each clip = body + handles (extra frames each side)
```

Everything is local. Nothing is uploaded.

## The one idea that explains the rest

**A build is a fingerprint.** `shots` hashes your edit, audio, driver/source files, render settings, and the toolchain (FFmpeg, Node, Python packages, shared code). Every later command (`validate`, `timeline`, `assemble`, `check`, `conform`, `package`) re-derives that fingerprint and refuses to run if any shot was built from something else.

So you never wonder whether a delivery is current; the tool tells you. The price: change *anything* in the fingerprint and the **whole** shot set is stale. Rebuild all shots, not one.

`status` now lists the changed source files and browser/tool/settings fields.
Its delivery report is historical evidence about movie bytes; current production
validation and human acceptance remain separate checks.

Use `./sbph shots /path/to/production.json --resume` to recover an interrupted
build. It verifies each current clip's record, ranges, hash, frame count, rate,
and dimensions before reusing it. Missing/invalid clips are rendered. A stale
identity prevents reuse; the option does not bless older clips. Plain `shots`
still renders fresh selected shots. Candidates replace shared shot/proof/assembly
outputs only after their checks, preserving prior files on handled failures.

For native Unit 9, start with `./unit9 motion-status` or `motion-resume`. Add
`--run full-run-ti36vxyf` immediately after either command to inspect the existing
complete run; the default continues to refer to the partial native output.

| Changes the fingerprint (rebuild all) | Does not |
|---|---|
| `edit.json`, audio, driver, `src/` `assets/` `data/` | notes, intent, checkpoints (`.sbph/`) |
| `handles`, fps, size, other render settings | `output`, `delivery`, `reference`, `timeline_file` |
| `source_files` / `source_globs` contents | `proof_start`, `proof_duration`, `verification` |
| FFmpeg / Node / Python package changes | |

## Five-minute tour (The Signal)

```sh
./scripts/setup.sh            # once: Python 3.11–3.13 venv + Node packages
./signal build                # prepare → proof → shots → timeline → assemble → check → conform
./signal status               # where am I, what's next (read-only)
open examples/signal/production/assembly.mp4
```

Then try the loop on a film you can break safely:

```sh
./signal note --shot bridge --at 00:00:01:16 --kind t --text "Longer hold"
./signal revision --note N1   # 2–3 s draft of that shot, labeled DRAFT, with matching audio
./signal resolve --note N1 --text "Reviewed"
```

## Command map

All commands: `./sbph <command> /path/to/production.json [flags]`. `./signal` and `./unit9` are short launchers with the project path filled in.

| Stage | Command | Reads | Writes |
|---|---|---|---|
| Orient | `doctor` · `status` · `resume` | config, hashes | nothing (`resume --note/--shot/--text` saves a checkpoint) |
| Plan | `note` `notes` `resolve` `reanchor` `intent` | `.sbph/` | `.sbph/*.json` |
| Preview | `animatic` · `revision` | edit, audio, driver | `output/drafts/` (unique, labeled) |
| Measure | `analyze` | audio | `audio-cues.json` |
| Build | `proof` · `shots [--shot ID]` | driver / scenes | `proof.mp4`, `shots/`, `shots.json` |
| Gate | `validate` | all of the above | nothing |
| Interchange | `timeline` · `package` | validated shots | `human-edit.otio` (+`.xml`), `handoffs/H…` |
| Deliver | `assemble` → `check` → `conform` | validated shots | `assembly.mp4`, `media-verification.json`, `assembly-verification.json`, `review/` |
| Return | `package-check` · `compare-return` | a handoff folder | nothing (optional `--out` report) |
| Resolve | `resolve-check` (Studio) · `resolve-record` (Free) | a handoff folder | `resolve-acceptance-<time>.json` in it |

Add `--json` to workflow commands for scripts. `./sbph --help` lists every flag.

## What each gate does and does not prove

| Command | Proves | Does not prove |
|---|---|---|
| `validate` | every shot is current; ranges, hashes, frame counts, size, source audio length | picture is good |
| `check` | delivery size/rate/frames/color tags, 48 kHz stereo, audio correlation, full decode, contact sheets | human approval |
| `conform` | assembly matches an **independent** reference at first/middle/last frame of every shot | the reference is right |
| `package-check` | folder is intact, relative, self-contained | the sender's identity |
| `compare-return` | what an editor changed in OTIO terms | anything about the picture |

Resolve/NLE import is **not** verified by any command. OTIO read/write and referenced media are.

## Where to go next

| I want to… | Read |
|---|---|
| Make my own film | [new-film.md](new-film.md) |
| Do a specific job | [cookbook.md](cookbook.md) |
| Fix an error message | [troubleshooting.md](troubleshooting.md) |
| Use Motion Canvas | [motion-canvas.md](motion-canvas.md), [portable-editorial.md](portable-editorial.md) |
| Understand the gate/fingerprint contract | [production-validation.md](production-validation.md) |
| Notes, intent, animatics in depth | [creative-workflow.md](creative-workflow.md) |
| Verification options | [generic-verification.md](generic-verification.md) |
| Prove it in Resolve | [resolve-acceptance.md](resolve-acceptance.md) |
| What's left for v1.0 | [v1.md](v1.md) |
| Project roadmap | [roadmap.md](../roadmap.md) |
| Unit 9 specifics | [unit9-motion-handoff.md](unit9-motion-handoff.md), [current-state.md](current-state.md) |
