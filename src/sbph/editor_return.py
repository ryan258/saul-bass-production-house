"""Read-only editorial comparison against an immutable collected handoff."""
from collections import Counter, defaultdict
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import unquote,urlsplit
import math
import opentimelineio as otio
from .handoff import check_package
from .project import sha


def local_media(url,timeline_file):
    parsed=urlsplit(url)
    if parsed.scheme not in {'','file'} or parsed.netloc not in {'','localhost'}:return None
    if parsed.query or parsed.fragment:return None
    file=Path(unquote(parsed.path))
    return file if file.is_absolute() else Path(timeline_file).parent/file


def relinked(folder,url,manifest):
    """An editor on another machine exports absolute paths (even C:\\...). Find the collected file by its unique name."""
    name=PurePosixPath(unquote(urlsplit(url).path).replace('\\','/')).name
    found=[Path(folder)/row['file'] for row in manifest['media'] if PurePosixPath(row['file']).name==name]
    return found[0] if len(found)==1 and found[0].is_file() else None


def frame(time,fps):
    value=time.rescaled_to(fps).value
    if not math.isfinite(value):raise ValueError('Non-finite editorial time')
    rounded=round(value)
    if abs(value-rounded)>1e-6:raise ValueError('Editorial time does not fall on a baseline frame boundary')
    return rounded


def inspect(tl,file,manifest,baseline=False,folder=None):
    fps=manifest['fps'];known=manifest['media'];rows=[];issues=[];gaps=[];structure=[]
    counts=Counter();by_hash=defaultdict(list)
    for row in known:by_hash[row['sha256']].append(row)
    if not isinstance(tl,otio.schema.Timeline):raise ValueError('Return must contain an OTIO Timeline')
    def problem(kind,where,detail):issues.append({'kind':kind,'where':where,'detail':detail})
    if tl.global_start_time and tl.global_start_time.rate!=fps:
        problem('rate_changed','timeline','Global timeline rate differs from the handoff')
    if tl.tracks.source_range is not None or tl.tracks.effects:
        problem('unsupported','timeline','Stack trims/effects require manual review')
    for index,track in enumerate(tl.tracks):
        if not isinstance(track,otio.schema.Track):
            problem('unsupported',f'track {index}','Nested stacks are not compared');continue
        kind=track.kind;ordinal=counts[kind];counts[kind]+=1;track_key=f'{kind}:{ordinal}'
        structure.append({'track':track_key,'name':track.name,'enabled':track.enabled,'markers':[m.to_json_string() for m in track.markers]})
        if not track.enabled:problem('disabled',track_key,'Track disabled')
        if track.source_range is not None or track.effects:
            problem('unsupported',track_key,'Track trims/effects require manual review')
        for pos,item in enumerate(track):
            where=f'{track_key}/{pos}'
            try:
                parent=item.range_in_parent();start=frame(parent.start_time,fps)
                duration=frame(parent.duration,fps)
            except (ValueError,RuntimeError) as error:
                problem('unsupported',where,str(error));continue
            if isinstance(item,otio.schema.Gap):
                gaps.append({'track':track_key,'timelineStart':start,'duration':duration});continue
            if not isinstance(item,otio.schema.Clip):
                problem('unsupported',where,item.schema_name()+' requires manual review');continue
            if item.effects:problem('unsupported',where,'Clip effects or retimes require manual review')
            if not item.enabled:problem('disabled',where,'Clip disabled')
            if not isinstance(item.media_reference,otio.schema.ExternalReference):
                problem('unmatched',where,'Missing or unsupported media reference');continue
            meta=item.metadata.get('sbph',{})
            if not hasattr(meta,'get'):
                problem('unmatched',where,'Malformed SBPH clip metadata');meta={}
            declared=meta.get('media_sha256');shot_id=meta.get('shot_id')
            if declared is not None and not isinstance(declared,str):
                problem('unmatched',where,'Malformed retained media identity');declared=None
            media=local_media(item.media_reference.target_url,file)
            if folder is not None and (media is None or not media.is_file()):media=relinked(folder,item.media_reference.target_url,manifest) or media
            actual=sha(media) if media is not None and media.is_file() else None
            if not baseline and actual is None:problem('unverified_media',where,'Media is unavailable locally; relink before accepting the return')
            if actual and declared and actual!=declared:problem('media_changed',where,'Returned media bytes differ from retained clip identity')
            identity=actual or declared;candidates=by_hash.get(identity,[])
            if shot_id:
                candidates=[r for r in candidates if r.get('shotId')==shot_id]
            candidates=[r for r in candidates if r['kind']==kind]
            if len(candidates)!=1:
                problem('unmatched',where,'Media identity is unknown, conflicting, or ambiguous; clip names are not identity')
                rows.append({'key':None,'name':item.name,'track':track_key,'timelineStart':start,'duration':duration});continue
            source=candidates[0];key=source.get('shotId','original_audio')
            try:
                sr=item.trimmed_range();source_start=frame(sr.start_time,fps);source_duration=frame(sr.duration,fps)
            except (ValueError,RuntimeError) as error:
                problem('unsupported',where,str(error));continue
            if kind=='Video' and any(t.rate!=fps for t in [sr.start_time,sr.duration]):
                problem('rate_changed',where,'Video source rate differs from the baseline; frame conversion requires review')
            if source_start<0 or source_start+source_duration>source['availableFrames']:
                problem('handle_overrun',where,'Source range exceeds collected media handles')
            if source_duration!=duration:problem('unsupported',where,'Timeline and source durations differ')
            rows.append({'key':key,'kind':kind,'name':item.name,'track':track_key,'timelineStart':start,'sourceStart':source_start,'duration':source_duration,'enabled':item.enabled,'markers':[m.to_json_string() for m in item.markers]})
    return {'clips':rows,'issues':issues,'gaps':gaps,'tracks':structure}


def compare(folder,returned):
    manifest,baseline=check_package(folder);returned=Path(returned).resolve()
    if returned.suffix.lower()!='.otio':raise ValueError('Return comparison currently requires an .otio export')
    original_hash=sha(returned)
    edited=otio.adapters.read_from_file(str(returned),adapter_name='otio_json')
    before=inspect(baseline,Path(folder)/manifest['timeline'],manifest,True)
    after=inspect(edited,returned,manifest,folder=folder)
    if before['issues']:raise ValueError('Baseline package timeline is not a supported comparison baseline')
    old=defaultdict(list);new=defaultdict(list)
    for row in before['clips']:old[row['key']].append(row)
    for row in after['clips']:
        if row['key'] is not None:new[row['key']].append(row)
    changes=[]
    for key in sorted(old.keys()|new.keys()):
        a,b=old[key],new[key]
        if len(a)!=len(b):changes.append({'clip':key,'type':'occurrences','before':len(a),'after':len(b)})
        for occurrence,(x,y) in enumerate(zip(a,b),1):
            delta={field:{'before':x.get(field),'after':y.get(field)} for field in ['track','timelineStart','sourceStart','duration','enabled','markers'] if x.get(field)!=y.get(field)}
            if delta:changes.append({'clip':key,'occurrence':occurrence,'type':'edit','fields':delta})
    def global_start(tl):return tl.global_start_time.to_seconds() if tl.global_start_time else 0
    if global_start(baseline)!=global_start(edited):changes.append({'type':'global_start','beforeSeconds':global_start(baseline),'afterSeconds':global_start(edited)})
    if before['gaps']!=after['gaps']:changes.append({'type':'gaps','before':before['gaps'],'after':after['gaps']})
    if before['tracks']!=after['tracks']:changes.append({'type':'tracks','before':before['tracks'],'after':after['tracks']})
    if [m.to_json_string() for m in baseline.tracks.markers]!=[m.to_json_string() for m in edited.tracks.markers]:
        changes.append({'type':'timeline_markers'})
    try:duration=frame(edited.duration(),manifest['fps'])
    except ValueError as error:
        duration=None;after['issues'].append({'kind':'unsupported','where':'timeline','detail':str(error)})
    audio=new.get('original_audio',[])
    audio_unchanged=(len(audio)==1 and all(audio[0].get(k)==v for k,v in {'timelineStart':0,'sourceStart':0,'duration':manifest['frames'],'enabled':True,'track':'Audio:0'}.items())
        and len([r for r in after['clips'] if r.get('kind')=='Audio'])==1 and not any(i['where'].startswith('Audio:') or i['where']=='timeline' for i in after['issues']))
    # Comparison reads only; detect an export being replaced during inspection.
    if sha(returned)!=original_hash:raise ValueError('Returned timeline changed during comparison; retry')
    return {'schemaVersion':1,'baselineFingerprint':manifest['sourceFingerprint'],'returnSha256':original_hash,'fps':manifest['fps'],'beforeFrames':manifest['frames'],'afterFrames':duration,
        'status':'needs_review' if changes or after['issues'] else 'unchanged','comparisonComplete':not any(i['kind'] in {'unsupported','unmatched','rate_changed','unverified_media','media_changed'} for i in after['issues']),
        'originalAudioPreserved':audio_unchanged,'changes':changes,'issues':after['issues'],'returnedClips':after['clips'],
        'limits':'OTIO timing, structure, and local media identity comparison only. No edits applied; no native editor, rendered picture, audio mix, or creative approval implied.'}


def display(report):
    lines=[f"Editor return: {report['status']} / {report['beforeFrames']} → {report['afterFrames']} frames at {report['fps']} fps",
        f"Original audio placement and bytes: {'preserved' if report['originalAudioPreserved'] else 'requires review'}"]
    def brief(tracks):return ', '.join(f"{t['track']} ({len(t['markers'])} markers)" for t in tracks)
    for row in report['changes']:
        if row['type']=='tracks':detail=f" / [{brief(row['before'])}] → [{brief(row['after'])}]"
        else:detail=f" / {row['fields']}" if 'fields' in row else f" / {row.get('before')} → {row.get('after')}"
        lines.append(f"- {row.get('clip','Timeline')}: {row['type']}"+detail)
    for issue in report['issues']:lines.append(f"- {issue['kind']} at {issue['where']}: {issue['detail']}")
    lines.append(report['limits'])
    return '\n'.join(lines)
