"""Collected, relative-reference OTIO handoffs; no source project needed to check."""
from pathlib import Path, PurePosixPath
from collections import Counter
from urllib.parse import quote, unquote, urlsplit
import json, shutil, uuid
import opentimelineio as otio
from .project import dump, sha


def member(root,name):
    if not isinstance(name,str):raise ValueError('Package member must be a relative path')
    parsed=urlsplit(name);path=PurePosixPath(unquote(parsed.path))
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or path.is_absolute() or '..' in path.parts or '\\' in name:
        raise ValueError('Unsafe or nonportable package reference: '+name)
    file=(Path(root)/str(path)).resolve()
    if not file.is_relative_to(Path(root).resolve()):raise ValueError('Package reference escapes its folder')
    return file


def check_package(folder):
    root=Path(folder).resolve();manifest=json.loads((root/'handoff.json').read_text())
    if not isinstance(manifest,dict) or manifest.get('schemaVersion')!=1:raise ValueError('Unsupported handoff package schema')
    if any(type(manifest.get(k)) is not int or manifest[k]<=0 for k in ['fps','frames']):raise ValueError('Package requires positive integer fps and frames')
    files=manifest.get('files')
    if not isinstance(files,dict) or not files:raise ValueError('Package has no file inventory')
    for name,expected in files.items():
        if not isinstance(expected,str) or len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected):raise ValueError('Invalid package file hash')
        file=member(root,name)
        if not file.is_file() or sha(file)!=expected:raise ValueError('Missing or changed package member: '+name)
    timeline=manifest.get('timeline')
    if not isinstance(timeline,str) or not timeline.endswith('.otio') or timeline not in files:raise ValueError('OTIO timeline is not inventoried')
    tl=otio.adapters.read_from_file(str(member(root,timeline)),adapter_name='otio_json')
    if not isinstance(tl,otio.schema.Timeline):raise ValueError('Package requires an OTIO Timeline')
    media=manifest.get('media',[])
    if not isinstance(media,list) or any(not isinstance(row,dict) or not isinstance(row.get('file'),str)
        or row.get('kind') not in ('Video','Audio') or type(row.get('availableFrames')) is not int or row['availableFrames']<=0
        or not isinstance(row.get('sha256'),str) for row in media):raise ValueError('Malformed package media inventory')
    if not media or len(media)!=len(list(tl.find_clips())):raise ValueError('Package media inventory differs from timeline')
    known={row['file']:row for row in media}
    if any(row['kind']=='Video' and (not isinstance(row.get('shotId'),str) or not row['shotId']) for row in media):raise ValueError('Video media requires a shot identity')
    if len(known)!=len(media):raise ValueError('Duplicate package media reference')
    seen=[]
    for clip in tl.find_clips():
        if not isinstance(clip.media_reference,otio.schema.ExternalReference):raise ValueError('Package has an unsupported media reference')
        name=unquote(clip.media_reference.target_url)
        seen.append(name)
        file=member(root,name)
        if name not in known or name not in files or files[name]!=known[name]['sha256']:
            raise ValueError('Uninventoried package media: '+name)
        row=known[name];r=clip.trimmed_range();fps=manifest['fps']
        if r.start_time.rescaled_to(fps).value<0 or r.end_time_exclusive().rescaled_to(fps).value>row['availableFrames']:
            raise ValueError('Package source range exceeds collected media')
        meta=clip.metadata.get('sbph',{})
        if not hasattr(meta,'get') or meta.get('media_sha256')!=row['sha256']:raise ValueError('Package clip identity differs from media')
        if row.get('shotId')!=meta.get('shot_id'):raise ValueError('Package shot identity differs from media')
    if Counter(seen)!=Counter(known.keys()):raise ValueError('Package must reference each collected media file exactly once')
    return manifest,tl


def package(p,destination=None):
    from .validation import validate_shot_set,audio_cues
    from .timeline import build_model
    from .workflow import notes,shot_intent
    records=validate_shot_set(p);tl=build_model(p,records,audio_cues(p))
    dest=Path(destination).resolve() if destination else p.output/'handoffs'/('H'+uuid.uuid4().hex[:12])
    if dest.exists():raise ValueError('Handoff destination already exists; choose a new folder')
    # Complete the source gates before creating anything in the destination.
    dest.parent.mkdir(parents=True,exist_ok=True);dest.mkdir()
    try:
        media=[]
        for scene,clip in zip(p.edit['scenes'],tl.video_tracks()[0]):
            row=records['shots'][scene['id']];source=p.output/'shots'/Path(row['file']).name
            name='media/video/'+source.name;target=dest/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            if sha(target)!=row['sha256']:raise ValueError('Shot changed during collection')
            clip.media_reference.target_url=quote(name,safe='/')
            media.append({'file':name,'sha256':row['sha256'],'shotId':scene['id'],'kind':'Video','availableFrames':row['frames']})
        name='media/audio/original'+p.audio.suffix.lower();target=dest/name;target.parent.mkdir(parents=True,exist_ok=True)
        audio_hash=tl.audio_tracks()[0][0].metadata['sbph']['media_sha256'];shutil.copy2(p.audio,target)
        if sha(target)!=audio_hash:raise ValueError('Original audio changed during collection')
        tl.audio_tracks()[0][0].media_reference.target_url=quote(name,safe='/')
        media.append({'file':name,'sha256':audio_hash,'kind':'Audio','availableFrames':p.frames})
        otio.adapters.write_to_file(tl,str(dest/'edit.otio'))
        dump(dest/'editorial-context.json',{'title':p.edit['title'],'fps':p.fps,'scenes':p.edit['scenes'],'events':p.edit.get('events',[]),'notes':notes(p,True),'intent':[shot_intent(p,s['id']) for s in p.edit['scenes']]})
        (dest/'README.txt').write_text('SBPH portable editorial handoff\n\nKeep this entire folder together. edit.otio uses media/ relative references.\nVideo clips contain baked animation and effects with documented handles.\nAudio is the unchanged original recording; lock it in your editor.\nNative editor import and track locks have not been verified. If your editor\ndoes not resolve relative paths, relink to this folder; do not move media alone.\nExport an OTIO return preserving clip metadata when possible.\nCompare: sbph compare-return /path/to/this-folder --returned /path/to/return.otio\nCheck: sbph package-check /path/to/this-folder\nComparison reports timing and media differences; it does not apply edits.\n',encoding='utf-8')
        manifest={'schemaVersion':1,'title':p.edit['title'],'fps':p.fps,'frames':p.frames,'timeline':'edit.otio','sourceFingerprint':records['sourceFingerprint'],'media':media,'files':{f.relative_to(dest).as_posix():sha(f) for f in sorted(dest.rglob('*')) if f.is_file()},'nativeEditorImport':'not tested'}
        dump(dest/'handoff.json',manifest)
        check_package(dest)
        if p.source_inventory()[0]!=records['sourceFingerprint']:raise ValueError('Sources changed during packaging; retry with a stable project')
        return dest
    except BaseException:
        shutil.rmtree(dest)
        raise
