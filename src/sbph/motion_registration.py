"""Frozen registration of an existing native full-film plan and named cut cues."""
from pathlib import Path
from contextlib import ExitStack
import argparse,copy,hashlib,json,os,shutil
from .project import Project,FRAMEWORK,dump,sha,read_object,path_within
from .motion_film import effective_plan,validate_plan
from .media import _promote_files,_candidate_directory,output_lock
from .fingerprint import digest

PROFILE='named-cut-full-film-v1'


def cue_identity(cues):
    """Keep render inputs while excluding the editor's recomputed cue caches."""
    data=copy.deepcopy(read_object(cues,'Motion Canvas metadata'))
    if not isinstance(data.get('timeEvents'),list) or any(not isinstance(row,dict) for row in data['timeEvents']):raise ValueError('Motion Canvas metadata requires timeEvents objects')
    data['timeEvents']=sorted(({key:value for key,value in row.items() if key not in {'initialTime','offset','stack'}} for row in data['timeEvents']),key=lambda row:json.dumps(row,sort_keys=True))
    return digest(data)


def native_plan(project):
    project=Path(project).resolve();folder=project.parent
    if not project.is_file():raise ValueError('Missing native Motion Canvas project: '+str(project))
    specification=read_object(folder/'proof.json','Native render specification')
    scene=specification.get('scene','film')
    if not isinstance(scene,str) or Path(scene).name!=scene:raise ValueError('Unsafe native scene name')
    cues=folder/(scene+'.meta');plan=read_object(folder/'edit.json','Native edit');meta=read_object(cues,'Native cues')
    edit=effective_plan(plan,meta);validate_plan(edit,meta)
    if any(type(edit.get(k)) is not int or edit[k]<1 or specification.get(k)!=edit[k] for k in ['frames','fps','width','height']):raise ValueError('Native render specification differs from edit')
    return edit,cues


def validate_registration(p):
    receipt=p.data.get('motion_registration')
    if receipt is None:return
    if not isinstance(receipt,dict) or receipt.get('schemaVersion') not in (1,2) or receipt.get('profile')!=PROFILE:
        raise ValueError('Unsupported Motion Canvas registration')
    if not isinstance(receipt.get('project'),str):raise ValueError('Registration requires a native project path')
    project=(p.root/receipt['project']).resolve();edit,cues=native_plan(project)
    expected={'planSha256':sha(project.parent/'edit.json'),'renderSpecSha256':sha(project.parent/'proof.json'),'sourceAudioSha256':sha(p.audio)}
    if receipt['schemaVersion']==1:expected['cuesSha256']=sha(cues)
    else:expected['cuesSemanticSha256']=cue_identity(cues)
    if any(receipt.get(k)!=v for k,v in expected.items()) or p.edit!=edit:
        raise ValueError('Motion registration is stale; refresh the registered plan and cut windows before rendering or export')
    if sha(project.parent/'audio.wav')!=expected['sourceAudioSha256'] or edit.get('sourceAudioSha256')!=expected['sourceAudioSha256']:
        raise ValueError('Registered native audio differs from the original recording')
    mapping=p.data.get('motion_shots')
    if not isinstance(mapping,dict) or set(mapping)!={s['id'] for s in edit['scenes']}:raise ValueError('Registered shot set differs from native edit')
    for scene in edit['scenes']:
        row=mapping[scene['id']]
        if not isinstance(row,dict) or set(row)!={'project','startFrame'} or row.get('project')!=receipt['project'] or type(row.get('startFrame')) is not int or row['startFrame']!=scene['start']:
            raise ValueError('Registered source window differs from native cut: '+scene['id'])


def isolate_registered_body(p,copied,start,count):
    """Adapt only the temporary named-cut project to one local-time scene.

    Seeking the full timeline can retain the previous scene at the cut frame.
    A one-scene project cannot render neighboring scene coverage into its body
    or edge holds. The original registration keeps global editorial coordinates.
    """
    if p.data.get('motion_registration') is None:return None
    validate_registration(p)
    matches=[s for s in p.edit['scenes'] if s['start']==start and s['end']-s['start']==count]
    if len(matches)!=1:raise ValueError('Registered render window is not one complete native shot')
    shot=copy.deepcopy(matches[0]);shot['start']=0;shot['end']=count
    names=set()
    for action in shot.get('animations',[]):
        action['startFrame']-=start;action['endFrame']-=start
        names.update([action['startEvent'],action['endEvent']])
    for hit in shot.get('pulses',[]):
        hit['frame']-=start;hit['endFrame']-=start;names.add(hit['startEvent'])
    for accent in shot.get('accents',[]):accent['frame']-=start
    edit=copy.deepcopy(p.edit);edit.update(frames=count,scenes=[shot])
    specification=json.loads((copied/'proof.json').read_text());cues=copied/(specification.get('scene','film')+'.meta')
    meta=json.loads(cues.read_text())
    events=[{**event,'targetTime':(round(event['targetTime']*p.fps)-start)/p.fps} for event in meta['timeEvents'] if event['name'] in names and event['name']!='cut-end']
    events.append({'name':'cut-end','targetTime':count/p.fps})
    meta['timeEvents']=events
    validate_plan(edit,meta)
    dump(copied/'edit.json',edit);dump(cues,meta)
    return shot['id']


def _registration_paths(legacy,destination,output):
    root=destination.parent/'unit-9-motion';target=root/'data/edit.json'
    if path_within(output,legacy.root) or path_within(legacy.root,output) or path_within(output,legacy.output):raise ValueError('Registration output must be separate from the existing film tree')
    originals=[legacy.root,legacy.audio.parent,legacy.output]
    if any(path_within(path,original) for path in [destination,root,target] for original in originals):raise ValueError('Registration destination and edit snapshot must be separate from the existing film tree')
    return root


def _registration_record(path,expected,label):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise RuntimeError('Registration inputs changed while planning; previous registration preserved')
    data=json.loads(raw)
    if not isinstance(data,dict):raise ValueError(label+' must be an object: '+str(path))
    return data


def register(legacy_config,destination,output,refresh=False,selected_config=None):
    # Serialize the paired snapshot and protect against a concurrent render or
    # refresh of the registered output. Nested production calls share the lock.
    legacy=Project.load(legacy_config);output=Path(output).resolve();destination=Path(destination).resolve()
    root=_registration_paths(legacy,destination,output)
    selected=Path(selected_config).resolve() if selected_config is not None else destination
    if path_within(selected,destination):selected=destination
    if path_within(selected,legacy.root):raise ValueError('Selected registration must be separate from the existing film tree')
    if selected!=destination and (selected.name!='production.json' or selected.parent.parent!=output):raise ValueError('Selected native run must be directly inside the registered output directory')
    with ExitStack() as locks:
        locks.enter_context(output_lock(root,'motion-register shared snapshot'))
        locks.enter_context(output_lock(output,'motion-register'))
        if selected!=destination:
            # Named run configurations live in their own output directory.
            # Lock it before reading settings; the shared-root lock serializes
            # registration refreshes of different runs.
            locks.enter_context(output_lock(selected.parent,'motion-register selected run'))
        return _register(legacy_config,destination,output,refresh,selected,locks)


def _register(legacy_config,destination,output,refresh=False,selected=None,locks=None):
    legacy=Project.load(legacy_config);destination=Path(destination).resolve();output=Path(output).resolve()
    root=_registration_paths(legacy,destination,output)
    target=root/'data/edit.json';selected=destination if selected is None else Path(selected).resolve()
    # Capture owner files before reading their settings so an external edit
    # anywhere during planning/staging cannot be overwritten by an old copy.
    before={path:sha(path) if path.exists() else None for path in [Path(legacy_config).resolve(),target,destination,selected]}
    project=(legacy.root/legacy.data.get('motion_canvas_full','motion-canvas/full-film-v01/project.ts')).resolve()
    edit,cues=native_plan(project)
    if any(edit[k]!=getattr(legacy,k) for k in ['fps','frames','width','height']):raise ValueError('Native film dimensions, rate, or duration differ from original edit')
    audio_hash=sha(legacy.audio)
    if edit.get('sourceAudioSha256')!=audio_hash or sha(project.parent/'audio.wav')!=audio_hash:raise ValueError('Native project must retain the original audio bytes')
    if path_within(output,legacy.root) or path_within(legacy.root,output) or path_within(output,legacy.output):
        raise ValueError('Registration output must be separate from the existing film tree')
    relative=lambda file:Path(os.path.relpath(file,root)).as_posix()
    native=relative(project)
    config={'root':root.name,'edit':'data/edit.json','audio':relative(legacy.audio),'output':relative(output),'delivery':relative(output/'assembly.mp4'),
        'renderer':'motion-canvas','handles':legacy.handles,'timeline_file':'unit-9-motion-human-edit.otio','source_globs':['data/**/*'],
        'verification':{'profile':'generic','conform_first_frame_offset':1},'motion_shots':{s['id']:{'project':native,'startFrame':s['start']} for s in edit['scenes']},
        'motion_registration':{'schemaVersion':2,'profile':PROFILE,'project':native,'planSha256':sha(project.parent/'edit.json'),'cuesSemanticSha256':cue_identity(cues),'renderSpecSha256':sha(project.parent/'proof.json'),'sourceAudioSha256':audio_hash}}
    existing={};candidate={destination:config}
    for path in dict.fromkeys([destination,selected]):
        if not path.exists():
            if path!=destination:raise ValueError('Selected native run configuration is missing: '+str(path))
            if target.exists():raise ValueError('Incomplete registration destination; inspect existing files before refreshing')
            continue
        data=_registration_record(path,before[path],'Motion registration');receipt=data.get('motion_registration')
        if not isinstance(receipt,dict) or receipt.get('profile')!=PROFILE or receipt.get('schemaVersion') not in (1,2):raise ValueError('Refusing to overwrite an unrecognized registration')
        prior=Project.load(path)
        same=lambda a,b:path_within(a,b) and path_within(b,a)
        expected_output=output if path==destination else path.parent
        if not same(prior.root,root) or not same(prior.output,expected_output) or not same(prior.audio,legacy.audio) or not same(prior.root/prior.data.get('edit','data/edit.json'),target) or prior.data.get('renderer')!='motion-canvas':raise ValueError('Registration root, edit, audio, renderer, or output differs from the owned native run')
        if path!=destination and prior.output.parent!=output:raise ValueError('Selected native run must be directly inside the registered output directory')
        if not isinstance(receipt.get('project'),str) or not same(prior.root/receipt['project'],project):raise ValueError('Registration refers to a different native source project')
        existing[path]=data
        if not refresh:
            # Legacy registrations have no saved semantic baseline. Their raw
            # guard remains authoritative until explicit --refresh.
            validate_registration(prior);candidate[path]=data
        else:
            candidate[path]={**copy.deepcopy(data),'motion_registration':copy.deepcopy(config['motion_registration']),'motion_shots':copy.deepcopy(config['motion_shots'])}
    changed_edit=not target.exists() or _registration_record(target,before[target],'Registered edit')!=edit
    changed={path:data for path,data in candidate.items() if existing.get(path)!=data}
    if not changed and not changed_edit:return selected
    if changed_edit and output.exists():
        # Shared timing changes stale sibling runs. Hold every existing named
        # output lock during the small transaction; an active sibling renderer
        # or an abandoned lock requires inspection before this mutation.
        selected_output=selected.parent if selected!=destination else None
        siblings=[]
        for sibling in sorted(output.glob('*/production.json')):
            folder=sibling.parent.resolve()
            if folder.parent!=output or sibling.resolve().parent!=folder:raise ValueError('Sibling native run must remain inside the registered output directory')
            sibling_data=read_object(sibling,'Sibling native run');sibling_root=(folder/sibling_data.get('root','.')).resolve()
            if sibling_root!=root or (sibling_root/sibling_data.get('output','production')).resolve()!=folder or sibling_data.get('renderer')!='motion-canvas':raise ValueError('Sibling native run configuration redirects its registered root or output')
            siblings.append(folder)
            if folder!=selected_output and locks is not None:locks.enter_context(output_lock(folder,'motion-register shared timing'))
        own={'.'+path.name+'.sbph-build-lock' for path in [selected_output] if path is not None}
        known={'.'+folder.name+'.sbph-build-lock' for folder in siblings}
        if any(lock.name not in own|known for lock in output.glob('.*.sbph-build-lock')):raise ValueError('A sibling native output is locked; inspect its writer before refreshing shared timing')
    tracked=[Path(legacy_config).resolve(),target,destination,selected,project.parent/'edit.json',cues,project.parent/'proof.json',legacy.audio,project.parent/'audio.wav']
    for path in tracked:
        if path not in before:before[path]=sha(path) if path.exists() else None
    destination.parent.mkdir(parents=True,exist_ok=True);target.parent.mkdir(parents=True,exist_ok=True)
    with _candidate_directory(prefix='.motion-registration-',dir=destination.parent) as work:
        work=Path(work);staged_edit=work/'edit.json';dump(staged_edit,edit);pairs=[]
        if changed_edit:pairs.append((staged_edit,target))
        # Validate the candidate pair without making either destination visible.
        for path,data in candidate.items():
            staged=work/('production.json' if path==destination else 'selected-production.json')
            dump(staged,{**data,'root':str(root),'edit':str(staged_edit)});validate_registration(Project.load(staged))
            if path in changed:dump(staged,data);pairs.append((staged,path))
        if selected!=destination and selected in changed:
            previous=work/'selected-before.json';shutil.copy2(selected,previous)
            if sha(previous)!=before[selected]:raise RuntimeError('Registration inputs changed while staging; previous registration preserved')
            history=selected.parent/'.registration-history'
            if history.is_symlink() or history.resolve().parent!=selected.parent or history.exists() and not history.is_dir():raise ValueError('Selected registration recovery directory must be a local directory, not a symlink')
            history.mkdir(exist_ok=True)
            saved=history/('production-'+before[selected]+'.json')
            if saved.exists():
                if sha(saved)!=before[selected]:raise ValueError('Selected registration recovery copy differs from its identity')
            else:pairs.insert(0,(previous,saved))
        # Locks serialize toolkit writers; recheck bytes because a native editor
        # or external file editor does not participate in these local locks.
        if any((sha(path) if path.exists() else None)!=value for path,value in before.items()):raise RuntimeError('Registration inputs changed while staging; previous registration preserved')
        _registration_paths(legacy,destination,output)
        _promote_files(pairs,work)
    return selected


def main():
    parser=argparse.ArgumentParser(description='Register Unit 9 native cuts without changing its source tree.')
    parser.add_argument('--refresh',action='store_true',help='Replace the owned registration snapshot after reviewing native timing changes')
    parser.add_argument('--run',help='Refresh an existing named run or default; otherwise use the saved active run')
    args=parser.parse_args()
    from .unit9_run import resolve
    selected=resolve(FRAMEWORK,args.run)
    path=register(FRAMEWORK/'examples/unit-9.json',FRAMEWORK/'examples/unit-9-motion.json',FRAMEWORK/'output/unit-9-motion-handled',args.refresh,selected)
    print('Unit 9 Motion registration: '+str(path)+'; source files preserved. No render started.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError) as error:raise SystemExit('sbph: '+' '.join(str(error).split()))
