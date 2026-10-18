"""Frozen registration of an existing native full-film plan and named cut cues."""
from pathlib import Path
import argparse,copy,json,os
from .project import Project,FRAMEWORK,dump,sha
from .motion_film import effective_plan,validate_plan

PROFILE='named-cut-full-film-v1'


def native_plan(project):
    project=Path(project).resolve();folder=project.parent
    if not project.is_file():raise ValueError('Missing native Motion Canvas project: '+str(project))
    specification=json.loads((folder/'proof.json').read_text())
    scene=specification.get('scene','film')
    if not isinstance(scene,str) or Path(scene).name!=scene:raise ValueError('Unsafe native scene name')
    cues=folder/(scene+'.meta');plan=json.loads((folder/'edit.json').read_text());meta=json.loads(cues.read_text())
    edit=effective_plan(plan,meta);validate_plan(edit,meta)
    if any(specification.get(k)!=edit[k] for k in ['frames','fps','width','height']):raise ValueError('Native render specification differs from edit')
    return edit,cues


def validate_registration(p):
    receipt=p.data.get('motion_registration')
    if receipt is None:return
    if not isinstance(receipt,dict) or receipt.get('schemaVersion')!=1 or receipt.get('profile')!=PROFILE:
        raise ValueError('Unsupported Motion Canvas registration')
    if not isinstance(receipt.get('project'),str):raise ValueError('Registration requires a native project path')
    project=(p.root/receipt['project']).resolve();edit,cues=native_plan(project)
    expected={'planSha256':sha(project.parent/'edit.json'),'cuesSha256':sha(cues),'renderSpecSha256':sha(project.parent/'proof.json'),'sourceAudioSha256':sha(p.audio)}
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
    for action in shot['animations']:
        action['startFrame']-=start;action['endFrame']-=start
        names.update([action['startEvent'],action['endEvent']])
    for hit in shot.get('pulses',[]):
        hit['frame']-=start;hit['endFrame']-=start;names.add(hit['startEvent'])
    for accent in shot['accents']:accent['frame']-=start
    edit=copy.deepcopy(p.edit);edit.update(frames=count,scenes=[shot])
    specification=json.loads((copied/'proof.json').read_text());cues=copied/(specification.get('scene','film')+'.meta')
    meta=json.loads(cues.read_text())
    events=[{**event,'targetTime':(round(event['targetTime']*p.fps)-start)/p.fps} for event in meta['timeEvents'] if event['name'] in names and event['name']!='cut-end']
    events.append({'name':'cut-end','targetTime':count/p.fps})
    meta['timeEvents']=events
    validate_plan(edit,meta)
    dump(copied/'edit.json',edit);dump(cues,meta)
    return shot['id']


def register(legacy_config,destination,output,refresh=False):
    legacy=Project.load(legacy_config);destination=Path(destination).resolve();output=Path(output).resolve()
    root=destination.parent/'unit-9-motion'
    project=(legacy.root/legacy.data.get('motion_canvas_full','motion-canvas/full-film-v01/project.ts')).resolve()
    edit,cues=native_plan(project)
    if any(edit[k]!=getattr(legacy,k) for k in ['fps','frames','width','height']):raise ValueError('Native film dimensions, rate, or duration differ from original edit')
    audio_hash=sha(legacy.audio)
    if edit.get('sourceAudioSha256')!=audio_hash or sha(project.parent/'audio.wav')!=audio_hash:raise ValueError('Native project must retain the original audio bytes')
    if output.is_relative_to(legacy.root) or legacy.root.is_relative_to(output) or output==legacy.output:
        raise ValueError('Registration output must be separate from the existing film tree')
    relative=lambda file:Path(os.path.relpath(file,root)).as_posix()
    native=relative(project)
    config={'root':root.name,'edit':'data/edit.json','audio':relative(legacy.audio),'output':relative(output),'delivery':relative(output/'assembly.mp4'),
        'renderer':'motion-canvas','handles':legacy.handles,'timeline_file':'unit-9-motion-human-edit.otio','source_globs':['data/**/*'],
        'verification':{'profile':'generic','conform_first_frame_offset':1},'motion_shots':{s['id']:{'project':native,'startFrame':s['start']} for s in edit['scenes']},
        'motion_registration':{'schemaVersion':1,'profile':PROFILE,'project':native,'planSha256':sha(project.parent/'edit.json'),'cuesSha256':sha(cues),'renderSpecSha256':sha(project.parent/'proof.json'),'sourceAudioSha256':audio_hash}}
    target=root/'data/edit.json'
    if target.exists() or destination.exists():
        if not destination.is_file() or not target.is_file():raise ValueError('Incomplete registration destination; inspect existing files before refreshing')
        existing=json.loads(destination.read_text())
        if existing==config and json.loads(target.read_text())==edit:
            validate_registration(Project.load(destination));return destination
        if not refresh:raise ValueError('Registration differs; use motion-register --refresh after reviewing saved native cues')
        if existing.get('motion_registration',{}).get('profile')!=PROFILE:raise ValueError('Refusing to overwrite an unrecognized registration')
    dump(target,edit);dump(destination,config)
    validate_registration(Project.load(destination))
    return destination


def main():
    parser=argparse.ArgumentParser(description='Register Unit 9 native cuts without changing its source tree.')
    parser.add_argument('--refresh',action='store_true',help='Replace the owned registration snapshot after reviewing native timing changes')
    args=parser.parse_args()
    path=register(FRAMEWORK/'examples/unit-9.json',FRAMEWORK/'examples/unit-9-motion.json',FRAMEWORK/'output/unit-9-motion-handled',args.refresh)
    print('Unit 9 Motion registration: '+str(path)+'; source files preserved. No render started.')


if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError) as error:raise SystemExit('sbph: '+str(error))
