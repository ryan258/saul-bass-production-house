"""Shared, read-only production gates. No caller may bless legacy evidence."""
from fractions import Fraction
from pathlib import Path
import json
import math

from .fingerprint import BUILD_SCHEMA
from .project import sha


def validate_edit(p):
    if not isinstance(p.edit.get('title'),str) or not p.edit['title']:
        raise ValueError('Edit title must be a non-empty string')
    for scene in p.edit['scenes']:
        for key in ['kind','name','action']:
            if not isinstance(scene.get(key),str) or not scene[key]:
                raise ValueError(f"Shot {scene['id']} requires {key}")
    for event in p.edit.get('events',[]):
        if type(event.get('frame')) is not int or not 0<=event['frame']<p.frames:
            raise ValueError('Event frame must be inside the edit')
        for key in ['id','basis','meaning']:
            if not isinstance(event.get(key),str):raise ValueError('Event requires '+key)


def validate_source_audio(p):
    from .media import probe
    streams=[s for s in probe(p.audio)['streams'] if s['codec_type']=='audio']
    if len(streams)!=1:raise ValueError('Source must have exactly one audio stream')
    stream=streams[0]
    if 'duration_ts' in stream and 'time_base' in stream:
        duration=Fraction(stream['duration_ts'])*Fraction(stream['time_base'])
    elif 'duration' in stream:
        duration=Fraction(stream['duration'])
    else:raise ValueError('Source audio has no verifiable duration')
    if duration+Fraction(1,int(stream['sample_rate']))<Fraction(p.frames,p.fps):
        raise ValueError('Source audio is shorter than the editorial timeline')
    return stream


def validate_shot_set(p):
    """Check current source identity, all ranges, hashes, and decoded metadata.

    Used before assembly, interchange, conform, or delivery verification writes
    anything. Legacy manifests are preserved, but require a deliberate rebuild.
    """
    validate_edit(p)
    path=p.output/'shots.json'
    if not path.is_file():raise ValueError('Shot manifest is missing; render shots first')
    manifest=json.loads(path.read_text())
    if not isinstance(manifest,dict):raise ValueError('Shot manifest must be an object')
    if manifest.get('schemaVersion')!=BUILD_SCHEMA:
        raise ValueError('Legacy shot manifest: rebuild all shots with build schema 2; existing outputs have not been changed')
    fingerprint,inventory=p.source_inventory()
    if manifest.get('sourceFingerprint')!=fingerprint or manifest.get('sourceInventory')!=inventory:
        from .fingerprint import inventory_changes,format_inventory_changes
        changes=inventory_changes(manifest.get('sourceInventory'),inventory)
        detail='; '.join(format_inventory_changes(changes,limit=8))
        raise ValueError('Stale shot build: '+(detail or 'build fingerprint changed')+'; refresh shots with shots --resume before export')
    from .shot_backend import renderer_record
    if manifest.get('fps')!=p.fps or manifest.get('sourceEditSha256')!=sha(p.root/p.data.get('edit','data/edit.json')) or any(manifest.get(k)!=v for k,v in renderer_record(p).items()):
        raise ValueError('Shot manifest does not match the current edit or renderer')
    records=manifest.get('shots',{})
    if not isinstance(records,dict) or set(records)!={s['id'] for s in p.edit['scenes']}:
        raise ValueError('Shot set is incomplete or contains unexpected shots; render all required shots')
    for scene in p.edit['scenes']:
        validate_shot_record(p,scene,records[scene['id']],fingerprint)
    validate_source_audio(p)
    return manifest


def validate_shot_record(p,scene,row,fingerprint,movie=None):
    """The same record/media gate is used for reuse and complete-set export."""
    from .media import probe
    body=scene['end']-scene['start']
    expected={'frames':body+2*p.handles,'bodyFrames':body,'handleIn':p.handles,
        'handleOut':p.handles,'sourceStart':p.handles,'timelineStart':scene['start'],'fps':p.fps}
    if not isinstance(row,dict):raise ValueError('Malformed shot record: '+scene['id'])
    if row.get('id')!=scene['id'] or row.get('sourceFingerprint')!=fingerprint:
        raise ValueError('Stale shot '+scene['id'])
    if any(type(row.get(k)) is not int or row[k]!=value for k,value in expected.items()):
        raise ValueError('Invalid frame/handle ranges for shot '+scene['id'])
    if not isinstance(row.get('handlePolicy'),str):raise ValueError('Missing handle policy for shot '+scene['id'])
    filename=f"{scene['id']}-{scene['kind']}.mp4"
    if not isinstance(row.get('file'),str) or Path(row['file']).name!=filename:
        raise ValueError('Unexpected media filename for shot '+scene['id'])
    file=Path(movie) if movie is not None else p.output/'shots'/filename
    if not file.is_file() or sha(file)!=row.get('sha256'):
        raise ValueError('Missing or changed media: '+str(file))
    try:
        video=next((s for s in probe(file)['streams'] if s['codec_type']=='video'),None)
        valid=video is not None and int(video.get('nb_frames',-1))==expected['frames'] \
            and Fraction(video['avg_frame_rate'])==p.fps \
            and (video['width'],video['height'])==(p.width,p.height)
    except (KeyError,TypeError,ValueError,ZeroDivisionError) as error:
        raise ValueError('Unverifiable shot media metadata: '+scene['id']) from error
    if not valid:raise ValueError('Shot media metadata differs from the build contract: '+scene['id'])
    if sha(file)!=row['sha256']:raise ValueError('Shot media changed during validation: '+scene['id'])
    return row


def audio_cues(p):
    path=p.output/'audio-cues.json'
    if not path.exists():return []
    data=json.loads(path.read_text())
    if data.get('sourceSha256')!=sha(p.audio):raise ValueError('Audio changed; rerun analysis and review the edit')
    result=[]
    for cue in data['markerCandidates']:
        seconds=cue.get('seconds')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<0:
            raise ValueError('Audio cues require nonnegative seconds; rerun analysis')
        result.append({**cue,'frame':round(seconds*p.fps)})
    return result
