# Review, pause, and resume

Pass three adds a small local creative loop. It keeps planning beside the film,
makes visibly marked drafts, and leaves existing proofs, baselines, handled
clips, timelines, and deliveries alone.

From the toolkit root, start with the self-contained example:

```sh
./signal status
./signal prepare
./signal intent --shot bridge --goal "Connect the track" --change "The crossing becomes possible"
./signal animatic
./signal note --shot bridge --at 00:00:01:16 --kind t --text "Give the connection a longer hold"
./signal resume --note N1
./signal revision --note N1
```

`./unit9` accepts the same commands for its configured film. No Unit 9 planning
records or drafts are created by installing these features. The implementation
and tests preserve the current Unit 9 package.

## Status and resume

`status` reports the configured film, source availability, handled-build state,
configured delivery, saved checkpoint, open notes, recent drafts, and one next
action. `resume` gives a shorter view of the same information. Neither executes
the suggested command, starts an editor, renders, or writes files.

Both work before source audio is prepared. A missing source is shown as a next
action. Missing, legacy, stale, incomplete, changed, and unverified builds remain
distinct. Matching source and media hashes are freshness evidence; `validate`,
`check`, native editor acceptance, and human review remain separate gates.
Saved delivery reports are identified as historical evidence tied to movie bytes.

Save a checkpoint with a short task, shot, or note:

```sh
./signal resume --shot bridge --text "Review the pause before crossing"
./signal resume --note N1
./signal resume
```

The last saved checkpoint is the focus; earlier checkpoints are retained.
An open note becomes the next task when appropriate. Resolved notes are not
automatically suggested again. A long shot gets an explicit five-second window
in the suggested command, avoiding an accidental long render. A command shown
in status is a suggestion, not an action already performed.

## Timecoded notes

Notes use short IDs such as `N1`. A shot-only note starts at that shot's in-point;
`--at` can specify a global position inside it. Without a shot, a global time
selects its containing shot. A note with no position can use a valid saved
checkpoint, reducing repeated input.

Accepted times include decimal seconds (`1.5`), minutes and seconds (`0:01.5`),
integer-rate timecode (`00:00:01:12`), and explicit frames (`36f`). The timecode
frame field must be below the project fps. Out-points are exclusive.

Categories accept short codes: `t` timing, `c` clarity, `v` continuity, `a` action,
`s` sound, and `n` general note. Full names also work.

```sh
./signal notes
./signal resolve --note N1 --text "Reviewed in the new preview"
./signal notes --all
```

A note retains its text, shot ID, local frame, original global frame, and fps.
Moving a shot recalculates the current global time. Changing fps, deleting the
shot, or trimming away the local frame flags the anchor rather than guessing.
Reposition an existing note without retyping its text:

```sh
./signal reanchor --note N1 --shot arrival --at 70f
```

The previous anchor is retained in history. Resolving a note retains the note.

## Lightweight shot intent

Each shot already has its authored action. Optional intent adds only what helps:
`goal`, `obstacle`, `change`, `emotion`, `framing`, and `exit_condition`.

```sh
./signal intent --shot bridge
./signal intent --shot bridge --goal "Connect the track" --exit-condition "The bridge reaches the far side"
```

Run `intent` without a shot to inspect the project. Fields merge across updates;
there is no mandatory bible or completion checklist. A scene may also carry an
optional `intent` object in its edit JSON. Separate planning overrides take
precedence without rewriting that authored edit.

## Draft animatics

`animatic` creates a full-length draft from the current integer-frame shot list,
with matching source audio and an exact editorial frame count. It does not need
handled clips, a successful production build, or an implemented renderer.

- A shot's optional `storyboard` image path is used when explicitly supplied.
- Otherwise a placeholder card shows the shot name, action, and available goal
  and change. Missing explicitly configured images fail rather than disappearing.
- `--render-stills` samples the registered SVG driver once per remaining shot,
  then holds that picture for its editorial duration. It does not animate every
  source frame.

```sh
./signal animatic
./signal animatic --render-stills --width 320
```

A storyboard entry is a film-root-relative or absolute path on a scene:

```json
{"storyboard": "boards/bridge.png"}
```

Drafts have a visible label and shot/time-range header above the picture. The
header adds 52 pixels to the movie height and does not cover source action.
Default picture width is capped at 640 pixels; `--width` accepts 160–1280.
Small pictures may be enlarged to 160 pixels to support labels.

## Bounded revision previews

`revision` renders fresh motion from the registered SVG driver for one shot plus
half a second of context on each side. It preserves global source timing and
uses the matching original-audio interval. It can select a note or the saved
shot checkpoint, so the operator does not have to reconstruct the location.

```sh
./signal revision --shot bridge
./signal revision --note N1 --before 0.25 --after 0.25
./signal revision
```

The total encoded window is capped at 30 seconds. For a long shot, select a
smaller global interval that overlaps the shot:

```sh
./sbph revision /path/to/production.json --shot long-shot --start 40 --duration 5
```

These previews and sampled animatics currently use the SVG `driver` and edit,
not a Motion Canvas scene or its editable event metadata. Native Motion Canvas
commands remain available separately. A preview is never an approved baseline.

## Storage, freshness, and limits

- Notes, intent, checkpoint history, and the draft index live in the film's
  `.sbph/` folder. Keep that folder with the film and include it in backups.
- Production fingerprints ignore managed workflow files, even when custom
  source globs include `.sbph/`. Deliberately declared `source_files` remain
  explicit inputs. Planning changes alone do not invalidate rendered shots.
- Drafts use unique filenames under `output/drafts/`, with a JSON sidecar. They
  never replace `proof.mp4`, its baseline, assembly, shot media, or timelines.
- Draft identity includes its parameters, actual source audio/edit, storyboards,
  relevant shot intent, shared code, tools, and source renderer when used.
  Status distinguishes current, stale, changed, missing, and unverified drafts.
- Draft checks cover frame count, rate, dimensions, source-window audio alignment,
  and stable inputs. They do not establish production acceptance or human review.
- Writes are atomic and workflow edits use `.sbph/.write.lock`. A corrupt record
  or existing lock causes a clear failure rather than discarding owner data.
  Inspect an abandoned lock before removing it; reads remain available.

All workflow commands support `--json` for local scripts and short aliases.
No browser, account, remote model, or upload is used by this workflow.

## Focused regression checks

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_workflow
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests .venv/bin/python -m unittest test_draft_workflow
```

Fixtures use temporary film copies. Checks include read-only resumption,
timecode and anchor changes, note/checkpoint history, isolated planning identity,
placeholder and sampled animatics, bounded motion previews, correct audio,
distinct output files, source-change rejection, and preservation of prior media.
