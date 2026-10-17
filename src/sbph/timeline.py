"""OpenTimelineIO is the timeline model and serializer, not handwritten interchange JSON."""
from pathlib import Path
import json,importlib.metadata
import opentimelineio as otio
from .project import dump,sha
from .validation import validate_shot_set,audio_cues

def build_model(p,records,candidates):
    """Construct interchange in memory so packaging never overwrites an export."""
    RT=otio.opentime.RationalTime;TR=otio.opentime.TimeRange
    tl=otio.schema.Timeline(name=p.edit['title']+' / human edit',global_start_time=RT(0,p.fps))
    v=otio.schema.Track(name='V1 / animated shots',kind=otio.schema.TrackKind.Video)
    a=otio.schema.Track(name='A1 / original recording',kind=otio.schema.TrackKind.Audio)
    for s in p.edit['scenes']:
        r=records['shots'][s['id']]
        local=p.output/'shots'/Path(r['file']).name
        mr=otio.schema.ExternalReference(target_url=p.public_path(local).as_uri(),available_range=TR(RT(0,p.fps),RT(r['frames'],p.fps)))
        clip=otio.schema.Clip(name=s['id']+' / '+s['name'],media_reference=mr,source_range=TR(RT(r['sourceStart'],p.fps),RT(r['bodyFrames'],p.fps)))
        clip.metadata['sbph']={'shot_id':s['id'],'media_sha256':r['sha256'],'action':s['action'],'handle_policy':r['handlePolicy'],'handle_in':r['handleIn'],'handle_out':r['handleOut']}
        v.append(clip)
    wav=otio.schema.ExternalReference(target_url=p.public_path(p.audio).as_uri(),available_range=TR(RT(0,p.fps),RT(p.frames,p.fps)))
    a.append(otio.schema.Clip(name='Original full WAV / lock this track before timing edits',media_reference=wav,source_range=TR(RT(0,p.fps),RT(p.frames,p.fps))))
    a[0].metadata['sbph']={'media_sha256':sha(p.audio),'role':'original_audio'}
    for e in p.edit.get('events',[]):
        color=otio.schema.MarkerColor.GREEN if e['basis']=='accent' else otio.schema.MarkerColor.CYAN
        v.markers.append(otio.schema.Marker(name=e['id'],marked_range=TR(RT(e['frame'],p.fps),RT(1,p.fps)),color=color,metadata={'sbph':{'basis':e['basis'],'meaning':e['meaning']}}))
    if candidates:
        for e in candidates:
            if e['frame']>=p.frames:continue
            a.markers.append(otio.schema.Marker(name=f"Audio onset candidate / {e['strength']:.2f}",marked_range=TR(RT(e['frame'],p.fps),RT(1,p.fps)),color=otio.schema.MarkerColor.RED,metadata={'sbph':{'basis':'librosa onset candidate','strength':e['strength'],'requires_editorial_judgment':True}}))
    tl.tracks.extend([v,a]);tl.metadata['sbph']={'version':'0.1.0','otio_version':importlib.metadata.version('opentimelineio'),'fps':p.fps,'duration_frames':p.frames,'sourceFingerprint':records['sourceFingerprint'],'native_resolve_import':'not tested on this host','note':'Motion and effects are baked within each shot. Clip timing remains editable. No Resolve track-lock state is implied by OTIO.'}
    return tl


def timeline(p):
    records=validate_shot_set(p)
    tl=build_model(p,records,audio_cues(p));v,a=tl.tracks
    filename=p.data.get('timeline_file','human-edit.otio')
    if Path(filename).name!=filename or not filename.endswith('.otio'):raise ValueError('timeline_file must be an .otio filename')
    output=p.output/filename
    otio.adapters.write_to_file(tl,str(output))
    reread=otio.adapters.read_from_file(str(output))
    if int(reread.duration().rescaled_to(p.fps).value)!=p.frames or len(list(reread.video_tracks()[0]))!=len(p.edit['scenes']):
        raise RuntimeError('OTIO round trip changed the editorial duration or shot count')
    for original,got in zip(p.edit['scenes'],reread.video_tracks()[0]):
        if got.source_range.start_time.value!=p.handles or got.source_range.duration.value!=original['end']-original['start']:
            raise RuntimeError('OTIO round trip changed shot ranges')
    fallback=None
    if 'fcp_xml' in otio.adapters.available_adapter_names():
        fallback=output.with_suffix('.xml');otio.adapters.write_to_file(tl,str(fallback),adapter_name='fcp_xml')
    report={'timeline':str(p.public_path(output)),'frames':p.frames,'fps':p.fps,'videoClips':len(v),'audioClips':len(a),'videoMarkers':len(v.markers),'audioMarkers':len(a.markers),'handleFramesEachSide':p.handles,'otioRoundtrip':'passed','mediaHashes':'passed','fallbackXml':str(p.public_path(fallback)) if fallback else None,'resolveImport':'not tested; app absent from standard locations','sourceEditSha256':records['sourceEditSha256']}
    dump(p.output/'timeline-verification.json',report)
    print(f"OTIO: {len(v)} separate shots, {p.handles}-frame handles, original WAV, {len(v.markers)+len(a.markers)} markers. Read/write roundtrip passed.",flush=True)
    return output
