"""DaVinci Resolve acceptance evidence for a collected handoff.

Two honest paths. `check` drives Resolve through its scripting API (Resolve Studio
only; the free edition refuses external scripts) and measures what it imported.
`record` stores a human's attestations from a manual File > Import > Timeline
session. Neither claims creative approval, and the Resolve API calls here were
written from Blackmagic's scripting README, not exercised on this host.
"""
from pathlib import Path
from urllib.parse import unquote
import os, sys, time
import opentimelineio as otio
from .handoff import check_package
from .project import dump

APPS=['/Applications/DaVinci Resolve','/Applications/DaVinci Resolve.app','~/Applications/DaVinci Resolve.app']
SCRIPT_API='/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting'
SCRIPT_LIB='/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so'
ATTESTATIONS={'imported':'edit.otio imported without errors','linked':'every clip is online (media found)',
    'markersVisible':'markers appear where the handoff placed them','audioLocked':'original audio track locked before timing edits'}


def detect():
    apps=[a for a in APPS if Path(a).expanduser().exists()]
    return {'app':apps,'scriptingModules':(Path(os.environ.get('RESOLVE_SCRIPT_API',SCRIPT_API))/'Modules').is_dir()}


def frames(time_value,fps):return round(time_value.rescaled_to(fps).value)


def expected(folder):
    """What a faithful import of the package's edit.otio must contain."""
    manifest,tl=check_package(folder);fps=manifest['fps']
    def rows(track):
        result=[]
        for item in track:
            if not isinstance(item,otio.schema.Clip):continue
            placed=item.range_in_parent();source=item.trimmed_range()
            result.append({'name':item.name,'start':frames(placed.start_time,fps),'duration':frames(placed.duration,fps),
                'sourceStart':frames(source.start_time,fps),'file':unquote(item.media_reference.target_url)})
        return result
    markers=sorted(frames(m.marked_range.start_time,fps) for t in tl.tracks for m in t.markers)
    return {'fps':fps,'frames':manifest['frames'],'video':rows(tl.video_tracks()[0]),'audio':rows(tl.audio_tracks()[0]),'markers':markers}


def evaluate(facts,exp):
    """Pure comparison of measured Resolve facts with the expected import."""
    checks=[]
    def add(name,ok,detail,warn=False):checks.append({'check':name,'status':'passed' if ok else ('warning' if warn else 'failed'),'detail':detail})
    add('frame rate',abs(facts['fps']-exp['fps'])<1e-6,f"Resolve {facts['fps']} vs handoff {exp['fps']}")
    for kind in ('video','audio'):
        got,want=facts[kind],exp[kind]
        add(kind+' clip count',len(got)==len(want),f'{len(got)} imported vs {len(want)} expected')
        for number,(a,b) in enumerate(zip(got,want),1):
            where=f'{kind} {number} ({b["name"]})'
            add(where+' placement',a['start']==b['start'] and a['duration']==b['duration'],f"start/duration {a['start']}/{a['duration']} vs {b['start']}/{b['duration']}")
            if kind=='video':add(where+' handle in-point',a['leftOffset']==b['sourceStart'],f"source offset {a['leftOffset']} vs {b['sourceStart']}")
            path=a.get('path');add(where+' media online',bool(path) and Path(path).is_file(),str(path))
    missing=sorted(set(exp['markers'])-set(facts['markers']))
    add('markers',not missing,f'{len(exp["markers"])-len(missing)} of {len(exp["markers"])} expected frames present'+(f'; missing {missing[:8]}' if missing else ''),warn=True)
    return checks


def connect():
    api=os.environ.get('RESOLVE_SCRIPT_API',SCRIPT_API)
    os.environ.setdefault('RESOLVE_SCRIPT_LIB',SCRIPT_LIB)
    sys.path.append(api+'/Modules')
    try:import DaVinciResolveScript as dvr
    except ImportError:
        raise ValueError('DaVinciResolveScript is not installed. Install Resolve Studio, or use the manual path: sbph resolve-record (docs/resolve-acceptance.md)') from None
    resolve=dvr.scriptapp('Resolve')
    if resolve is None:
        raise ValueError('Resolve refused the scripting connection. Start Resolve Studio and set Preferences > General > External scripting using = Local. The free edition does not allow it; use sbph resolve-record')
    return resolve


def collect(resolve,folder,name):
    project=resolve.GetProjectManager().GetCurrentProject()
    if project is None:raise ValueError('Open a Resolve project first')
    timeline=project.GetMediaPool().ImportTimelineFromFile(str(Path(folder)/'edit.otio'),
        {'timelineName':name,'importSourceClips':True,'sourceClipsPath':str(Path(folder)/'media')})
    if not timeline:raise ValueError('Resolve refused to import edit.otio')
    origin=timeline.GetStartFrame()
    def items(kind):
        rows=[]
        for item in timeline.GetItemListInTrack(kind,1) or []:
            media=item.GetMediaPoolItem()
            rows.append({'name':item.GetName(),'start':item.GetStart()-origin,'duration':item.GetDuration(),
                'leftOffset':item.GetLeftOffset(),'path':media.GetClipProperty('File Path') if media else None})
        return rows
    facts={'product':resolve.GetProductName(),'version':resolve.GetVersionString(),'fps':float(timeline.GetSetting('timelineFrameRate')),
        'video':items('video'),'audio':items('audio'),'markers':sorted(int(m) for m in (timeline.GetMarkers() or {}))}
    return timeline,facts


def return_summary(folder,returned):
    from .editor_return import compare
    result=compare(folder,returned)
    return {'file':str(returned),'status':result['status'],'comparisonComplete':result['comparisonComplete'],
        'originalAudioPreserved':result['originalAudioPreserved'],'changes':len(result['changes']),'issues':result['issues']}


def stamp():return time.strftime('%Y%m%d-%H%M%S')


def write(folder,report):
    path=Path(folder)/f'resolve-acceptance-{stamp()}.json'
    if path.exists():raise ValueError('Acceptance record already exists; retry in a second')
    dump(path,report);report['file']=str(path);return report


def check(folder):
    """Scripted import into Resolve Studio, measured against the handoff."""
    exp=expected(folder);resolve=connect();name='SBPH acceptance '+stamp()
    timeline,facts=collect(resolve,folder,name);checks=evaluate(facts,exp)
    out=Path(folder)/f'resolve-return-{stamp()}.otio'
    exported=bool(timeline.Export(str(out),resolve.EXPORT_OTIO))
    back=return_summary(folder,out) if exported else None
    failed=[c for c in checks if c['status']=='failed']
    return write(folder,{'schemaVersion':1,'mode':'scripted','status':'failed' if failed or not exported else 'passed',
        'resolve':{'product':facts['product'],'version':facts['version']},'timeline':name,'checks':checks,
        'exportedReturn':back,'limit':'Measured an import of this handoff into Resolve and its OTIO export. Not creative approval, color management, or device playback.'})


def record(folder,version,confirmed,returned=None,text=None):
    """Human attestations from a manual File > Import > Timeline session."""
    check_package(folder)
    if not version:raise ValueError('Name the Resolve edition and version, for example --resolve-version "19.1 Free"')
    back=return_summary(folder,Path(returned).resolve()) if returned else None
    checks=[{'check':key,'status':'attested' if confirmed.get(key) else 'not confirmed','detail':label} for key,label in ATTESTATIONS.items()]
    done=all(confirmed.get(key) for key in ATTESTATIONS)
    return write(folder,{'schemaVersion':1,'mode':'manual','status':'attested' if done else 'incomplete','resolve':{'version':version},
        'checks':checks,'exportedReturn':back,'notes':text,
        'limit':'Human attestation, not measured by the toolkit. Exported-return comparison (if given) is measured.'})


def display(report):
    lines=[f"Resolve acceptance ({report['mode']}): {report['status']} — {report['file']}"]
    lines+=[f"- {c['status']}: {c['check']} — {c['detail']}" for c in report['checks'] if c['status']!='passed' or report['mode']=='manual']
    back=report.get('exportedReturn')
    if back:lines.append(f"Return comparison: {back['status']} (complete: {back['comparisonComplete']}, audio preserved: {back['originalAudioPreserved']})")
    lines.append(report['limit'])
    return '\n'.join(lines)
