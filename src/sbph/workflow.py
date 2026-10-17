"""Small, local planning records. Reading these never creates project files."""
from contextlib import contextmanager
from datetime import datetime,timezone
from fractions import Fraction
from pathlib import Path
import json
import re

from .project import dump,sha

INTENT_FIELDS=('goal','obstacle','change','emotion','framing','exit_condition')
KINDS={'n':'note','t':'timing','c':'clarity','v':'continuity','a':'action','s':'sound'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def state_path(p,name):
    return p.root/'.sbph'/f'{name}.json'


def read_state(p,name):
    path=state_path(p,name)
    if not path.exists():return {'schemaVersion':1,'items':[]}
    try:data=json.loads(path.read_text())
    except (ValueError,OSError) as error:raise ValueError(f'Cannot read {path}: {error}') from error
    if not isinstance(data,dict) or data.get('schemaVersion')!=1 or not isinstance(data.get('items'),list) or not all(isinstance(row,dict) for row in data['items']):
        raise ValueError('Unsupported or malformed workflow record: '+str(path))
    return data


@contextmanager
def write_lock(p):
    folder=p.root/'.sbph';folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'.write.lock'
    try:stream=lock.open('x')
    except FileExistsError:raise ValueError('Another workflow edit holds '+str(lock)+'; inspect it before removing a stale lock') from None
    try:
        with stream:stream.write(now())
        yield
    finally:lock.unlink(missing_ok=True)


def shot(p,identifier):
    result=next((s for s in p.edit['scenes'] if s['id']==identifier),None)
    if result is None:raise ValueError('Unknown shot ID: '+str(identifier))
    return result


def timecode(frame,fps):
    seconds,subframe=divmod(frame,fps)
    hours,remainder=divmod(seconds,3600);minutes,seconds=divmod(remainder,60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}:{subframe:02d}'


def parse_time(value,fps):
    """Integer-rate timecode, decimal seconds/MM:SS, or explicit 48f frames."""
    try:
        value=str(value).strip()
        if re.fullmatch(r'\d+f',value):return int(value[:-1])
        fields=value.split(':')
        if len(fields)==4:
            h,m,s,f=map(int,fields)
            if min(h,m,s,f)<0 or m>=60 or s>=60 or f>=fps:raise ValueError()
            return ((h*60+m)*60+s)*fps+f
        if len(fields)==2:
            minutes=int(fields[0]);seconds=Fraction(fields[1])
            if minutes<0 or not 0<=seconds<60:raise ValueError()
            seconds+=minutes*60
        elif len(fields)==1:seconds=Fraction(value.removesuffix('s'))
        else:raise ValueError()
        if seconds<0:raise ValueError()
        return round(seconds*fps)
    except (ValueError,ZeroDivisionError):
        raise ValueError('Use seconds, MM:SS, HH:MM:SS:FF, or frames such as 48f') from None


def anchor(p,identifier=None,at=None):
    frame=parse_time(at,p.fps) if at is not None else None
    if identifier is not None:
        scene=shot(p,identifier)
        if frame is None:frame=scene['start']
    elif frame is not None:
        scene=next((s for s in p.edit['scenes'] if s['start']<=frame<s['end']),None)
        if scene is None:raise ValueError('Note time is outside the edit')
    else:raise ValueError('Choose --shot or --at')
    if not scene['start']<=frame<scene['end']:raise ValueError('Time must fall inside the selected shot')
    return {'shotId':scene['id'],'localFrame':frame-scene['start'],'originalFrame':frame,'originalShotStart':scene['start'],'fps':p.fps}


def locate(p,point):
    if not isinstance(point,dict):raise ValueError('Malformed note/checkpoint anchor')
    scene=next((s for s in p.edit['scenes'] if s['id']==point.get('shotId')),None)
    local=point.get('localFrame')
    if scene is None:return {'status':'orphaned','frame':None,'timecode':None}
    if point.get('fps')!=p.fps:return {'status':'rate_changed','frame':None,'timecode':None}
    if type(local) is not int or not 0<=local<scene['end']-scene['start']:
        return {'status':'outside_shot','frame':None,'timecode':None}
    frame=scene['start']+local
    return {'status':'current' if scene['start']==point.get('originalShotStart') else 'retimed','frame':frame,'timecode':timecode(frame,p.fps)}


def notes(p,include_resolved=False):
    rows=read_state(p,'notes')['items'];seen=set();result=[]
    for row in rows:
        if not re.fullmatch(r'N[1-9]\d*',str(row.get('id'))) or row['id'] in seen or row.get('status') not in {'open','resolved'} or not isinstance(row.get('text'),str):
            raise ValueError('Malformed note in '+str(state_path(p,'notes')))
        seen.add(row['id'])
        located=locate(p,row.get('anchor'))
        if include_resolved or row['status']=='open':result.append({**row,'location':located})
    return result


def find_note(p,identifier):
    row=next((n for n in notes(p,True) if n['id']==identifier.upper()),None)
    if row is None:raise ValueError('Unknown note ID: '+str(identifier))
    return row


def add_note(p,text,identifier=None,at=None,kind='note'):
    if not isinstance(text,str) or not text.strip():raise ValueError('A note needs --text')
    kind=KINDS.get(kind.lower(),kind.lower())
    if kind not in set(KINDS.values()):raise ValueError('Note kind must be note, timing, clarity, continuity, action, or sound (n/t/c/v/a/s)')
    point=anchor(p,identifier,at)
    with write_lock(p):
        existing=notes(p,True)
        number=max([int(n['id'][1:]) for n in existing],default=0)+1
        row={'id':f'N{number}','status':'open','kind':kind,'text':text.strip(),'anchor':point,'createdAt':now()}
        data=read_state(p,'notes');data['items'].append(row);dump(state_path(p,'notes'),data)
    return {**row,'location':locate(p,point)}


def resolve_note(p,identifier,text=None):
    with write_lock(p):
        selected=find_note(p,identifier);data=read_state(p,'notes')
        row=next(n for n in data['items'] if n['id']==selected['id'])
        row.update(status='resolved',resolvedAt=now())
        if text:row['resolution']=text
        dump(state_path(p,'notes'),data)
    return row


def reanchor_note(p,identifier,shot_id=None,at=None):
    point=anchor(p,shot_id,at)
    with write_lock(p):
        selected=find_note(p,identifier);data=read_state(p,'notes')
        row=next(n for n in data['items'] if n['id']==selected['id'])
        row.setdefault('anchorHistory',[]).append({'anchor':row['anchor'],'changedAt':now()})
        row['anchor']=point;dump(state_path(p,'notes'),data)
    return {**row,'location':locate(p,point)}


def intents(p):
    rows=read_state(p,'intent')['items'];result={}
    for row in rows:
        if not isinstance(row.get('shotId'),str) or row['shotId'] in result or not isinstance(row.get('fields'),dict):
            raise ValueError('Malformed shot intent record')
        if any(k not in INTENT_FIELDS or not isinstance(v,str) for k,v in row['fields'].items()):raise ValueError('Invalid shot intent field')
        result[row['shotId']]=row['fields']
    return result


def shot_intent(p,identifier):
    scene=shot(p,identifier);base=scene.get('intent',{})
    if not isinstance(base,dict) or any(k not in INTENT_FIELDS or not isinstance(v,str) for k,v in base.items()):
        raise ValueError('Shot intent must contain optional text fields: '+', '.join(INTENT_FIELDS))
    return {'shotId':identifier,'action':scene.get('action',''),'fields':{**base,**intents(p).get(identifier,{})}}


def set_intent(p,identifier,fields):
    shot(p,identifier)
    if not fields or any(k not in INTENT_FIELDS or not isinstance(v,str) for k,v in fields.items()):raise ValueError('Choose at least one text intent field')
    with write_lock(p):
        intents(p);data=read_state(p,'intent')
        row=next((r for r in data['items'] if r['shotId']==identifier),None)
        if row is None:row={'shotId':identifier,'fields':{}};data['items'].append(row)
        row['fields'].update(fields);row['updatedAt']=now();dump(state_path(p,'intent'),data)
    return shot_intent(p,identifier)


def checkpoint(p):
    rows=read_state(p,'resume')['items']
    if not rows:return None
    row=rows[-1]
    if not isinstance(row.get('text'),str):raise ValueError('Malformed resume checkpoint')
    if row.get('noteId'):row={**row,'anchor':find_note(p,row['noteId'])['anchor']}
    return {**row,'location':locate(p,row['anchor']) if row.get('anchor') else None}


def save_checkpoint(p,identifier=None,note_id=None,text=None):
    if identifier and note_id:raise ValueError('Choose a shot or a note for the checkpoint')
    row={'text':text.strip() if text else '','savedAt':now()}
    if note_id:
        note=find_note(p,note_id)
        if note['location']['frame'] is None:raise ValueError('Note anchor needs review: '+note['location']['status'])
        row.update(noteId=note['id'],anchor=note['anchor'])
        if not row['text']:row['text']=note['text']
    elif identifier:
        row['anchor']=anchor(p,identifier)
        if not row['text']:row['text']=shot(p,identifier).get('action','Review this shot')
    elif not row['text']:raise ValueError('Save a checkpoint with --shot, --note, or --text')
    with write_lock(p):
        checkpoint(p)  # Refuse to replace a malformed existing record.
        data=read_state(p,'resume');data['items'].append(row);dump(state_path(p,'resume'),data)
    return row


def register_artifact(p,row):
    with write_lock(p):
        data=read_state(p,'artifacts');data['items'].append(row);dump(state_path(p,'artifacts'),data)


def relative_path(p,path):
    path=Path(path).resolve()
    try:return str(path.relative_to(p.root))
    except ValueError:return str(path)
