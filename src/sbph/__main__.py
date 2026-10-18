import argparse,json,subprocess,sys
from pathlib import Path
from .project import Project

def main():
    parser=argparse.ArgumentParser(prog='sbph',description='Local video tools built on FFmpeg, librosa, and OpenTimelineIO.')
    parser.add_argument('command',choices=['package','package-check','compare-return','status','resume','animatic','revision','note','notes','resolve','reanchor','intent','proof','motion-proof','motion-editor','motion-film','motion-film-editor','analyze','shots','timeline','assemble','validate','check','conform','doctor','resolve-check','resolve-record'])
    parser.add_argument('project',help='production.json, or a handoff folder for package-check/compare-return')
    parser.add_argument('--resolve-version',help='resolve-record: Resolve edition and version, such as "19.1 Free"')
    for flag,text in [('imported','edit.otio imported without errors'),('linked','every clip online'),('markers-visible','markers visible where placed'),('audio-locked','original audio track locked')]:
        parser.add_argument('--'+flag,action='store_true',help='resolve-record: confirm '+text)
    parser.add_argument('--out',help='New package folder or new comparison report file; existing paths are refused')
    parser.add_argument('--returned',help='Human editor return .otio file')
    parser.add_argument('--shot',action='append',help='Render only this shot ID; repeat for more than one')
    parser.add_argument('--resume',action='store_true',dest='resume_shots',help='For shots: reuse only current clips that pass record, hash, range, and media checks')
    parser.add_argument('--start',type=float,help='Proof start in seconds (project proof_start, otherwise 0)')
    parser.add_argument('--duration',type=float,help='Proof length in seconds (project proof_duration, otherwise 15)')
    parser.add_argument('--delivery',help='Movie to check, relative to the film root or absolute')
    parser.add_argument('--profile',choices=['generic','unit9'],help='Optional delivery verification profile')
    parser.add_argument('--reference',help='Independent movie for assembly conform, relative to film root or absolute')
    parser.add_argument('--motion-project',help='Override the registered Motion Canvas project.ts')
    parser.add_argument('--keep-frames',action='store_true',help='Retain the full Motion Canvas PNG sequence')
    parser.add_argument('--chunk-frames',type=int,default=600,help='Full Motion Canvas section size in frames; whole seconds')
    parser.add_argument('--json',action='store_true',help='Print workflow output as JSON')
    parser.add_argument('--text',help='Note or saved checkpoint text')
    parser.add_argument('--at',help='Note time: seconds, MM:SS, HH:MM:SS:FF, or 48f')
    parser.add_argument('--note',help='Short note ID, such as N1')
    parser.add_argument('--kind',default='note',help='Note category: n/t/c/v/a/s or its full name')
    parser.add_argument('--all',action='store_true',help='Include resolved notes')
    parser.add_argument('--width',type=int,default=640,help='Draft width limit (160–1280)')
    parser.add_argument('--render-stills',action='store_true',help='Use one renderer sample per shot in an animatic')
    parser.add_argument('--before',type=float,default=.5,help='Revision context before the shot, seconds')
    parser.add_argument('--after',type=float,default=.5,help='Revision context after the shot, seconds')
    for field in ['goal','obstacle','change','emotion','framing','exit_condition']:
        parser.add_argument('--'+field.replace('_','-'),help='Optional shot intent: '+field.replace('_',' '))
    args=parser.parse_args()
    if args.resume_shots and args.command!='shots':parser.error('--resume is only valid with shots')
    if args.command in {'resolve-check','resolve-record'}:
        from . import resolve as acceptance
        if args.command=='resolve-check':result=acceptance.check(args.project)
        else:result=acceptance.record(args.project,args.resolve_version,{'imported':args.imported,'linked':args.linked,'markersVisible':args.markers_visible,'audioLocked':args.audio_locked},args.returned,args.text)
        print(json.dumps(result,indent=2) if args.json else acceptance.display(result))
        return
    if args.command in {'package-check','compare-return'}:
        from .handoff import check_package
        if args.command=='package-check':
            manifest,_=check_package(args.project)
            result={'status':'valid','files':len(manifest['files']),'media':len(manifest['media']),'relativeReferences':True}
            print(json.dumps(result,indent=2) if args.json else f"Portable handoff valid: {result['media']} media files; collected hashes and relative references passed.")
        else:
            from .editor_return import compare,display
            if not args.returned:raise ValueError('Choose --returned /path/to/return.otio')
            if args.out and Path(args.out).exists():raise ValueError('Report destination already exists')
            result=compare(args.project,args.returned)
            if args.out:
                # Exclusive creation prevents a report from replacing owner files.
                with Path(args.out).open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
            print(json.dumps(result,indent=2) if args.json else display(result))
        return
    planning={'status','resume','note','notes','resolve','reanchor','intent'}
    p=Project.load(args.project,require_audio=args.command not in planning)
    if args.command in planning|{'animatic','revision'}:
        from . import workflow as flow
        if args.shot and len(args.shot)!=1:raise ValueError('This workflow command selects one shot at a time')
        selected=args.shot[0] if args.shot else None
        if args.command in {'status','resume'}:
            from .status import snapshot,display
            if args.command=='resume' and any([selected,args.note,args.text]):flow.save_checkpoint(p,selected,args.note,args.text)
            result=snapshot(p)
            print(json.dumps(result,indent=2) if args.json else display(result,brief=args.command=='resume'))
        elif args.command=='note':
            at=args.at
            if selected is None and at is None:
                saved=flow.checkpoint(p)
                if saved and saved.get('anchor') and saved['location']['frame'] is not None:
                    selected=saved['anchor']['shotId'];at=str(saved['location']['frame'])+'f'
            result=flow.add_note(p,args.text,selected,at,args.kind)
            print(json.dumps(result,indent=2) if args.json else f"{result['id']} / {result['anchor']['shotId']} / {result['location']['timecode']}: {result['text']}")
        elif args.command=='notes':
            result=flow.notes(p,args.all)
            print(json.dumps(result,indent=2) if args.json else '\n'.join(f"{n['id']} [{n['status']}] / {n['anchor']['shotId']} / {n['location']['timecode'] or n['location']['status']}: {n['text']}" for n in result) or 'No matching notes.')
        elif args.command=='resolve':
            if not args.note:raise ValueError('Choose --note N1 to resolve a note')
            result=flow.resolve_note(p,args.note,args.text)
            print(json.dumps(result,indent=2) if args.json else result['id']+' resolved; history retained.')
        elif args.command=='reanchor':
            if not args.note:raise ValueError('Choose --note N1 to move a note anchor')
            result=flow.reanchor_note(p,args.note,selected,args.at)
            print(json.dumps(result,indent=2) if args.json else f"{result['id']} / {result['anchor']['shotId']} / {result['location']['timecode']}; text and previous anchor retained.")
        elif args.command=='intent':
            fields={key:getattr(args,key) for key in flow.INTENT_FIELDS if getattr(args,key) is not None}
            if fields:
                if selected is None:raise ValueError('Choose --shot to update intent')
                result=[flow.set_intent(p,selected,fields)]
            else:result=[flow.shot_intent(p,s['id']) for s in p.edit['scenes'] if selected is None or s['id']==selected]
            if selected:flow.shot(p,selected)
            print(json.dumps(result,indent=2,ensure_ascii=False))
        else:
            from .drafts import render,animatic_parameters,revision_parameters
            if args.motion_project:raise ValueError('Draft commands use the SVG driver; use motion-proof or motion-film for Motion Canvas')
            if p.data.get('renderer')=='motion-canvas' and (args.command=='revision' or args.render_stills):
                raise ValueError('Use shots --shot ID for a Motion Canvas window; draft motion/still previews currently require the SVG driver')
            params=animatic_parameters(p,args.width,args.render_stills) if args.command=='animatic' else revision_parameters(p,selected,args.note,args.before,args.after,args.start,args.duration,args.width)
            result=render(p,params)
            print(json.dumps(result,indent=2) if args.json else f"DRAFT {result['id']}: {result['frames']} frames / {result['duration']:.2f}s — {p.root/result['file']}")
    elif args.command=='package':
        from .handoff import package
        output=package(p,args.out)
        print(json.dumps({'package':str(output)},indent=2) if args.json else 'Portable handoff: '+str(output))
    elif args.command=='validate':
        from .validation import validate_shot_set
        records=validate_shot_set(p)
        print(f"Production valid: {len(records['shots'])} current shots, ranges, media hashes, and source audio.")
    elif args.command=='proof':
        from .preview import preview
        preview(p,args.start,args.duration)
    elif args.command=='motion-proof':
        from .motion import build
        build(p,args.motion_project,args.keep_frames)
    elif args.command=='motion-editor':
        from .motion import editor
        editor(p,args.motion_project)
    elif args.command=='motion-film':
        from .motion_film import build
        build(p,args.motion_project,args.chunk_frames)
    elif args.command=='motion-film-editor':
        from .motion_film import editor
        editor(p,args.motion_project)
    elif args.command=='analyze':
        from .analyze import analyze
        analyze(p)
    elif args.command=='shots':
        from .media import render_shots
        render_shots(p,set(args.shot) if args.shot else None,resume=args.resume_shots)
    elif args.command=='timeline':
        from .timeline import timeline
        timeline(p)
    elif args.command=='assemble':
        from .media import assemble
        print(assemble(p))
    elif args.command=='check':
        from .verify import verify
        verify(p,args.delivery,args.profile)
    elif args.command=='conform':
        from .assembly_check import check
        check(p,args.reference)
    else:
        import importlib.metadata,shutil
        from .resolve import detect as detect_resolve
        print(json.dumps({'project':str(p.config),'libraries':{n:importlib.metadata.version(n) for n in ['opentimelineio','ffmpeg-python','librosa','moviepy']},'binaries':{n:shutil.which(n) for n in ['node','ffmpeg','ffprobe']},'resolve':detect_resolve(),'noExternalMediaCalls':True},indent=2))

if __name__=='__main__':
    try:main()
    except subprocess.CalledProcessError as e:
        print(f'sbph: command failed ({e.returncode}): '+' '.join(map(str,e.cmd)),file=sys.stderr);sys.exit(1)
    except KeyError as e:
        print(f'sbph: missing required field {e} in the edit or configuration',file=sys.stderr);sys.exit(1)
    except (ValueError,RuntimeError,FileNotFoundError,AssertionError) as e:
        print('sbph: '+str(e),file=sys.stderr);sys.exit(1)
