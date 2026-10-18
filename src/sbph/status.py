"""Read-only orientation. Freshness evidence is distinct from production QA."""
from pathlib import Path
import json
import shlex
import subprocess

from .project import FRAMEWORK,sha
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
            row=records[scene['id']];movie=p.output/'shots'/f"{scene['id']}-{scene['kind']}.mp4"
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
        same=reported is not None and Path(reported).resolve()==movie.resolve()
        result['verification']='saved report matches movie bytes' if same and expected==sha(movie) else 'saved report is for different or changed media'
        result['limit']='Historical report identity only; this command does not repeat its media checks.'
    except (ValueError,OSError,AttributeError,TypeError) as error:result['verification']='unreadable report: '+str(error)
    return result


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
    build=shot_build(p)
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
        scene=p.edit['scenes'][0]
        next_action={'text':'Review one bounded shot; no full rebuild is started.','command':revision_command(p,'shot',scene['id'])}
    return {'project':str(p.config),'title':p.edit['title'],'fps':p.fps,'frames':p.frames,'shots':len(p.edit['scenes']),
        'sourceAudioExists':p.audio.is_file(),'driverExists':p.driver.is_file(),'build':build,'delivery':delivery(p),
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
