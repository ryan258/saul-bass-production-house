"""Read-only orientation. Freshness evidence is distinct from production QA."""
from pathlib import Path
import json
import shlex
import subprocess

from .project import FRAMEWORK,sha,shot_filename
from .fingerprint import BUILD_SCHEMA,inventory_changes,format_inventory_changes
from .delivery import delivery_path
from . import workflow as flow


def command(p,name,*args):
    return shlex.join([str(FRAMEWORK/'sbph'),name,str(p.config),*map(str,args)])


def revision_command(p,kind,identifier):
    if p.data.get('renderer')=='motion-canvas':
        shot_id=flow.find_note(p,identifier)['anchor']['shotId'] if kind=='note' else identifier
        return command(p,'shots','--shot',shot_id)
    if not p.driver.is_file():return command(p,'animatic')
    from .drafts import revision_parameters
    selected={'note_id':identifier} if kind=='note' else {'identifier':identifier}
    try:revision_parameters(p,**selected)
    except ValueError as error:
        if '30 seconds' not in str(error):raise
        frame=flow.find_note(p,identifier)['location']['frame'] if kind=='note' else flow.shot(p,identifier)['start']
        start=max(0,frame-round(.5*p.fps));frames=min(5*p.fps,p.frames-start)
        return command(p,'revision','--'+kind,identifier,'--start',start/p.fps,'--duration',frames/p.fps)
    return command(p,'revision','--'+kind,identifier)


def shot_build(p):
    file=p.output/'shots.json'
    if not file.is_file():return {'status':'missing','reason':'No handled-shot manifest.','productionValidation':'not run'}
    try:
        data=json.loads(file.read_text())
        if not isinstance(data,dict):raise ValueError('manifest must be an object')
        if data.get('schemaVersion')!=BUILD_SCHEMA:
            return {'status':'legacy','reason':'Preserved manifest predates the current build schema; no automatic rebuild.','productionValidation':'not run'}
        fingerprint,inventory=p.source_inventory()
        if data.get('sourceFingerprint')!=fingerprint or ('sourceInventory' in data and data['sourceInventory']!=inventory):
            changes=inventory_changes(data.get('sourceInventory'),inventory)
            return {'status':'stale','reason':'Configured sources, settings, or tools changed.',
                'staleChanges':changes,'productionValidation':'not run'}
        records=data.get('shots',{})
        if not isinstance(records,dict) or set(records)!={s['id'] for s in p.edit['scenes']}:
            return {'status':'incomplete','reason':'Not every current shot has a record.','productionValidation':'not run'}
        changed=[]
        for scene in p.edit['scenes']:
            row=records[scene['id']];movie=p.output/'shots'/shot_filename(scene)
            if not isinstance(row,dict):raise ValueError('Malformed shot record: '+scene['id'])
            if not movie.is_file() or sha(movie)!=row.get('sha256'):changed.append(scene['id'])
        return {'status':'changed' if changed else 'matches','changedShots':changed,
            'reason':'Source fingerprint and clip hashes checked; ranges and media metadata require validate.','productionValidation':'not run'}
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as error:
        return {'status':'unverified','reason':str(error),'productionValidation':'not run'}


def delivery(p):
    movie=delivery_path(p)
    result={'file':str(movie),'exists':movie.is_file(),'verification':'not checked'}
    report_file=p.output/'media-verification.json'
    if not movie.is_file() or not report_file.is_file():return result
    try:
        report=json.loads(report_file.read_text())
        if not isinstance(report,dict):raise ValueError('Delivery report must be an object')
        expected=report.get('deliverySha256',report.get('masterSha256'))
        reported=report.get('delivery',report.get('master'))
        if expected is not None and not isinstance(expected,str):raise ValueError('Delivery report hash must be text')
        if reported is not None and (not isinstance(reported,str) or not reported):raise ValueError('Delivery report path must be non-empty text')
        same=reported is not None and Path(reported).resolve() in {movie.resolve(),p.public_path(movie).resolve()}
        result['verification']='saved report matches movie bytes' if same and expected==sha(movie) else 'saved report is for different or changed media'
        result['sourceFingerprint']=report.get('sourceFingerprint');result['reportStatus']=report.get('status')
        result['limit']='Historical report identity only; this command does not repeat its media checks.'
    except (ValueError,OSError,AttributeError,TypeError) as error:result['verification']='unreadable report: '+str(error)
    return result


def production_action(p,build,delivered):
    """Choose the next stage from saved evidence; never executes its command."""
    if build['status']!='matches':return None
    fingerprint=p.source_inventory()[0];movie=delivery_path(p);assembled=p.output/'assembly.mp4'
    timeline=p.output/p.data.get('timeline_file','human-edit.otio')
    def action(stage,text,name=None,*args):return {'stage':stage,'text':text,'command':command(p,name,*args) if name else None}
    timeline_current=False
    try:
        timeline_report=json.loads((p.output/'timeline-verification.json').read_text())
        timeline_current=timeline.is_file() and timeline_report.get('sourceFingerprint')==fingerprint and timeline_report.get('timelineSha256')==sha(timeline)
    except (ValueError,OSError,AttributeError):pass
    if not timeline_current:return action('timeline','Export the current handled shots as an editable timeline.','timeline')
    if not assembled.is_file():return action('assemble','Assemble the current shot bodies for review.','assemble')
    if not movie.is_file():return action('delivery','Restore or configure the selected delivery: '+str(movie))
    if delivered.get('verification')!='saved report matches movie bytes' or delivered.get('sourceFingerprint')!=fingerprint or delivered.get('reportStatus')!='passed':
        return action('check','Check the current delivery and save its media evidence.','check')
    conform_file=p.output/'assembly-verification.json';conform=None
    if conform_file.is_file():
        try:
            candidate=json.loads(conform_file.read_text())
            if candidate.get('sourceFingerprint')==fingerprint and candidate.get('sha256')==sha(assembled) and candidate.get('status') in {'passed','passed_with_exclusions'}:
                from .delivery import reference_path
                reference=reference_path(p) if p.data.get('reference') or p.data.get('master') else Path(candidate.get('referenceLocal',candidate.get('reference','')))
                offset=(p.data.get('verification') or {}).get('conform_first_frame_offset',0)
                if reference.is_file() and sha(reference)==candidate.get('referenceSha256') and candidate.get('firstFrameOffset',0)==offset:conform=candidate
        except (ValueError,OSError,AttributeError):pass
    if conform is None:
        if p.data.get('reference') or p.data.get('master'):return action('conform','Conform against the configured viewing reference.','conform')
        return action('conform','Choose an independent viewing reference and run conform; no full-fidelity reference check is recorded.')
    from .evidence import screening_status
    if screening_status(p,movie,fingerprint) is None:
        text='Watch the complete delivery and review first cut frames, then record your screening.'
        if conform.get('firstFrameReviewRequired'):text+=' Conform has explicit first-frame exclusions.'
        return action('screening',text,'screen-record','--screened','--first-cuts-reviewed')
    from .handoff import check_package
    import opentimelineio as otio
    packages=[]
    for file in sorted((p.output/'handoffs').glob('*/handoff.json'),key=lambda f:f.stat().st_mtime_ns,reverse=True):
        try:
            data=json.loads(file.read_text())
            if data.get('sourceFingerprint')==fingerprint:
                check_package(file.parent);packages.append(file)
        except (ValueError,OSError,AttributeError,RuntimeError,otio.exceptions.OTIOError):continue
    if not packages:return action('package','Collect the current edit and media into a portable handoff.','package')
    for file in packages:
        identity=sha(file)
        for receipt in file.parent.glob('resolve-acceptance-*.json'):
            try:
                data=json.loads(receipt.read_text());back=data.get('exportedReturn') or {}
                if data.get('status') in {'passed','attested'} and data.get('packageIdentity',{}).get('handoffSha256')==identity and back.get('comparisonComplete') is True and back.get('originalAudioPreserved') is True:
                    return action('recorded','Screening and Resolve evidence are recorded for this build; inspect saved evidence before any release.','evidence')
            except (ValueError,OSError,AttributeError):continue
    return {'stage':'resolve','text':'Complete Resolve acceptance for '+str(packages[0].parent)+'; choose the documented Studio or manual path.',
        'command':shlex.join([str(FRAMEWORK/'sbph'),'resolve-check',str(packages[0].parent)])}


def snapshot(p):
    errors=[];open_notes=[];saved=None;artifacts=[];intent={}
    for name in ['notes','resume','intent','artifacts']:
        try:
            if name=='notes':open_notes=flow.notes(p)
            elif name=='resume':saved=flow.checkpoint(p)
            elif name=='intent':intent=flow.intents(p)
            else:
                from .drafts import artifact_status
                artifacts=[artifact_status(p,row) for row in flow.read_state(p,'artifacts')['items'][-5:]]
        except (ValueError,OSError,KeyError,TypeError) as error:errors.append(str(error))
    build=shot_build(p);delivered=delivery(p)
    actionable=[n for n in open_notes if n['location']['frame'] is not None]
    selected=None
    if saved:
        if saved.get('noteId'):
            try:
                note=flow.find_note(p,saved['noteId'])
                if note['status']=='open' and note['location']['frame'] is not None:selected=('note',note['id'],saved['text'])
            except ValueError as error:errors.append(str(error))
        elif saved.get('anchor') and saved['location']['frame'] is not None:selected=('shot',saved['anchor']['shotId'],saved['text'])
        elif not saved.get('anchor'):selected=('project',None,saved['text'])
    if selected is None and actionable:selected=('note',actionable[0]['id'],actionable[0]['text'])
    if errors:
        next_action={'text':'Review the workflow record error before editing planning records.','command':None}
    elif not p.audio.is_file():
        next_action={'text':'Prepare or restore source audio: '+str(p.audio),'command':None}
    elif saved and saved.get('anchor') and saved['location']['frame'] is None:
        next_action={'text':'Saved checkpoint anchor needs review: '+saved['location']['status'],'command':command(p,'notes','--all') if saved.get('noteId') else None}
    elif selected:
        kind,identifier,text=selected
        next_action={'text':text,'command':None if kind=='project' else revision_command(p,kind,identifier)}
    elif saved and not saved.get('anchor'):
        next_action={'text':saved['text'],'command':None}
    elif open_notes:
        next_action={'text':'Review unresolved note anchors before choosing a preview.','command':command(p,'notes')}
    elif p.data.get('renderer')!='motion-canvas' and not p.driver.is_file():
        next_action={'text':'Block out the story with placeholder cards; the renderer is not available yet.','command':command(p,'animatic')}
    else:
        try:next_action=production_action(p,build,delivered)
        except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as error:
            errors.append(str(error));next_action={'text':'Inspect the saved production evidence before continuing.','command':None}
        if next_action is None:
            scene=p.edit['scenes'][0]
            next_action={'text':'Review one bounded shot; no full rebuild is started.','command':revision_command(p,'shot',scene['id'])}
    return {'project':str(p.config),'title':p.edit['title'],'fps':p.fps,'frames':p.frames,'shots':len(p.edit['scenes']),
        'sourceAudioExists':p.audio.is_file(),'driverExists':p.driver.is_file(),'build':build,'delivery':delivered,
        'checkpoint':saved,'openNotes':open_notes,'intentShots':list(intent),'orphanedIntentShots':sorted(set(intent)-{s['id'] for s in p.edit['scenes']}),
        'recentDrafts':artifacts,'errors':errors,'nextAction':next_action,
        'limit':'Read-only source/hash evidence; no encoding, probing, native editor acceptance, or production validation was performed.'}


def display(data,brief=False):
    lines=[f"{data['title']} — {data['shots']} shots / {data['frames']/data['fps']:.2f}s at {data['fps']} fps",
        'Next: '+data['nextAction']['text']]
    if data['nextAction']['command']:lines.append(data['nextAction']['command'])
    lines.append('Handled build: '+data['build']['status']+' — '+data['build']['reason'])
    for change in format_inventory_changes(data['build'].get('staleChanges',[]),limit=6 if brief else 12):
        lines.append('  '+change)
    lines.append('Delivery: '+data['delivery']['file']+(' (present)' if data['delivery']['exists'] else ' (missing)'))
    if data['checkpoint']:lines.append('Saved checkpoint: '+data['checkpoint']['text'])
    lines.append(f"Open notes: {len(data['openNotes'])}")
    for note in data['openNotes'][:3 if brief else 10]:
        lines.append(f"  {note['id']} / {note['anchor']['shotId']} / {note['location']['timecode'] or note['location']['status']}: {note['text']}")
    for row in data['recentDrafts'][-2:]:lines.append(f"Draft {row['id']}: {row['status']} — {row['file']}")
    for error in data['errors']:lines.append('Record error: '+error)
    lines.append('Production QA and human acceptance are separate checks.')
    return '\n'.join(lines)
