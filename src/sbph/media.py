from pathlib import Path
from fractions import Fraction
from contextlib import contextmanager
import json, os, shutil, subprocess, sys, tempfile, time
import ffmpeg
from .project import binary, dump, sha, FRAMEWORK

COLOR=dict(color_primaries='bt709',color_trc='iec61966-2-1',colorspace='bt709',color_range='tv')
BSF='h264_metadata=colour_primaries=1:transfer_characteristics=13:matrix_coefficients=1'

def probe(path):return ffmpeg.probe(str(path),cmd=binary('ffprobe'))

def _protect_output_inputs(p,outputs,inputs=()):
    """Reject generated destinations that would replace known original inputs."""
    protected=[Path(value).resolve() for value in inputs]
    for name in ['audio','driver','config']:
        value=getattr(p,name,None)
        if value is not None:protected.append(Path(value).resolve())
    if getattr(p,'root',None) is not None:
        protected.append((p.root/p.data.get('edit','data/edit.json')).resolve())
    for output in outputs:
        destination=Path(output).resolve()
        for original in protected:
            if original.is_relative_to(destination):
                raise ValueError('Generated output would replace a protected input: '+str(original)+' -> '+str(destination))

@contextmanager
def _candidate_directory(*,prefix,dir):
    """Clean disposable render work without masking a build or saved result."""
    work=Path(tempfile.mkdtemp(prefix=prefix,dir=dir)).resolve()
    try:yield work
    finally:
        try:shutil.rmtree(work)
        except BaseException as error:
            try:print('Temporary render work retained: '+str(work)+' ('+type(error).__name__+')',file=sys.stderr)
            except BaseException:pass

def _stop_process(process):
    """Reap an interrupted encoder/producer before its temporary files disappear."""
    if process is None:return
    try:
        if process.poll() is None:
            try:process.terminate()
            except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
    finally:
        for name in ('stdin','stdout','stderr'):
            pipe=getattr(process,name,None)
            if pipe is not None:pipe.close()


def _run_ffmpeg(graph):
    command=ffmpeg.compile(graph,cmd=binary('ffmpeg'),overwrite_output=True)
    process=None
    try:
        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        _,errors=process.communicate()
        if process.returncode:
            raise RuntimeError('FFmpeg failed: '+errors.decode('utf-8',errors='replace')[-3000:])
    finally:
        _stop_process(process)


def _validate_video(path,p,count,with_audio=False):
    """Verify a completed candidate before replacing any previous output."""
    info=probe(path)
    videos=[s for s in info['streams'] if s.get('codec_type')=='video']
    audios=[s for s in info['streams'] if s.get('codec_type')=='audio']
    if len(videos)!=1 or len(audios)!=(1 if with_audio else 0):
        raise RuntimeError('Candidate requires one video stream'+(' and one audio stream' if with_audio else ' without audio'))
    video=videos[0]
    if int(video.get('nb_frames',-1))!=count or Fraction(video['avg_frame_rate'])!=p.fps:
        raise RuntimeError('Encoder did not deliver the requested frame count/rate')
    if (video.get('width'),video.get('height'))!=(p.width,p.height):
        raise RuntimeError('Encoder dimensions differ from the edit')
    if [video.get(k) for k in ['color_primaries','color_transfer','color_space','color_range']]!=['bt709','iec61966-2-1','bt709','tv']:
        raise RuntimeError('Encoder color tags differ from the delivery contract')
    if with_audio:
        audio=audios[0]
        if int(audio.get('sample_rate',0))!=48000 or audio.get('channels')!=2:
            raise RuntimeError('Encoded audio must be 48 kHz stereo')
        if abs(float(audio.get('duration',-1))-count/p.fps)>.022:
            raise RuntimeError('Encoded audio duration differs from the requested window')
    return info


def render_picture(p,destination,start,count,shot=None):
    destination=Path(destination)
    _protect_output_inputs(p,[destination])
    destination.parent.mkdir(parents=True,exist_ok=True)
    options=dict(driver=str(p.driver),start=start,count=count,shot=shot,width=p.width,height=p.height)
    with _candidate_directory(prefix='.picture-',dir=destination.parent) as folder:
        work=Path(folder);candidate=work/'picture.mp4';tagged=work/'tagged.mp4'
        producer=consumer=None
        try:
            producer=subprocess.Popen([binary('node'),str(FRAMEWORK/'render/emit.cjs'),json.dumps(options)],stdout=subprocess.PIPE)
            picture=ffmpeg.input('pipe:0',format='rawvideo',pix_fmt='rgba',s=f'{p.width}x{p.height}',framerate=p.fps).video
            picture=picture.filter('scale',out_color_matrix='bt709',out_range='tv')
            graph=ffmpeg.output(picture,str(candidate),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=p.fps,threads=6,g=p.fps,movflags='+faststart',**COLOR).global_args('-hide_banner','-loglevel','error')
            command=ffmpeg.compile(graph,cmd=binary('ffmpeg'),overwrite_output=True)
            consumer=subprocess.Popen(command,stdin=producer.stdout,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            producer.stdout.close()
            _,errors=consumer.communicate()
            if consumer.returncode:_stop_process(producer)
            producer_code=producer.wait()
            if consumer.returncode or producer_code:
                raise RuntimeError(f'Frame producer/encoder failed: {producer_code}/{consumer.returncode}: '+errors.decode('utf-8',errors='replace')[-3000:])
        finally:
            if producer is not None and producer.stdout is not None:producer.stdout.close()
            _stop_process(consumer);_stop_process(producer)
        graph=ffmpeg.output(ffmpeg.input(str(candidate)).video,str(tagged),vcodec='copy',**{'bsf:v':BSF},movflags='+faststart',**COLOR)
        _run_ffmpeg(graph);_validate_video(tagged,p,count)
        record={'file':str(p.public_path(destination)),'frames':count,'sha256':sha(tagged),'fps':p.fps,'color':COLOR}
        tagged.replace(destination)
    return record

def _promote_shot(candidate,destination,manifest_path,manifest,work,before_promote=None):
    """Stage both artifacts, then roll back if either replacement fails."""
    staged=work/'shots.json'
    dump(staged,manifest)
    if before_promote is not None:before_promote()
    _promote_files([(candidate,destination),(staged,manifest_path)],work)


def _promote_files(pairs,work,remove=()):
    """Promote a complete generated set, restoring it on a caught failure.

    Candidates live inside a unique temporary work directory on the output
    filesystem. Outputs must be independent of that staging tree and each
    other. Old files are hardlinked before any output changes; old directories
    are renamed, avoiding a second copy of retained frame sequences. Recovery
    storage and its mapping are prepared beside final outputs before any output
    is detached, so even a failed rollback needs no new recovery write or move.
    """
    def path(value):
        result=Path(value)
        if result.is_symlink():raise ValueError('Promotion paths must not be symlinks: '+str(result))
        return result.absolute()

    def overlaps(a,b):
        a,b=a.resolve(),b.resolve()
        return a==b or a.is_relative_to(b) or b.is_relative_to(a)

    def discard(target):
        if target.is_symlink() or target.is_file():target.unlink()
        elif target.is_dir():shutil.rmtree(target)

    work=path(work)
    if not work.is_dir():raise ValueError('Promotion work directory is missing')
    if isinstance(remove,(str,bytes,Path)):raise ValueError('Promotion removals must be a sequence of paths')
    pairs=[(path(candidate),path(destination)) for candidate,destination in pairs]
    targets=[destination for _,destination in pairs]+[path(target) for target in remove]
    candidates=[candidate for candidate,_ in pairs]
    if not targets:return
    device=work.stat().st_dev
    for candidate in candidates:
        if candidate.resolve()==work.resolve() or not candidate.resolve().is_relative_to(work.resolve()):
            raise ValueError('Promotion candidates must be inside the work directory')
        if not candidate.is_file() and not candidate.is_dir():raise ValueError('Promotion candidate is missing: '+str(candidate))
        if candidate.stat().st_dev!=device:raise ValueError('Promotion requires one filesystem')
    for index,candidate in enumerate(candidates):
        if any(overlaps(candidate,other) for other in candidates[:index]):
            raise ValueError('Promotion candidates overlap')
    for index,target in enumerate(targets):
        if overlaps(target,work) or any(overlaps(target,other) for other in targets[:index]):
            raise ValueError('Promotion outputs overlap each other or staging')
        if not target.parent.is_dir():raise ValueError('Promotion output parent is missing: '+str(target.parent))
        if target.exists() and not target.is_file() and not target.is_dir():
            raise ValueError('Unsupported promotion output: '+str(target))
        if target.parent.stat().st_dev!=device or (target.exists() and target.stat().st_dev!=device):
            raise ValueError('Promotion requires one filesystem')

    # A section's work parent can itself be temporary. Old bytes must never
    # depend on escaping that staging tree after a rollback has already failed.
    recovery_parent=Path(os.path.commonpath([str(target.parent.resolve()) for target in targets]))
    recovery=Path(tempfile.mkdtemp(prefix='.promotion-recovery-',dir=recovery_parent))
    backup_root=recovery/'backups'
    backups={};touched=[]

    def cleanup(outcome):
        # The output set is already complete or restored. Cleanup must not turn
        # that result into a false failure, including cancellation while deleting
        # potentially large, superseded frame directories.
        try:shutil.rmtree(recovery)
        except BaseException as cleanup_error:
            try:print(outcome+'; recovery cleanup incomplete: '+str(recovery)+' ('+type(cleanup_error).__name__+')',file=sys.stderr)
            except BaseException:pass

    try:
        backup_root.mkdir()
        # Hardlink every old file before detaching any part of the previous set.
        for index,target in enumerate(targets):
            backup=backup_root/str(index)
            if target.is_file():
                backup.hardlink_to(target);backups[target]=(backup,'file')
            elif target.is_dir():backups[target]=(backup,'directory')
        dump(recovery/'recovery.json',{'schemaVersion':1,
            'previousOutputs':{str(target):str(backup.relative_to(backup_root)) for target,(backup,_) in backups.items()},
            'previouslyAbsentOutputs':[str(target) for target in targets if target not in backups]})
    except BaseException:
        cleanup('Previous outputs unchanged')
        raise
    try:
        for target in targets:
            if target not in backups:continue
            backup,kind=backups[target];touched.append(target)
            if kind=='directory':target.replace(backup)
            else:target.unlink()
        for candidate,destination in pairs:
            if destination not in touched:touched.append(destination)
            candidate.replace(destination)
    except BaseException as error:
        failures=[]
        for target in reversed(touched):
            try:
                previous=backups.get(target)
                if previous is None:discard(target)
                elif previous[0].exists():
                    discard(target);previous[0].replace(target)
            except BaseException as restore_error:
                failures.append({'output':str(target),'error':str(restore_error)})
        if failures:
            raise RuntimeError('Output promotion rollback was incomplete; previous output backups are preserved in '+str(recovery)
                +'; outputs needing recovery: '+', '.join(failure['output'] for failure in failures)) from error
        cleanup('Previous outputs restored')
        raise
    cleanup('Outputs promoted successfully')


def render_shots(p,selected=None,resume=False):
    from .fingerprint import BUILD_SCHEMA
    from .shot_backend import backend, renderer_record
    from .validation import validate_edit,validate_source_audio,validate_shot_record
    manifest_path=p.output/'shots.json'
    scenes=[s for s in p.edit['scenes'] if selected is None or s['id'] in selected]
    _protect_output_inputs(p,[manifest_path,*[p.output/'shots'/f"{s['id']}-{s['kind']}.mp4" for s in scenes]])
    validate_edit(p);validate_source_audio(p)
    if selected is not None:
        unknown=selected-{s['id'] for s in p.edit['scenes']}
        if unknown:raise ValueError('Unknown shot IDs: '+', '.join(sorted(unknown)))
    prior=json.loads(manifest_path.read_text()) if manifest_path.exists() else {'shots':{}}
    if not isinstance(prior,dict):raise ValueError('Shot manifest must be an object')
    fingerprint,inventory=p.source_inventory()
    renderer=renderer_record(p)
    header={'schemaVersion':BUILD_SCHEMA,'project':p.edit['title'],'fps':p.fps,
        'sourceFingerprint':fingerprint,'sourceInventory':inventory,
        'sourceEditSha256':sha(p.root/p.data.get('edit','data/edit.json')),**renderer}
    compatible=all(prior.get(key)==value for key,value in header.items() if key!='project')
    current_ids={s['id'] for s in p.edit['scenes']}
    records={key:value for key,value in prior.get('shots',{}).items() if key in current_ids} \
        if compatible and isinstance(prior.get('shots'),dict) else {}
    reused=0;rendered=0
    def check_sources():
        if p.source_inventory()[0]!=fingerprint:
            raise RuntimeError('Sources changed during render; previous clip and manifest preserved')
    for i,s in enumerate(scenes):
        body=s['end']-s['start'];count=body+2*p.handles
        file=p.output/'shots'/f"{s['id']}-{s['kind']}.mp4"
        if resume and s['id'] in records:
            try:validate_shot_record(p,s,records[s['id']],fingerprint)
            except (ValueError,OSError,ffmpeg.Error):pass
            else:
                reused+=1
                print(f"Shot {s['id']} / {i+1} of {len(scenes)}: reused verified clip.",flush=True)
                continue
        file.parent.mkdir(parents=True,exist_ok=True)
        with _candidate_directory(prefix='.shot-build-',dir=p.output) as temporary:
            work=Path(temporary);candidate=work/file.name
            if backend(p)=='motion-canvas':
                from .motion_shots import render_shot
                record=render_shot(p,s,candidate)
            else:record=render_picture(p,candidate,-p.handles,count,s['id'])
            record.update(file=str(p.public_path(file)),sourceFingerprint=fingerprint,id=s['id'],bodyFrames=body,
                handleIn=p.handles,handleOut=p.handles,sourceStart=p.handles,timelineStart=s['start'],
                handlePolicy='Same-shot renderer extension. Normalized progress clamps at the shot boundary; time-based details may continue. Some handles are holds. SVG rig/effects are baked in this clip.')
            if backend(p)=='motion-canvas':record['handlePolicy']='Explicit Motion Canvas body window; first/last body frames held for handles. Motion and effects are baked.'
            validate_shot_record(p,s,record,fingerprint,movie=candidate)
            updated={**records,s['id']:record}
            _promote_shot(candidate,file,manifest_path,{**header,'shots':updated},work,before_promote=check_sources)
            records=updated
        rendered+=1
        print(f"Shot {s['id']} / {i+1} of {len(scenes)}: {count} frames including handles.",flush=True)
    if p.source_inventory()[0]!=fingerprint:raise RuntimeError('Sources changed during shot build; reload before continuing')
    print(f'Shot build: {rendered} rendered, {reused} reused after verification.',flush=True)
    return manifest_path

def mux_master(p,picture,output):
    from .verify import project_audio_comparison
    picture=Path(picture);output=Path(output)
    _protect_output_inputs(p,[output],inputs=[picture])
    output.parent.mkdir(parents=True,exist_ok=True)
    inputs=(sha(picture),sha(p.audio))
    with _candidate_directory(prefix='.mux-',dir=output.parent) as folder:
        candidate=Path(folder)/'master.mp4'
        video=ffmpeg.input(str(picture)).video;audio=ffmpeg.input(str(p.audio)).audio
        graph=ffmpeg.output(video,audio,str(candidate),vcodec='copy',acodec='aac',audio_bitrate='320k',ar=48000,ac=2,t=p.frames/p.fps,movflags='+faststart',**{'bsf:v':BSF},**COLOR)
        _run_ffmpeg(graph);_validate_video(candidate,p,p.frames,with_audio=True)
        project_audio_comparison(p,candidate)
        if inputs!=(sha(picture),sha(p.audio)):
            raise RuntimeError('Picture or source audio changed during muxing')
        candidate.replace(output)


def assemble(p):
    """Assemble the editorial bodies with FFmpeg, leaving shot handles out of the master."""
    from .validation import validate_shot_set
    output=p.output/'assembly.mp4'
    _protect_output_inputs(p,[output])
    manifest=validate_shot_set(p);streams=[];inputs=[]
    manifest_sha=sha(p.output/'shots.json')
    for s in p.edit['scenes']:
        rec=manifest['shots'][s['id']];file=p.output/'shots'/Path(rec['file']).name
        inputs.append((file,rec['sha256']))
        # Trimming uses integer frame boundaries; timestamps restart before concat.
        stream=ffmpeg.input(str(file),threads=1).video.filter('trim',start_frame=rec['sourceStart'],end_frame=rec['sourceStart']+rec['bodyFrames']).filter('setpts','PTS-STARTPTS')
        streams.append(stream)
    output.parent.mkdir(parents=True,exist_ok=True)
    with _candidate_directory(prefix='.assembly-',dir=output.parent) as folder:
        picture=Path(folder)/'picture.mp4';candidate=Path(folder)/'assembly.mp4'
        graph=ffmpeg.output(ffmpeg.concat(*streams,v=1,a=0),str(picture),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=p.fps,threads=6,movflags='+faststart',**COLOR).global_args('-filter_complex_threads','2','-hide_banner','-loglevel','error')
        _run_ffmpeg(graph)
        mux_master(p,picture,candidate)
        if p.source_inventory()[0]!=manifest['sourceFingerprint']:
            raise RuntimeError('Sources changed during assembly; rebuild before export')
        if sha(p.output/'shots.json')!=manifest_sha or any(sha(file)!=digest for file,digest in inputs):
            raise RuntimeError('Shot media or manifest changed during assembly')
        candidate.replace(output)
    return output
