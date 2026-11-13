"""Local, hash-bound evidence and explicit human screening attestations."""
from pathlib import Path
import json,uuid
from .project import sha,dump,shot_filename
from .delivery import delivery_path
from .media import output_lock,_protect_output_inputs
from .workflow import now


def preflight(p):
    from .fingerprint import source_paths
    from .validation import validate_edit
    validate_edit(p)
    filename=p.data.get('timeline_file','human-edit.otio')
    if not isinstance(filename,str) or Path(filename).name!=filename or not filename.endswith('.otio'):raise ValueError('timeline_file must be an .otio filename')
    outputs=[p.output/'shots.json',p.output/'proof.mp4',p.output/'proof.json',p.output/'assembly.mp4',
        p.output/filename,(p.output/filename).with_suffix('.xml'),p.output/'timeline-verification.json',
        p.output/'media-verification.json',p.output/'assembly-verification.json',p.output/'review']
    outputs.extend(p.output/'shots'/shot_filename(scene) for scene in p.edit['scenes'])
    _protect_output_inputs(p,outputs)
    paths=source_paths(p);missing=[str(file) for file in paths if not file.is_file()]
    return {'status':'blocked' if missing else 'ready','project':str(p.config),'output':str(p.output),'sourceFiles':len(paths),'missingRequiredSources':missing,
        'shotFiles':[shot_filename(scene) for scene in p.edit['scenes']],
        'limit':'Configuration and path preflight only; no probing, encoding, or production acceptance.'}


def saved_records(p):
    paths=[p.output/name for name in ['shots.json','proof.json','media-verification.json','assembly-verification.json','timeline-verification.json']]
    paths+=sorted((p.output/'evidence').glob('*.json'))
    paths+=sorted((p.output/'handoffs').glob('*/resolve-acceptance-*.json'))
    rows=[]
    for path in paths:
        if not path.is_file():continue
        try:
            data=json.loads(path.read_text())
            if not isinstance(data,dict):raise ValueError('record must be an object')
            rows.append({'file':str(path),'sha256':sha(path),'status':data.get('status','recorded'),
                'sourceFingerprint':data.get('sourceFingerprint',data.get('packageIdentity',{}).get('sourceFingerprint')),
                'createdAt':data.get('createdAt'),'mode':data.get('mode')})
        except (ValueError,OSError,AttributeError) as error:rows.append({'file':str(path),'status':'unreadable','reason':str(error)})
    return {'project':str(p.config),'records':rows,'limit':'Saved evidence inventory; historical receipts do not establish current production or human acceptance.'}


def screening_status(p,movie,fingerprint):
    if not movie.is_file():return None
    expected=None
    for path in sorted((p.output/'evidence').glob('screening-*.json'),reverse=True):
        try:
            data=json.loads(path.read_text())
            if data.get('schemaVersion')!=1 or data.get('mode')!='human-screening' or data.get('status')!='attested' or data.get('sourceFingerprint')!=fingerprint:continue
            if expected is None:expected=sha(movie)
            if data.get('deliverySha256')==expected and data.get('watchedEntireMovie') is True and data.get('reviewedFirstCutFrames') is True:
                return {'status':'attested','file':str(path),'createdAt':data.get('createdAt'),'limit':'Owner attestation; not measured by the toolkit.'}
        except (ValueError,OSError,AttributeError):continue
    return None


def record_screening(p,screened=False,first_cuts=False,text=None):
    if not screened or not first_cuts:raise ValueError('Watch the complete movie and review first cut frames, then pass --screened --first-cuts-reviewed')
    from .status import shot_build,delivery
    with output_lock(p,'screen-record'):
        if shot_build(p)['status']!='matches':raise ValueError('Screening needs a current complete handled-shot build; refresh and check it first')
        movie=delivery_path(p);verified=delivery(p)
        if verified.get('verification')!='saved report matches movie bytes':raise ValueError('Run check for this delivery before recording a screening')
        fingerprint=p.source_inventory()[0];movie_hash=sha(movie)
        media=json.loads((p.output/'media-verification.json').read_text())
        if media.get('status')!='passed' or media.get('sourceFingerprint')!=fingerprint:raise ValueError('Delivery verification is historical; run check against the current build')
        folder=p.output/'evidence';_protect_output_inputs(p,[folder]);folder.mkdir(parents=True,exist_ok=True)
        path=folder/('screening-'+now().replace(':','').replace('+','_')+'-'+uuid.uuid4().hex[:8]+'.json')
        report={'schemaVersion':1,'mode':'human-screening','status':'attested','createdAt':now(),'sourceFingerprint':fingerprint,
            'delivery':str(movie),'deliverySha256':movie_hash,'mediaVerificationSha256':sha(p.output/'media-verification.json'),
            'watchedEntireMovie':True,'reviewedFirstCutFrames':True,'notes':text or '',
            'limit':'Explicit owner attestation, not measured viewing, creative approval, or Resolve acceptance.'}
        if sha(movie)!=movie_hash or p.source_inventory()[0]!=fingerprint:raise ValueError('Delivery or sources changed before screening record save')
        with path.open('x',encoding='utf-8') as stream:stream.write(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        return {**report,'file':str(path)}
