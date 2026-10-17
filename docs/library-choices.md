# Library choices

Use established libraries for media mechanics, leaving custom code for artwork, actions, and editorial intent.

| Library | Decision | Reason |
|---|---|---|
| OpenTimelineIO 0.18.1 | Core | Standard clip, track, marker, and rational-time model; native Resolve interchange. |
| ffmpeg-python 0.2.0 | Core | Explicit FFmpeg graphs for frame streams, trims, concatenation, muxing, and probing. It still needs the installed FFmpeg binary. |
| librosa 1.0.0 | Core | Established onset-strength, onset-detection, and beat-tracking functions replace bespoke peak-picking logic for new projects. |
| Sharp 0.35.5 | Core | SVG rasterization through librsvg with the embedded image support our cut-paper assets require. |
| MoviePy 2.2.1 | Optional composition | Helpful Python clip and layer operations. It is installed and pinned; current encoding/assembly use ffmpeg-python directly. Use v2 APIs rather than old `moviepy.editor` examples. |
| otio-fcp-adapter 1.0.0 | Fallback | Community adapter writes FCP 7 XML from the same OTIO timeline. Feature preservation still needs an editor conform. |
| Motion Canvas 3.17.2 | Installed animation backend | Native signals, easing and editable time events drive the Unit 9 shutdown proof. Official Renderer/ImageExporter supply frames; shared FFmpeg delivers the controlled A/B. Full-film handled-shot integration remains a future step. |
| Remotion | Alternative backend | Frame-based React composition and preview tools fit SVG and web-authored scenes. Not installed or integrated in this version. |

Motion Canvas now supplies the bounded shutdown proof alongside the existing renderer. OTIO and Resolve retain editorial interchange. Remotion remains an uninstalled alternative; it is not another dependency in this production path.

## Primary references checked on 2026-10-17

- [Blackmagic: Resolve 18.5 OTIO introduction and import workflow](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_18.5_New_Features_Guide.pdf)
- [OpenTimelineIO adapters and community plugin boundaries](https://github.com/AcademySoftwareFoundation/OpenTimelineIO/blob/main/docs/tutorials/adapters.md)
- [ffmpeg-python API](https://kkroening.github.io/ffmpeg-python/)
- [librosa onset detection](https://librosa.org/doc/main/api/generated/librosa.onset.onset_detect.html)
- [MoviePy installation and FFmpeg configuration](https://zulko.github.io/moviepy/getting_started/install.html)
- [MoviePy repository, v2 changes, and performance tradeoffs](https://github.com/zulko/moviepy)
- [Motion Canvas introduction](https://motioncanvas.io/docs/)
- [Remotion's frame-based composition model](https://www.remotion.dev/docs/idea)

Onset candidates are measurements, not editorial acceptance. A successful OTIO round trip is interchange evidence, not native Resolve acceptance. Those distinctions prevent a new library from becoming a new source of misleading confidence.
