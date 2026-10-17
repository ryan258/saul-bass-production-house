# Generic delivery verification

`check` verifies a delivery using the shared production gate, encoder contract,
audio comparison, and decoded review frames. A project does not need a WebP
directory, a transcript, geometry samples, pre-existing review pictures, or a
particular title or shot count.

## Artifact roles

- `delivery` is a film-root-relative or absolute movie path. Without it, `check`
  uses the legacy explicit `master` setting, then `output/assembly.mp4`.
- `reference` is a separate, explicitly selected full-film movie used only by
  `conform`. The legacy explicit `master` setting remains a reference fallback.
- Without a reference, conform stops with an instruction; it never silently
  compares an assembly against itself. Same-path, symlink, and hard-link aliases
  of the assembly are rejected.
- `timeline_file` is an optional `.otio` filename inside the output directory.
  Its default is `human-edit.otio`; it is not inferred from the film title.
- `proof_start` defaults to zero seconds and `proof_duration` to 15 seconds,
  clamped to the remaining edit. Explicit CLI values override project defaults.

For example:

```json
{
  "delivery": "production/assembly.mp4",
  "reference": "production/proof.mp4",
  "timeline_file": "human-edit.otio",
  "proof_start": 0,
  "proof_duration": 4
}
```

CLI overrides are available for bounded checks:

```sh
./sbph check /path/to/production.json --delivery /path/to/movie.mp4
./sbph conform /path/to/production.json --reference /path/to/reference.mp4
```

Conform checks both movies' dimensions, rate, and length, then compares the first,
middle, and last editorial frame of every shot. Samples use an aspect-preserving
512-pixel width. This is sampled consistency evidence, not full visual or human
editor acceptance. Regenerating a reference from current source is useful for
render-path checks; it does not turn that reference into an approved prior cut.

## Generic checks and reports

The delivery must have the edit's dimensions, frame count, rate, and duration;
the shared encoder's BT.709/sRGB-transfer/limited-range color tags; and 48 kHz
stereo audio of the expected duration. Audio uses the pass-one sample-count,
correlation, and alignment checks. The workflow currently expects the continuous
source recording to match the editorial duration.

FFmpeg decodes the video through the stream with errors treated as failures.
The verifier retains a midpoint picture from each shot in contact sheets,
paginating as many sheets as needed, with no 60-shot ceiling. It uses Pillow's
built-in font, avoiding an operating-system font requirement.

Reports and generated review pictures go under the configured output directory:

- `media-verification.json` identifies the selected delivery and SHA-256, source
  fingerprint, actual video metadata, audio evidence, shot checks, decoded shot
  frame list, contact-sheet paths, and any optional comparisons/profile checks.
- `review/decoded-storyboard-N.jpg` contains up to 20 shots per sheet. The report's
  list identifies the current sheets; older unlisted files are not current evidence.
- `assembly-verification.json` identifies the explicit reference and its hash,
  compared frames, sample dimensions, audio results, and measured picture error.

The generic check does not rewrite a film-owned `review/verification.json`.
Missing or failing configured checks do not produce a new passing report.

## Optional source-picture references

To compare specific decoded frames against source PNGs, explicitly configure
film-root-relative or absolute paths:

```json
{
  "verification": {
    "reference_frames": [
      {"frame": 0, "file": "review/references/opening.png"}
    ]
  }
}
```

Reference frames must be in range and files must exist. Dimensions must match.
The comparison requires luma PSNR above 38 dB and flat-interior RGB error below
3/255 when flat interiors exist. Reference hashes are recorded and checked for
changes during verification. Without references, the report records zero source
picture comparisons rather than implying that they were performed.

Artifact-role, proof-window, and verification settings do not change handled
picture identity. Adding a reference comparison or choosing a different delivery
therefore does not require rerendering otherwise current shots. Source, handle,
rate, dimensions, and toolchain changes still invalidate the build.

## Optional Unit 9 profile

Unit 9's lossless RGBA WebP inventory, final connection gap, lever-position
assertions, and source-reference list now live in `src/sbph/unit9_checks.py`.
They run only when explicitly selected:

```json
{"verification": {"profile": "unit9"}}
```

`--profile unit9` opts in for one check; `--profile generic` overrides a configured
profile. The profile reads the film's existing source-review files. It does not
regenerate geometry or establish its currency against a new animation revision.
That limit is recorded in the report.

The toolkit's `examples/unit-9.json` explicitly preserves its original proof
interval, timeline filename, master path, and optional profile. The external
Unit 9 project and its generated outputs remain untouched. Its legacy shot
manifest still requires an intentional schema-2 rebuild before the production
gate accepts it. If later using the external film's own configuration for a new
build, add these explicit settings there deliberately; generic commands no
longer infer them from its name.
