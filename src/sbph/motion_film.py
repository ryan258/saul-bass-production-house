"""Bounded, resumable full-film renders using Motion Canvas's official renderer."""
from pathlib import Path
from fractions import Fraction
import copy, hashlib, io, json, shutil, subprocess, time
import ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .project import FRAMEWORK, binary, dump, sha
from .media import COLOR, BSF, probe, _run_ffmpeg, _promote_files, _candidate_directory
from .motion import pcm, verify_audio_window
from .fingerprint import browser_identity, runtime_identity, digest

CACHE_SCHEMA=2
QA_FRAMES={0,456,669,1157,1228,1290,2700,5044,5292,5673,5739,6549,6975,7193}


def source(p,override=None):
    file=Path(override).resolve() if override else (p.root/p.data.get('motion_canvas_full','motion-canvas/full-film-v01/project.ts')).resolve()
    if not file.is_file():raise ValueError('Full Motion Canvas source is missing: '+str(file))
    return file


def editor(p,override=None):
    subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/render.mjs'),'editor',str(source(p,override)),str(p.output/'motion-canvas-full/editor-exports')],check=True)


def inventory(project):
    records=[];semantic=[]
    for file in sorted(project.parent.rglob('*')):
        if not file.is_file() or any(part in {'node_modules','__pycache__','.vite','.git'} for part in file.relative_to(project.parent).parts):continue
        relative=str(file.relative_to(project.parent))
        records.append({'file':relative,'sha256':sha(file)})
        if file.name=='project.meta':continue # Delivery settings are explicitly supplied to Renderer.
        if file.suffix=='.meta':
            data=json.loads(file.read_text())
            # SceneMetadata includes the random seed, version and custom fields.
            # EditableTimeEvents computes these three event fields in memory;
            # ReadOnlyTimeEvents uses the saved name/targetTime during rendering.
            # Keep all other metadata conservatively, including unknown fields.
            if 'timeEvents' in data:
                data['timeEvents']=sorted(
                    ({key:value for key,value in event.items() if key not in {'initialTime','offset','stack'}} for event in data['timeEvents']),
                    key=lambda event:json.dumps(event,sort_keys=True))
            semantic.append((relative,data))
        else:semantic.append((relative,sha(file)))
    for name in ['motion-canvas/render.mjs','motion-canvas/render.html','motion-canvas/vite.config.ts','motion-canvas/typecheck.mjs','src/sbph/motion_film.py','src/sbph/motion.py','src/sbph/media.py','src/sbph/project.py','src/sbph/fingerprint.py','package-lock.json','requirements.lock']:
        label='framework:'+name;value=sha(FRAMEWORK/name)
        semantic.append((label,value));records.append({'file':label,'sha256':value})
    runtime={'tools':runtime_identity(),'browser':browser_identity()}
    semantic.append(('runtime:specification',runtime))
    records.append({'file':'runtime:specification','sha256':digest(runtime),'specification':runtime})
    fingerprint=hashlib.sha256(json.dumps(semantic,sort_keys=True).encode()).hexdigest()
    return fingerprint,records


def effective_plan(plan,meta):
    """Use the editor's saved cue positions without making users retype JSON."""
    result=copy.deepcopy(plan);fps=plan['fps']
    events={e['name']:round(e['targetTime']*fps) for e in meta['timeEvents']}
    def frame(name):
        if name not in events:raise ValueError('Missing Motion Canvas event: '+name)
        return events[name]
    if frame('cut-end')!=plan['frames']:raise ValueError('Keep the end event at the full original audio duration')
    for i,shot in enumerate(result['scenes']):
        shot['start']=0 if i==0 else frame('cut-'+shot['id'])
        shot['end']=frame('cut-'+result['scenes'][i+1]['id']) if i+1<len(result['scenes']) else frame('cut-end')
        for action in shot['animations']:
            action['startFrame']=frame(action['startEvent']);action['endFrame']=frame(action['endEvent'])
        for hit in shot.get('pulses',[]):
            length=hit['endFrame']-hit['frame'];hit['frame']=frame(hit['startEvent']);hit['endFrame']=hit['frame']+length
    return result


def validate_plan(plan,meta):
    shots=plan['scenes'];fps=plan['fps'];frames=plan['frames']
    if not shots or shots[0]['start']!=0 or shots[-1]['end']!=frames:raise ValueError('Motion edit must cover the complete recording')
    events={e['name']:round(e['targetTime']*fps) for e in meta['timeEvents']}
    if len(events)!=len(meta['timeEvents']):raise ValueError('Duplicate Motion Canvas event names')
    for i,shot in enumerate(shots):
        if shot['end']<=shot['start'] or i and shots[i-1]['end']!=shot['start']:raise ValueError('Motion edit has a gap or overlap')
        if i and events.get('cut-'+shot['id'])!=shot['start']:raise ValueError('Cut event disagrees with narration edit')
        intervals={}
        for action in shot['animations']:
            a,b=action['startFrame'],action['endFrame']
            if not shot['start']<=a<b<=shot['end']:raise ValueError('Animation crosses a shot boundary')
            if events.get(action['startEvent'])!=a or events.get(action['endEvent'])!=b:raise ValueError('Action event disagrees with edit')
            intervals.setdefault(action['signal'],[]).append((a,b))
        for pairs in intervals.values():
            pairs.sort()
            if any(b>c for (a,b),(c,d) in zip(pairs,pairs[1:])):raise ValueError('Two animations compete for the same signal')
        for hit in shot['accents']:
            if not shot['start']<=hit['frame']<shot['end']:raise ValueError('Hit lies outside its shot')
    if events.get('cut-end')!=frames:raise ValueError('End event does not match recording')


def render(project,work,start,count,samples=None):
    options={'startFrame':start,'frames':count,'logEvery':600}
    if samples is not None:options['sampleFrames']=samples
    result=subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/render.mjs'),'render',str(project),str(work),json.dumps(options)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:raise RuntimeError('Motion Canvas render failed:\n'+result.stderr[-5000:]+'\n'+result.stdout[-5000:])
    lines=[line for line in result.stdout.splitlines() if line.startswith('{')]
    if not lines:raise RuntimeError('Renderer returned no completion record')
    return json.loads(lines[-1])


def encode(work,output,start,count,fps,width,height):
    files=sorted((work/'frames').glob('*.png'))
    if [f.name for f in files]!=[f'{i:06}.png' for i in range(start,start+count)]:raise RuntimeError('Incomplete or incorrectly numbered image sequence')
    video=ffmpeg.input(str(work/'frames/%06d.png'),start_number=start,framerate=fps).video.filter('scale',out_color_matrix='bt709',out_range='tv')
    graph=ffmpeg.output(video,str(output),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=fps,threads=6,g=fps,vframes=count,**{'bsf:v':BSF},**COLOR)
    _run_ffmpeg(graph.global_args('-hide_banner','-loglevel','error'))
    check_video(output,count,fps,(width,height))


def check_video(file,count,fps,size,with_audio=False):
    streams=probe(file)['streams'];videos=[s for s in streams if s.get('codec_type')=='video'];audios=[s for s in streams if s.get('codec_type')=='audio']
    if len(videos)!=1 or len(audios)!=(1 if with_audio else 0):raise RuntimeError('Delivered stream count mismatch')
    video=videos[0]
    if int(video.get('nb_frames',-1))!=count or Fraction(video['avg_frame_rate'])!=fps:raise RuntimeError('Delivered frame count/rate mismatch')
    if (video['width'],video['height'])!=size:raise RuntimeError('Delivered dimensions mismatch')
    expected={'color_primaries':'bt709','color_transfer':'iec61966-2-1','color_space':'bt709','color_range':'tv'}
    if any(video.get(k)!=v for k,v in expected.items()):raise RuntimeError('Delivered color tags mismatch')
    return video


def decode_frames(movie,frames,folder,size=None):
    frames=sorted(set(frames));folder.mkdir(parents=True,exist_ok=True)
    expression='+'.join(f'eq(n\\,{frame})' for frame in frames)
    filters='select='+expression+',scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int'
    if size:filters+=f',scale={size[0]}:{size[1]}'
    subprocess.run([binary('ffmpeg'),'-v','error','-i',str(movie),'-vf',filters,'-fps_mode','vfr','-frames:v',str(len(frames)),'-start_number','0',str(folder/'%06d.png')],check=True)
    images=sorted(folder.glob('*.png'))
    if len(images)!=len(frames):raise RuntimeError('Decoded sample set is incomplete')
    return dict(zip(frames,images))


def contact_sheets(movie,plan,out):
    """Decode the full movie once for all 57 storyboard samples."""
    from .review import label_font
    font=label_font(14)
    shots=plan['scenes'];audit=[];folder=out/'decoded-storyboard-work'
    if folder.exists():shutil.rmtree(folder)
    samples=decode_frames(movie,[(s['start']+s['end']-1)//2 for s in shots],folder,(426,240))
    for page in range((len(shots)+11)//12):
        group=shots[page*12:(page+1)*12];im=Image.new('RGB',(1280,4*265),'#13252B');draw=ImageDraw.Draw(im)
        for i,shot in enumerate(group):
            frame=(shot['start']+shot['end']-1)//2;x=(i%3)*426;y=(i//3)*265
            with Image.open(samples[frame]) as pic:im.paste(pic,(x,y+25))
            draw.text((x+7,y+5),f"{shot['id']} | {frame/plan['fps']:.2f}s | {shot['name'][:33]}",font=font,fill='#E7D9BB')
            audit.append({'shot':shot['id'],'frame':frame})
        im.save(out/f'decoded-shots-{page+1:02}.jpg',quality=94)
    shutil.rmtree(folder)
    return audit


def quality_checks(movie,qa,out):
    sources=sorted(qa.glob('*.png'));folder=out/'decoded-quality-work'
    if folder.exists():shutil.rmtree(folder)
    samples=decode_frames(movie,[int(f.stem) for f in sources],folder)
    checks=[]
    for file in sources:
        frame=int(file.stem)
        with Image.open(file) as im:a=np.asarray(im.convert('RGB')).astype(np.float32)
        with Image.open(samples[frame]) as im:b=np.asarray(im.convert('RGB')).astype(np.float32)
        error=float(np.abs(a-b).mean());checks.append({'frame':frame,'rgbMeanAbsoluteError':round(error,4)})
        if error>3:raise RuntimeError(f'Encoded picture differs excessively at frame {frame}: {error}')
    shutil.rmtree(folder)
    return checks


def _cut_audit(audit,expected,start,count):
    if not isinstance(audit,dict) or any(key not in expected or type(frame) is not int or frame!=expected[key] for key,frame in audit.items()):
        raise RuntimeError('Native cut audit disagrees with the current edit')
    if any(key not in audit for key,frame in expected.items() if start<=frame<start+count):
        raise RuntimeError('Native cut audit is incomplete for the rendered section')
    return audit


def _qa_records(folder,frames,size):
    expected=[f'{frame:06}.png' for frame in sorted(frames)]
    if sorted(file.name for file in folder.iterdir())!=expected:
        raise RuntimeError('Section source-frame evidence is incomplete')
    records=[]
    for name in expected:
        file=folder/name
        with Image.open(file) as image:
            if image.size!=size:raise RuntimeError('Section source-frame dimensions differ from the edit')
            image.verify()
        records.append({'file':name,'sha256':sha(file)})
    return records


def _reusable_chunk(row,file,qa,start,count,spec,selected,expected_cuts):
    if not isinstance(row,dict):return False
    expected={'start':start,'frames':count,'fps':spec['fps'],'width':spec['width'],'height':spec['height']}
    if any(type(row.get(key)) is not int or row[key]!=value for key,value in expected.items()):return False
    try:
        if not file.is_file() or sha(file)!=row.get('sha256'):return False
        check_video(file,count,spec['fps'],(spec['width'],spec['height']))
        _cut_audit(row.get('cutAudit'),expected_cuts,start,count)
        evidence_matches=_qa_records(qa,selected,(spec['width'],spec['height']))==row.get('sourceFrames')
        return evidence_matches and sha(file)==row.get('sha256')
    except (OSError,ValueError,KeyError,TypeError,RuntimeError,ffmpeg.Error):return False


def _protect_inputs(out,audio,baseline,page_count):
    """Managed output replacement must never consume an original input."""
    chunks=out/'chunks'
    if chunks.is_symlink():raise ValueError('Full-film chunk directory must not be a symlink')
    managed=[chunks,out/'chunks.json',out/'unit-9-motion-canvas-v01.mp4',
        out/'verification.json',out/'effective-edit.json',out/'source-frames',
        *out.glob('decoded-shots-*.jpg'),
        *[out/f'decoded-shots-{page+1:02}.jpg' for page in range(page_count)]]
    for file in [Path(audio).resolve(),baseline.resolve()]:
        if any(file.is_relative_to(target.resolve()) for target in managed):
            raise ValueError('Full-film original audio and baseline must be outside managed output paths: '+str(file))


def build(p,override=None,chunk_frames=600):
    project=source(p,override);out=(p.output/'motion-canvas-full').resolve()
    if out.is_relative_to(project.parent) or project.parent.is_relative_to(out):
        raise ValueError('Motion Canvas source and full-film output directories must not overlap')
    fingerprint,source_inventory=inventory(project)
    spec=json.loads((project.parent/'proof.json').read_text());plan=json.loads((project.parent/'edit.json').read_text())
    meta=json.loads((project.parent/(spec.get('scene','film')+'.meta')).read_text())
    plan=effective_plan(plan,meta);validate_plan(plan,meta)
    for key in ['frames','fps','width','height']:
        if type(spec.get(key)) is not int or spec[key]<1:raise ValueError('Invalid full-film render field: '+key)
    if spec['width']%2 or spec['height']%2:raise ValueError('Full-film delivery requires even dimensions')
    if spec['frames']!=plan['frames'] or spec['fps']!=plan['fps']:raise ValueError('Render and edit frame ranges disagree')
    if type(chunk_frames) is not int or chunk_frames<30 or chunk_frames%spec['fps']:raise ValueError('Use whole-second chunks of at least one second')
    baseline=(p.root/p.data.get('motion_full_baseline','unit-9-svg-film-v01.mp4')).resolve()
    _protect_inputs(out,p.audio,baseline,(len(plan['scenes'])+11)//12)
    baseline_sha=sha(baseline);audio_sha=sha(p.audio)
    if audio_sha!=plan['sourceAudioSha256'] or sha(project.parent/'audio.wav')!=audio_sha:raise ValueError('Full original audio identity changed')
    window_sha=verify_audio_window(p,project,spec)
    out.mkdir(parents=True,exist_ok=True);chunks=out/'chunks';chunks.mkdir(exist_ok=True);cache=out/'chunks.json'
    header={'schemaVersion':CACHE_SCHEMA,'sourceFingerprint':fingerprint,'chunkFrames':chunk_frames,
        'renderSpecification':{key:spec[key] for key in ['frames','fps','width','height']}}
    prior=json.loads(cache.read_text()) if cache.exists() else {}
    compatible=isinstance(prior,dict) and all(prior.get(key)==value for key,value in header.items())
    total=(spec['frames']+chunk_frames-1)//chunk_frames
    entries={key:value for key,value in prior.get('chunks',{}).items() if key in {str(i) for i in range(total)}} \
        if compatible and isinstance(prior.get('chunks'),dict) else {}
    selected={frame for frame in QA_FRAMES|{spec['frames']-1} if frame<spec['frames']}
    began=time.perf_counter();render_seconds=0;full_audit={};expected_cuts={s['id']:s['start'] for s in plan['scenes']}
    final=out/'unit-9-motion-canvas-v01.mp4'
    # Scratch cleanup must not turn a promoted, verified delivery into a failure.
    with _candidate_directory(prefix='.motion-film-',dir=out) as temporary:
        stage=Path(temporary);copied=stage/'source'
        shutil.copytree(project.parent,copied,ignore=shutil.ignore_patterns('node_modules','.git','.vite','__pycache__'))
        render_project=copied/project.name
        if inventory(project)[0]!=fingerprint or inventory(render_project)[0]!=fingerprint:
            raise RuntimeError('Source or timing changed while preparing the render')
        subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/typecheck.mjs'),str(render_project)],check=True)
        qa=stage/'source-frames';qa.mkdir();linked=stage/'concat-chunks';linked.mkdir();used=[]
        for index,start in enumerate(range(0,spec['frames'],chunk_frames)):
            count=min(chunk_frames,spec['frames']-start);file=chunks/f'{index:03}.mp4';key=str(index);chunk_qa=chunks/f'{index:03}.source-frames'
            section_frames={frame for frame in selected if start<=frame<start+count};old=entries.get(key)
            if _reusable_chunk(old,file,chunk_qa,start,count,spec,section_frames,expected_cuts):
                print(f'Motion Canvas section {index+1}: reusing verified frames {start}–{start+count-1}.',flush=True)
            else:
                with _candidate_directory(prefix='.section-',dir=stage) as section:
                    work=Path(section);result=render(render_project,work,start,count)
                    if result.get('result')!=0 or result.get('errors'):raise RuntimeError('Motion Canvas did not report successful section completion')
                    audit=_cut_audit(result.get('cutAudit'),expected_cuts,start,count)
                    candidate=work/'section.mp4';encode(work,candidate,start,count,spec['fps'],spec['width'],spec['height'])
                    evidence=work/'source-frames';evidence.mkdir()
                    for frame in section_frames:shutil.copy2(work/'frames'/f'{frame:06}.png',evidence/f'{frame:06}.png')
                    old={'start':start,'frames':count,'fps':spec['fps'],'width':spec['width'],'height':spec['height'],
                        'sha256':sha(candidate),'cutAudit':audit,'renderSeconds':result.get('renderSeconds',0),
                        'sourceFrames':_qa_records(evidence,section_frames,(spec['width'],spec['height']))}
                    updated={**entries,key:old};staged_cache=work/'chunks.json';dump(staged_cache,{**header,'chunks':updated})
                    if inventory(project)[0]!=fingerprint or inventory(render_project)[0]!=fingerprint:
                        raise RuntimeError('Source or timing changed during render; previous section and cache preserved')
                    _promote_files([(candidate,file),(evidence,chunk_qa),(staged_cache,cache)],work)
                    entries=updated
                    render_seconds+=old['renderSeconds']
                print(f'Motion Canvas section {index+1}/{total}: frames {start}–{start+count-1} verified.',flush=True)
            full_audit.update(old['cutAudit'])
            chunk=linked/f'{index:03}.mp4';chunk.hardlink_to(file)
            if sha(chunk)!=old['sha256']:raise RuntimeError('Section changed while preparing assembly')
            used.append((chunk,old['sha256']))
            for row in old['sourceFrames']:
                target=qa/row['file'];shutil.copy2(chunk_qa/row['file'],target)
                if sha(target)!=row['sha256']:raise RuntimeError('Section source-frame evidence changed during assembly')
        if full_audit!=expected_cuts:raise RuntimeError('Native cut audit is incomplete')
        listing=stage/'concat.txt';listing.write_text(''.join(f"file 'concat-chunks/{i:03}.mp4'\n" for i in range(total)))
        picture=ffmpeg.input(str(listing),format='concat',safe=1).video;candidate=stage/final.name
        graph=ffmpeg.output(picture,ffmpeg.input(str(baseline)).audio,str(candidate),vcodec='copy',acodec='copy',t=spec['frames']/spec['fps'],movflags='+faststart',**{'bsf:v':BSF},**COLOR)
        _run_ffmpeg(graph.global_args('-hide_banner','-loglevel','error'))
        check_video(candidate,spec['frames'],spec['fps'],(spec['width'],spec['height']),with_audio=True)
        original_pcm=hashlib.sha256(pcm(baseline)).hexdigest()
        if hashlib.sha256(pcm(candidate)).hexdigest()!=original_pcm:raise RuntimeError('Delivery audio differs from original full film')
        decoded=contact_sheets(candidate,plan,stage);picture_checks=quality_checks(candidate,qa,stage)
        effective=stage/'effective-edit.json';dump(effective,plan)
        sheets=sorted(stage.glob('decoded-shots-*.jpg'))
        if len(sheets)!=(len(plan['scenes'])+11)//12:raise RuntimeError('Decoded storyboard sheet set is incomplete')
        record={'schemaVersion':CACHE_SCHEMA,'engine':'Motion Canvas 3.17.2 / official Renderer + ImageExporter','file':str(p.public_path(final)),'sha256':sha(candidate),'frames':spec['frames'],'fps':spec['fps'],'duration':spec['frames']/spec['fps'],'width':spec['width'],'height':spec['height'],'color':COLOR,'nativeShots':len(plan['scenes']),'chosenActionAccents':sum(len(s['accents']) for s in plan['scenes']),'editableEvents':len(meta['timeEvents']),'nativeCutAudit':full_audit,'sourceAudioSha256':audio_sha,'baselineSha256':baseline_sha,'editorWavPcmSha256':window_sha,'decodedDeliveryPcmSha256':original_pcm,'audio':'Original full-film AAC track stream-copied; decoded PCM identical. Editor WAV is a byte-identical copy of the original recording.','sourceFingerprint':fingerprint,'sourceInventory':source_inventory,'renderSecondsThisRun':round(render_seconds,3),'totalBuildSecondsThisRun':round(time.perf_counter()-began,3),'decodedShotSamples':decoded,'sourceToDecodedPictureChecks':picture_checks,'nativeResolveImport':'not performed; original Resolve timeline preserved','humanScreening':'not recorded for this build'}
        record['artifacts']=[{'file':str(file.relative_to(stage)),'sha256':sha(file)} for file in [candidate,effective,*sorted(qa.glob('*.png')),*sheets]]
        receipt=stage/'verification.json';dump(receipt,record)
        if sha(p.audio)!=audio_sha or sha(baseline)!=baseline_sha:raise RuntimeError('Original film or recording changed before delivery')
        if inventory(project)[0]!=fingerprint or inventory(render_project)[0]!=fingerprint:
            raise RuntimeError('Sources or rendering tools changed before delivery')
        if any(sha(file)!=value for file,value in used):raise RuntimeError('Section media changed before delivery')
        obsolete=[file for file in out.glob('decoded-shots-*.jpg') if file.name not in {sheet.name for sheet in sheets}]
        _promote_files([(candidate,final),(receipt,out/'verification.json'),(effective,out/'effective-edit.json'),(qa,out/'source-frames'),*[(sheet,out/sheet.name) for sheet in sheets]],stage,remove=obsolete)
    print(json.dumps({k:record[k] for k in ['file','frames','fps','duration','nativeShots','chosenActionAccents','audio','totalBuildSecondsThisRun']},indent=2))
    return final
