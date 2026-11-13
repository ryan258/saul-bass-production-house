# DaVinci Resolve acceptance

This is the step that turns "valid OTIO" into "a Resolve user can edit this". It produces a dated evidence file next to the handoff. Until one exists for a real film, native Resolve import is **unverified** (see [resolve-handoff.md](resolve-handoff.md)).

Which path you have depends on your Resolve edition:

| | Resolve **Studio** | Resolve **Free** |
|---|---|---|
| External scripting | allowed | refused (`scriptapp` returns nothing) |
| Command | `sbph resolve-check` — measures an import and export | `sbph resolve-record` — stores your attestations; the export is still measured |
| Evidence | `checks[]` each `passed`/`failed`/`warning` | `checks[]` each `attested`/`not confirmed` |

(Edition gating is from Blackmagic forum/community reports, not their official feature matrix. If `resolve-check` can't connect, the error tells you to use the manual path.)

## 0. Make a handoff

```sh
./unit9 motion-package --run full-run-ti36vxyf        # or: ./sbph package /path/to/production.json --out ~/handoffs/film-v1
./sbph package-check ~/handoffs/film-v1
```

## 1a. Studio: one command

Resolve running, a project open, **Preferences ▸ System ▸ General ▸ External scripting using = Local**.

```sh
./sbph resolve-check ~/handoffs/film-v1
```
```
Resolve acceptance (scripted): passed — ~/handoffs/film-v1/resolve-acceptance-20261018-141500.json
Return comparison: unchanged (complete: True, audio preserved: True)
```

It imports `edit.otio` as a new timeline named `SBPH acceptance <time>`, then measures: frame rate; clip counts; each clip's timeline start and length; each video clip's **source in-point (= handle length)**; whether each clip's media is online; expected marker frames (warning only). It then exports the timeline back to OTIO and runs `compare-return` on it. Any `failed` check makes the status `failed`.

## 1b. Free: manual import, recorded

1. **File ▸ Import ▸ Timeline…** and choose `edit.otio` from the handoff folder. Keep source-clip import on. If clips come in offline, select them ▸ right-click ▸ **Relink Selected Clips…** ▸ the handoff's `media/` folder (reported behavior: OTIO imports can arrive unlinked).
2. Check: frame rate matches, clips sit back to back, the first video clip's source starts at the handle length (slip a clip and you should see extra frames), markers are visible, the single audio clip spans the whole film.
3. **Lock the audio track.**
4. Make at least one real timing edit (slip, trim, move) so the return has something to say.
5. **File ▸ Export ▸ Timeline…** as OTIO, **into the handoff folder** (e.g. `return.otio`).
6. Record it:

```sh
./sbph resolve-record ~/handoffs/film-v1 --resolve-version "19.1 Free" \
  --imported --linked --markers-visible --audio-locked \
  --returned ~/handoffs/film-v1/return.otio --text "slipped shot 31 by 3 frames"
```

Leave off any flag you didn't actually confirm; the status is then `incomplete`, not `attested`. The `--returned` comparison is measured by the toolkit either way.

## Resolve on another machine (for example Windows)

The toolkit never needs to run where Resolve runs. A handoff is a self-contained folder (Unit 9's is about 63 MB), so:

1. On the toolkit machine: make and check the handoff (step 0).
2. Copy the **whole** folder to the Resolve machine (USB, cloud drive, `scp`). Install Resolve there; nothing else is needed: no Python, FFmpeg, or Node.
3. Do the manual steps in 1b on that machine. Export the OTIO **into the copied folder** as `return.otio`.
4. Copy `return.otio` back into the original handoff folder on the toolkit machine.
5. There, run `resolve-record … --returned <handoff>/return.otio` (or just `compare-return`).

Resolve on another machine can export absolute paths unavailable here. A unique basename permits a **presumed association** with collected media; it does not prove the bytes used by the remote editor. Such media remains `unverified_media` and comparison is incomplete. Return the actual media used, or explicitly relink/export against the verified collected files locally before measured acceptance. Merely copying the OTIO back cannot attest unavailable remote bytes.

If Resolve Free shows clips as unplayable, tell me the codec message: the clips are 8-bit H.264 4:2:0, which Free on Windows normally decodes, but that is from memory, not tested here.

## What the evidence does and doesn't say

- **Does:** this handoff, at this Resolve version, imported with these results; and how the returned OTIO differs from the baseline.
- **Doesn't:** color management, device playback, render/export from Resolve, or that the edit is good. Manual attestations are yours, not measured.
- The record is a new `resolve-acceptance-<time>.json` inside the handoff. Extra files don't break `package-check`; nothing is overwritten.

## If it fails

| Symptom | Likely cause |
|---|---|
| `DaVinciResolveScript is not installed` | Resolve Studio's scripting modules not at the default path → set `RESOLVE_SCRIPT_API` to its `…/Developer/Scripting` folder |
| `Resolve refused the scripting connection` | Free edition, Resolve not running, or External scripting not set to Local |
| `media online` failed | source clips weren't found → relink to `media/`; the toolkit won't edit your OTIO |
| `handle in-point` failed | Resolve normalised the source offset (e.g. start timecode) → file the exact numbers from `checks[]`; this is a signal, not noise |
| return `needs_review` with `unverified_media` | export the OTIO into the handoff folder, or relink |

## Acceptance gates and intended edits

Scripted `resolve-check` must preserve measured media identity, enabled structure, supported timing, and original audio through export. Marker and track-label differences are warnings; other incomplete/failed return checks block success. Receipts bind the exact handoff manifest, timeline, and source fingerprint; failed/incomplete acceptance returns a nonzero process status.

For a manual return containing intended supported picture edits, review `compare-return` and add `--accept-edits` to `resolve-record`. That flag attests your intent only; unavailable media, changed audio, disabled/unsupported structures, and incomplete comparisons still block measured acceptance. Without an exported return, a manual import attestation remains an import attestation and does not close the round-trip milestone.

Exports and receipts use unique protected destinations. Keep the package, returned OTIO and actual media, acceptance JSON, and screening evidence together in a durable backup.
