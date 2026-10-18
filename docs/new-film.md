# Make your own film

A film is a folder you own. The toolkit never writes into your sources; it writes into `production/`. This walkthrough builds **Two Dots** (4 seconds, 2 shots) in about 40 lines. Every file below is complete and was run as written.

```sh
alias sbph=/path/to/saul-bass-production-house/sbph
mkdir -p ~/films/twodots/data ~/films/twodots/src && cd ~/films/twodots
```

## 1. The four files

**`production.json`** — the project file. Everything is optional; these defaults apply: `root` `.`, `edit` `data/edit.json`, `audio` `audio.wav`, `driver` `src/film.cjs`, `output` `production`, `handles` `12`.

```json
{"handles": 6, "reference": "production/proof.mp4"}
```

**`data/edit.json`** — the shot list. Frames, not seconds; shots must tile `0 … frames` with no gap or overlap.

```json
{
  "title": "TWO DOTS",
  "fps": 24, "width": 320, "height": 180, "frames": 96,
  "scenes": [
    {"id": "drift", "kind": "move", "start": 0,  "end": 48, "name": "Drift",   "action": "A dot crosses the frame."},
    {"id": "meet",  "kind": "move", "start": 48, "end": 96, "name": "Meeting", "action": "A second dot arrives and they touch."}
  ],
  "events": [
    {"id": "touch", "frame": 90, "basis": "action", "meaning": "The dots touch."}
  ]
}
```

| Field | Rule |
|---|---|
| `fps`, `frames`, `width`, `height` | positive integers; width and height **even** (H.264) |
| scene `id`, `kind` | letters, digits, `-`, `_`; clip is named `{id}-{kind}.mp4` |
| scene `name`, `action` | required text; `action` feeds notes, animatic cards, OTIO metadata |
| scene `intent`, `storyboard` | optional ([creative-workflow.md](creative-workflow.md)) |
| `events` | optional story beats → OTIO video-track markers (`basis: "accent"` is green, anything else cyan) |

**`src/film.cjs`** — the driver. It returns one SVG string per frame. That's the whole contract:

```js
const edit = require('../data/edit.json');
const clamp = x => Math.max(0, Math.min(1, x));
const ease = t => t * t * (3 - 2 * t);

function draw(scene, local) {
  // local < 0 is the leading handle; local >= length is the trailing handle. Clamp, never borrow a neighbor.
  const u = ease(clamp(local / (scene.end - scene.start - 1)));
  const a = scene.id === 'drift' ? 20 + 130 * u : 150;
  const b = scene.id === 'drift' ? 300 : 300 - 130 * u;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${edit.width}" height="${edit.height}" viewBox="0 0 320 180">
    <rect width="320" height="180" fill="#15283F"/>
    <circle cx="${a}" cy="90" r="14" fill="#F3AE35"/>
    <circle cx="${b}" cy="90" r="14" fill="#72C9B5"/></svg>`;
}
const shotFrame = (id, local) => draw(edit.scenes.find(s => s.id === id), local);
const frame = n => { const s = edit.scenes.find(s => n >= s.start && n < s.end); return shotFrame(s.id, n - s.start); };
module.exports = {init: async () => {}, frame, shotFrame};
```

- `shotFrame(id, local)` renders handled clips. `local` runs from `-handles` to `length + handles - 1`.
- `frame(n)` renders the full-film `proof`. Both paths must give the same picture inside each shot's body; `conform` checks exactly that.
- The SVG's `width`/`height` must equal the edit's, or rasterization fails with *Raster contract mismatch*.

**`audio.wav`** — your recording, at least `frames / fps` seconds long. Never rewritten by the toolkit. Here, a synthetic tone:

Assembly, timeline audio, delivery checks, and conform use the source-zero
editorial window. An unused recording tail is retained in the original file but
excluded from that window; proofs use their selected interval. Verification
records both the original recording hash and the compared window.

```python
import wave, math, struct
with wave.open('audio.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
    w.writeframes(b''.join(struct.pack('<hh', v, v)
        for v in (int(8000 * math.sin(2 * math.pi * 220 * t / 48000)) for t in range(48000 * 4))))
```

## 2. Build

```sh
sbph doctor   production.json    # libraries, ffmpeg/ffprobe/node found?
sbph proof    production.json    # full-frame reference render → production/proof.mp4
sbph shots    production.json    # 2 clips × (48 body + 12 handle) = 60 frames each
sbph analyze  production.json    # optional: librosa onset candidates (do this BEFORE timeline)
sbph timeline production.json    # production/human-edit.otio (+ .xml)
sbph assemble production.json    # bodies only, handles excluded → assembly.mp4
sbph check    production.json    # delivery + audio + decoded contact sheets
sbph conform  production.json    # assembly vs proof.mp4 at first/mid/last frame of each shot
```

Expected tail: `Media checks passed: 96 frames; 2 shots; 1 contact sheets; profile generic.` then `Assembly conforms: 6 boundary/midpoint samples; …`.

Open `production/review/decoded-storyboard-1.jpg` (a decoded midpoint from every shot) before the movie; it is the fastest sanity check.

## 3. What you get

```
production/
  shots/drift-move.mp4  meet-move.mp4   60 frames each: 6 handle + 48 body + 6 handle
  shots.json                           build fingerprint + per-clip hashes
  human-edit.otio / .xml               V1: 2 clips (source in-point 6), A1: original WAV, markers
  assembly.mp4  proof.mp4              review movies
  media-verification.json  assembly-verification.json  timeline-verification.json
  review/  audio-cues.json             (drafts/ appears after animatic/revision)
.sbph/                                 notes, intent, checkpoints (created by the first note) — keep with the film
```

In the NLE, the picture clips start at source frame 6 and last 48 frames. The six frames on each side are your slip room.

## 4. Iterate

Edit `src/film.cjs` and run `sbph validate production.json`:

```
sbph: Stale shot build: configuration, sources, or tools changed; refresh all shots
```

That is the fingerprint working. Rebuild everything the gate needs (`sbph shots production.json`), then `timeline`, `assemble`, `check`. For fast looks while you tweak, use drafts instead ([cookbook](cookbook.md#look-at-one-shot-without-rebuilding)).

## Grow it

| Need | Do |
|---|---|
| Files the driver reads that aren't in `src/ assets/ data/` | list them in `"source_files": ["../shared/font.ttf"]` — undeclared reads are invisible to the fingerprint |
| Different source folders | `"source_globs": ["src/**/*", "art/**/*", "data/**/*"]` (replaces the defaults) |
| Separate review/conform movies | `"delivery"`, `"reference"` paths |
| Another OTIO filename | `"timeline_file": "twodots.otio"` |
| Vector animation with editable timing | `"renderer": "motion-canvas"` + `"motion_shots"` — see [cookbook](cookbook.md#use-motion-canvas-for-shots) |
| A reference example to crib from | [`examples/signal`](../examples/signal/README.md) (SVG and Motion Canvas versions of one film) |
