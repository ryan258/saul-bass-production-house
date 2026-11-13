"""DaVinci Resolve acceptance evidence for a collected handoff.

Two honest paths. `check` drives Resolve through its scripting API (Resolve Studio
only; the free edition refuses external scripts) and measures what it imported.
`record` stores a human's attestations from a manual File > Import > Timeline
session. Neither claims creative approval, and the Resolve API calls here were
written from Blackmagic's scripting README, not exercised on this host.
"""
from pathlib import Path
from urllib.parse import unquote
import json, os, sys, tempfile, time, uuid
import opentimelineio as otio
from .handoff import check_package
from .project import sha
from .media import locked_output

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
    folder=Path(folder).resolve();manifest,tl=check_package(folder);fps=manifest['fps'];media={r['file']:r for r in manifest['media']}
    def rows(track):
        result=[]
        for item in track:
            if not isinstance(item,otio.schema.Clip):continue
            placed=item.range_in_parent();source=item.trimmed_range()
            result.append({'name':item.name,'start':frames(placed.start_time,fps),'duration':frames(placed.duration,fps),
                'sourceStart':frames(source.start_time,fps),'file':unquote(item.media_reference.target_url),'sha256':media[unquote(item.media_reference.target_url)]['sha256']})
        return result
    markers=sorted(frames(m.marked_range.start_time,fps) for t in tl.tracks for m in t.markers)
    return {'fps':fps,'frames':manifest['frames'],'video':rows(tl.video_tracks()[0]),'audio':rows(tl.audio_tracks()[0]),'markers':markers,
        'trackCounts':{'video':len(tl.video_tracks()),'audio':len(tl.audio_tracks())},'packageIdentity':package_identity(folder,manifest)}


def evaluate(facts,exp):
    """Pure comparison of measured Resolve facts with the expected import."""
    checks=[]
    def add(name,ok,detail,warn=False):checks.append({'check':name,'status':'passed' if ok else ('warning' if warn else 'failed'),'detail':detail})
    add('frame rate',abs(facts['fps']-exp['fps'])<1e-6,f"Resolve {facts['fps']} vs handoff {exp['fps']}")
    for kind in ('video','audio'):
        got,want=facts[kind],exp[kind]
        add(kind+' track count',facts.get('trackCounts',{}).get(kind)==exp['trackCounts'][kind],f"{facts.get('trackCounts',{}).get(kind)} imported vs {exp['trackCounts'][kind]} expected")
        add(kind+' clip count',len(got)==len(want),f'{len(got)} imported vs {len(want)} expected')
        for number,(a,b) in enumerate(zip(got,want),1):
            where=f'{kind} {number} ({b["name"]})'
            add(where+' placement',a['start']==b['start'] and a['duration']==b['duration'],f"start/duration {a['start']}/{a['duration']} vs {b['start']}/{b['duration']}")
            add(where+(' handle in-point' if kind=='video' else ' source in-point'),a['leftOffset']==b['sourceStart'],f"source offset {a['leftOffset']} vs {b['sourceStart']}")
            path=a.get('path');add(where+' media online',bool(path) and Path(path).is_file(),str(path))
            actual=sha(Path(path)) if path and Path(path).is_file() else None
            add(where+' media identity',actual==b['sha256'],f"sha256 {actual} vs {b['sha256']}")
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
    counts={kind:timeline.GetTrackCount(kind) for kind in ('video','audio')}
    def items(kind):
        rows=[]
        for number in range(1,counts[kind]+1):
            for item in timeline.GetItemListInTrack(kind,number) or []:
                media=item.GetMediaPoolItem()
                rows.append({'name':item.GetName(),'track':number,'start':item.GetStart()-origin,'duration':item.GetDuration(),
                    'leftOffset':item.GetLeftOffset(),'path':media.GetClipProperty('File Path') if media else None})
        return rows
    facts={'product':resolve.GetProductName(),'version':resolve.GetVersionString(),'fps':float(timeline.GetSetting('timelineFrameRate')),
        'video':items('video'),'audio':items('audio'),'trackCounts':counts,'markers':sorted(int(m) for m in (timeline.GetMarkers() or {}))}
    return timeline,facts


def return_summary(folder,returned):
    from .editor_return import compare
    result=compare(folder,returned)
    def material(change):
        if change['type']=='timeline_markers':return False
        if change['type']=='edit':return bool(set(change['fields'])-{'markers'})
        if change['type']=='tracks':
            def core(rows):return [{k:v for k,v in r.items() if k not in {'markers','name'}} for r in rows]
            return core(change['before'])!=core(change['after'])
        return True
    significant=[c for c in result['changes'] if material(c)]
    return {'file':str(returned),'status':result['status'],'comparisonComplete':result['comparisonComplete'],
        'originalAudioPreserved':result['originalAudioPreserved'],'changes':len(result['changes']),'materialChanges':len(significant),'issues':result['issues'],
        'returnSha256':result['returnSha256'],'beforeFrames':result['beforeFrames'],'afterFrames':result['afterFrames'],
        'baselineManifestSha256':result['baselineManifestSha256'],'baselineTimelineSha256':result['baselineTimelineSha256']}


def package_identity(folder,manifest=None):
    if manifest is None:manifest,_=check_package(folder)
    return {'handoffSha256':sha(Path(folder)/'handoff.json'),'timelineSha256':manifest['files'][manifest['timeline']],'sourceFingerprint':manifest['sourceFingerprint']}


def return_passed(back):
    return bool(back and back['comparisonComplete'] and back['originalAudioPreserved'] and not back['issues'] and not back['materialChanges'] and back['beforeFrames']==back['afterFrames'])


def measured_return(folder,returned):
    try:return return_summary(folder,returned)
    except (OSError,RuntimeError,ValueError,otio.exceptions.OTIOError) as error:
        return {'file':str(returned),'status':'failed','comparisonComplete':False,'originalAudioPreserved':False,'materialChanges':0,'beforeFrames':None,'afterFrames':None,'changes':0,
            'issues':[{'kind':'comparison_failed','where':'timeline','detail':str(error)}]}


def stamp():return time.strftime('%Y%m%d-%H%M%S')


def write(folder,report):
    path=Path(folder)/f'resolve-acceptance-{stamp()}-{uuid.uuid4().hex[:12]}.json'
    # Link a fully flushed candidate exclusively; no partial report is visible.
    candidate=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',prefix='.acceptance-',dir=folder,delete=False) as handle:
            candidate=Path(handle.name);handle.write(json.dumps(report,indent=2)+'\n');handle.flush();os.fsync(handle.fileno())
        if report.get('packageIdentity') and package_identity(folder)!=report['packageIdentity']:raise ValueError('Handoff package changed before acceptance record save; retry')
        os.link(candidate,path)
    finally:
        if candidate is not None:
            try:candidate.unlink(missing_ok=True)
            except OSError:print('sbph: Acceptance staging retained: '+str(candidate),file=sys.stderr)
    report['file']=str(path);return report


@locked_output
def check(folder):
    """Scripted import into Resolve Studio, measured against the handoff."""
    exp=expected(folder);resolve=connect();name='SBPH acceptance '+stamp()+' '+uuid.uuid4().hex[:8]
    timeline,facts=collect(resolve,folder,name);checks=evaluate(facts,exp)
    # A new directory gives the editor a guaranteed unused export path.
    out=Path(tempfile.mkdtemp(prefix='resolve-return-'+stamp()+'-',dir=Path(folder).resolve()))/'return.otio'
    export_error=None
    try:exported=bool(timeline.Export(str(out),resolve.EXPORT_OTIO))
    except (OSError,RuntimeError,ValueError) as error:exported=False;export_error=str(error)
    back=measured_return(folder,out) if exported else None
    checks.append({'check':'exported return','status':'passed' if return_passed(back) else 'failed','detail':export_error or 'Export must preserve local media identity, enabled structure, timing, and original audio; marker-only changes may warn'})
    if back and back['changes'] and return_passed(back):checks.append({'check':'exported markers or labels','status':'warning','detail':'Marker or track-label changes require visual review'})
    if package_identity(folder)!=exp['packageIdentity']:raise ValueError('Handoff package changed during Resolve acceptance; retry')
    failed=[c for c in checks if c['status']=='failed']
    return write(folder,{'schemaVersion':1,'mode':'scripted','status':'failed' if failed or not exported else 'passed',
        'resolve':{'product':facts['product'],'version':facts['version']},'timeline':name,'packageIdentity':exp['packageIdentity'],'checks':checks,
        'exportedReturn':back,'limit':'Measured an import of this handoff into Resolve and its OTIO export. Not creative approval, color management, or device playback.'})


@locked_output
def record(folder,version,confirmed,returned=None,text=None,accept_edits=False):
    """Human attestations from a manual File > Import > Timeline session."""
    identity=package_identity(folder)
    if not version:raise ValueError('Name the Resolve edition and version, for example --resolve-version "19.1 Free"')
    back=measured_return(folder,Path(returned).resolve()) if returned else None
    checks=[{'check':key,'status':'attested' if confirmed.get(key) else 'not confirmed','detail':label} for key,label in ATTESTATIONS.items()]
    done=all(confirmed.get(key) for key in ATTESTATIONS)
    acceptable=return_passed(back) or bool(accept_edits and back and back['comparisonComplete'] and back['originalAudioPreserved'] and not back['issues'])
    accepted_edits=bool(acceptable and accept_edits and back and back['materialChanges'])
    if back:checks.append({'check':'exported return','status':'passed' if acceptable else 'failed','detail':'Measured local media identity, supported structure, and original audio; editorial changes explicitly accepted' if accepted_edits else 'Measured local media identity, structure, timing, and original audio; material changes require --accept-edits'})
    if package_identity(folder)!=identity:raise ValueError('Handoff package changed during Resolve acceptance; retry')
    return write(folder,{'schemaVersion':1,'mode':'manual','status':'failed' if back and not acceptable else ('attested' if done else 'incomplete'),'resolve':{'version':version},'packageIdentity':identity,
        'checks':checks,'exportedReturn':back,'acceptedEditorialChanges':accepted_edits,'notes':text,
        'limit':'Human attestation, not measured by the toolkit. Exported-return comparison (if given) is measured.'})


def display(report):
    lines=[f"Resolve acceptance ({report['mode']}): {report['status']} — {report['file']}"]
    lines+=[f"- {c['status']}: {c['check']} — {c['detail']}" for c in report['checks'] if c['status']!='passed' or report['mode']=='manual']
    back=report.get('exportedReturn')
    if back:lines.append(f"Return comparison: {back['status']} (complete: {back['comparisonComplete']}, audio preserved: {back['originalAudioPreserved']})")
    lines.append(report['limit'])
    return '\n'.join(lines)
