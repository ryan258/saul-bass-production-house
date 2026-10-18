# Motion shots, collected handoffs, and editor returns

The existing `shots → validate → timeline → assemble` path now supports explicit
Motion Canvas shot bodies. `package` collects a validated shot set and original
audio into a new folder. `compare-return` compares an editor's OTIO export with
that saved folder, independently of the source project. These commands do not
apply an editor's changes to the source edit.

## Short example

For the browser-free SVG example:

```sh
./signal prepare
./signal shots
./signal package --out /tmp/signal-handoff
./sbph package-check /tmp/signal-handoff
./sbph compare-return /tmp/signal-handoff --returned /path/to/returned.otio
```

Choose a new `--out` folder; existing destinations are refused. Without `--out`,
packages receive unique names under the film's output `handoffs/` directory.
Copy or zip the **entire** folder, then check it after moving or unpacking it.
The toolkit performs no upload, messaging, or publication.

Unit 9 now has a separate native registration with explicit saved cut windows
and an audio/timing identity guard. See [Unit 9 native handoff](unit9-motion-handoff.md).
Its existing production files remain preserved. Shot 31 is rendered in the
default output, and a complete 57-shot run with a verified collected handoff exists
under `full-run-ti36vxyf/` (`handoffs/H615c266ae878`). It has passed shot rendering,
validation, timeline export (`unit-9-motion-human-edit.otio`), assembly, `check`,
and `conform` against the full-film reference. That registration isolates each selected
native scene in the temporary render copy to keep neighboring cached cut frames out of
its body and handles. Arbitrary unregistered shared-project windows require review of
their own renderer's cut-frame behavior; isolated per-shot projects avoid that
dependency.

For the optional native Motion Canvas version of The Signal:

```sh
./signal prepare
./signal motion-shots --shot approach
./signal motion-shots
./signal motion-validate
./signal motion-timeline
./signal motion-assemble
./signal motion-package --out /tmp/signal-motion-handoff
```

These commands use `examples/signal/production-motion.json` and a separate
`production-motion/` output. `motion-shots` launches installed headless Chromium
to run the official Motion Canvas renderer; it downloads no browser. A
real run of this path (three shots, then validate, timeline, assembly, package
and package-check) passed on 2026-10-17; that is mechanical evidence, not visual
acceptance.
The SVG and Motion Canvas examples illustrate the same story, with independent
animation implementations; pixel equivalence is not claimed.

## Registering Motion Canvas

Select `"renderer": "motion-canvas"` in a new or deliberately changed production
configuration. Keep a separate output directory when preserving a prior build.
The default renderer remains `svg`. Map every edit shot ID:

```json
{
  "renderer": "motion-canvas",
  "output": "production-motion",
  "motion_shots": {
    "opening": "motion/opening/project.ts",
    "answer": "motion/answer/project.ts"
  }
}
```

A string path renders that shot's body from source frame zero. For a shared
full-film project, each entry instead explicitly supplies its window:

```json
{
  "opening": {"project": "motion/full/project.ts", "startFrame": 0},
  "answer": {"project": "motion/full/project.ts", "startFrame": 48}
}
```

The body count comes from `end - start` in the edit. Source windows must be
reviewed against the saved native cuts after cue changes; this generic path
does not infer or rewrite an edit from arbitrary Motion Canvas event names.
It fails on incomplete or incorrectly numbered frame sequences. It then adds
`handles` copies of the first and last body frames, encodes the normal shot
format, and records the explicit hold policy. Handles cannot expose adjacent
source scenes. Animation and effects remain baked within each clip.

Each project needs a self-contained source folder, `tsconfig.json`, and scene
module declarations (see the example). Rendering/typechecking uses a temporary
copy so Motion Canvas metadata caches do not alter original sources. Keep
relative imports/assets inside that folder; use toolkit dependencies through
the configured aliases. Sources must be outside the output folder. Folder
contents, cues, framework launcher, browser identity, runtime identity, edit,
audio, settings, and explicit windows contribute to the build fingerprint.
Declare other dynamic inputs through `source_files`/`source_globs`; their bytes
are inventoried, but that declaration does not copy them into an isolated
Motion source folder or rewrite external imports.

`--shot` uses the existing partial-build contract. A source change invalidates
the complete fingerprint: rebuild all required shots before production export.
Planning and placeholder animatics remain available. Fresh draft SVG motion or
sampled SVG stills are refused for Motion configurations; use one handled shot
for a native review. Existing Unit 9 sources/outputs and its legacy manifest remain preserved. A
separate native registration now exists; see [Unit 9 native handoff](unit9-motion-handoff.md).

## What is in a package

| File | Purpose |
| --- | --- |
| `edit.otio` | Separate picture clips, handles, original audio, and markers |
| `media/video/` | Collected handled clips, byte-checked against the build |
| `media/audio/original.*` | Unmodified source recording, even if outside film root |
| `editorial-context.json` | Scene actions, events, optional intent, all notes/history |
| `handoff.json` | File hashes, media identities, frame bounds, source fingerprint |
| `README.txt` | Moving, relinking, returning, and checking instructions |

OTIO references are relative to the package timeline. `package-check` verifies
every inventoried file, contained relative media reference, clip identity, and
source range. It rejects missing/changed files and references escaping the
folder. It needs neither the production configuration nor the original media
location. File hashes detect changes; they are not signatures authenticating
the sender. New return files placed alongside the package are allowed and do
not change the saved baseline.

The package contains baked media and editorial context, not an editable source
archive, native editor database, or new viewing master. No Resolve import or
track lock is implied. Relink to `media/` if the editor does not resolve relative
references. Lock the original audio in the editor before timing changes.

## Comparing an editor return

Export a new `.otio` file from the editor. Preserve SBPH clip metadata when
possible. Keep returned references pointing to the collected media, or relink
them before checking. Names alone never establish shot identity.

```sh
./sbph compare-return /path/to/handoff --returned /path/to/return.otio --json
./sbph compare-return /path/to/handoff --returned /path/to/return.otio --out /tmp/return-review.json
```

The report lists timeline/source start changes, duration changes, moves across
tracks, duplicates/deletions, gaps, track/marker changes, source ranges outside
available handles, and original-audio placement/identity. It checks actual local
media hashes. Retained metadata can associate offline media provisionally, but
unavailable media is reported as unverified and cannot yield `unchanged`.
Identical media used by multiple shots requires stable shot metadata to avoid
an ambiguous match.

Nested stacks, transitions, track trims, effects/retimes, incompatible frame
rates, and off-frame time values are explicitly marked for manual review;
`comparisonComplete` becomes false. Comparison never executes an adapter for
another interchange format, fetches remote references, renders an editor mix,
or changes the source edit, return, package, notes, or production manifests.
`--out` writes one new JSON report and refuses to overwrite any existing file.
Without it the report is printed only. Human creative approval and native
editor acceptance remain separate.
