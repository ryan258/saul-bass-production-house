# The production path

For a complete, bounded practice run, use [The Signal](../examples/signal/README.md):
`./signal build` creates a second film from its own source and audio and checks
the complete proof → handled shots → OTIO → assembly path. It also works after
copying the film folder outside this checkout.

1. **Inspect the recording first.** Keep the original file and its SHA-256. Probe actual sample count, duration, channels, and rate. Transcribe locally when words drive the story. Keep uncertain words marked as uncertain.
2. **Choose an editorial spine.** Write a finite shot list with frame ranges. Describe a character's action and its consequence. A repeated lyric or announcement should change the visual situation.
3. **Measure audio with librosa.** Retain onset and beat candidates. Select meaningful accents after the story exists. Do not replace speech timing with a uniform beat grid.
4. **Prove a short physical action.** Check contact, release, reach, direction, scale, and the result of the action in delivered pixels. Review a short encoded proof before committing to a full render.
5. **Keep film code small.** Use Motion Canvas signals, easing and named time events for new vector choreography; use `useDuration` when an endpoint should be movable in the editor. The existing SVG backend supplies `init`, `frame`, and `shotFrame`. The shared toolkit handles encoding and interchange. Preserve native SVG props, lossless WebP counterparts, and outlined type. Compare one short proof against the previous renderer before migrating a full film. See [the Motion Canvas workflow](motion-canvas.md).
6. **Render separate shots with handles.** Configure the extra frames before and after each editorial body: Unit 9 uses 12; The Signal uses 4. The source-frame convention is always explicit. Do not use a neighboring shot as an extension.
7. **Generate the OTIO timeline.** One continuous original WAV; individual picture clips; chosen action cues; separate machine music candidates. Read it back with OTIO and verify every clip's in-point, duration, and available range.
8. **Make the human pass in Resolve.** Import the OTIO, lock the audio track, and adjust pauses, anticipation, overlaps, cut timing, and reaction holds. The machine proposes structure; the editor chooses the performance.
9. **Verify the delivered file.** Check exact frame count, duration, color tags, audio correlation and offset, representative decoded frames, and media hashes. Keep contact sheets of actual delivered frames. Generic verification generates them from the shot list; optional source pictures and film-specific assertions are explicit. Keep the delivery and conform reference roles separate. See [verification](generic-verification.md).
10. **Leave a way back.** Save the edit, paths, original audio reference, source art, locked dependencies, short commands, and concise evidence limits. Mark native Resolve acceptance separately from static interchange checks.

Start with one film. Add another renderer only when it removes a recurring source of effort. Do not build a new studio interface as a prerequisite for finishing a film.

For a full Motion Canvas rebuild, keep the narration anchors and chosen action accents in the film's edit data. Check one native timing audit and representative physical contacts first. Render in bounded sections, validate their frame ranges, and retain a source fingerprint so interruption recovery is automatic. Match the full recording without gain or tempo changes. Review decoded frames from every shot as well as the complete movie.
