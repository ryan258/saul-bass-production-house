"""Bounded, resumable full-film renders using Motion Canvas's official renderer."""
from pathlib import Path
import copy, hashlib, io, json, shutil, subprocess, time
import ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .project import FRAMEWORK, binary, dump, sha
from .media import COLOR, BSF, probe
from .motion import pcm, verify_audio_window


def source(p,override=None):
    file=Path(override).resolve() if override else (p.root/p.data.get('motion_canvas_full','motion-canvas/full-film-v01/project.ts')).resolve()
    if not file.is_file():raise ValueError('Full Motion Canvas source is missing: '+str(file))
    return file


def editor(p,override=None):
    subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/render.mjs'),'editor',str(source(p,override)),str(p.output/'motion-canvas-full/editor-exports')],check=True)


def inventory(project):
    records=[];semantic=[]
    for file in sorted(project.parent.rglob('*')):
        if not file.is_file() or any(part in {'node_modules','__pycache__','.vite'} for part in file.parts):continue
        relative=str(file.relative_to(project.parent))
        records.append({'file':relative,'sha256':sha(file)})
        if file.name=='project.meta':continue # Delivery settings are explicitly supplied to Renderer.
        if file.suffix=='.meta':
            data=json.loads(file.read_text())
            semantic.append((relative,sorted((e['name'],round(e['targetTime'],9)) for e in data.get('timeEvents',[]))))
        else:semantic.append((relative,sha(file)))
    for name in ['motion-canvas/render.mjs','motion-canvas/render.html','motion-canvas/vite.config.ts','motion-canvas/typecheck.mjs','src/sbph/motion_film.py','package-lock.json']:
        semantic.append(('framework:'+name,sha(FRAMEWORK/name)))
    digest=hashlib.sha256(json.dumps(semantic,sort_keys=True).encode()).hexdigest()
    return digest,records


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
    ffmpeg.run(graph.global_args('-hide_banner','-loglevel','error'),cmd=binary('ffmpeg'),overwrite_output=True)
    check_video(output,count,fps,(width,height))


def check_video(file,count,fps,size):
    streams=probe(file)['streams'];video=next(s for s in streams if s['codec_type']=='video')
    if int(video.get('nb_frames',-1))!=count or video['avg_frame_rate']!=f'{fps}/1':raise RuntimeError('Delivered frame count/rate mismatch')
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
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',14)
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


def build(p,override=None,chunk_frames=600):
    project=source(p,override);spec=json.loads((project.parent/'proof.json').read_text());plan=json.loads((project.parent/'edit.json').read_text())
    meta=json.loads((project.parent/(spec.get('scene','film')+'.meta')).read_text())
    plan=effective_plan(plan,meta);validate_plan(plan,meta)
    if spec['frames']!=plan['frames'] or spec['fps']!=plan['fps']:raise ValueError('Render and edit frame ranges disagree')
    if not isinstance(chunk_frames,int) or chunk_frames<30 or chunk_frames%spec['fps']:raise ValueError('Use whole-second chunks of at least one second')
    subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/typecheck.mjs'),str(project)],check=True)
    baseline=(p.root/p.data.get('motion_full_baseline','unit-9-svg-film-v01.mp4')).resolve()
    baseline_sha=sha(baseline);audio_sha=sha(p.audio)
    if audio_sha!=plan['sourceAudioSha256'] or sha(project.parent/'audio.wav')!=audio_sha:raise ValueError('Full original audio identity changed')
    window_sha=verify_audio_window(p,project,spec)
    fingerprint,source_inventory=inventory(project)
    out=p.output/'motion-canvas-full';out.mkdir(parents=True,exist_ok=True)
    dump(out/'effective-edit.json',plan)
    chunks=out/'chunks';chunks.mkdir(exist_ok=True);qa=out/'source-frames';qa.mkdir(exist_ok=True)
    work=out/'render-work';cache=out/'chunks.json'
    prior=json.loads(cache.read_text()) if cache.exists() else {}
    entries=prior.get('chunks',{}) if prior.get('sourceFingerprint')==fingerprint else {}
    selected={0,456,669,1157,1228,1290,2700,5044,5292,5673,5739,6549,6975,7193}
    began=time.perf_counter();render_seconds=0;full_audit={}
    expected_cuts={s['id']:s['start'] for s in plan['scenes']}
    for index,start in enumerate(range(0,spec['frames'],chunk_frames)):
        count=min(chunk_frames,spec['frames']-start);file=chunks/f'{index:03}.mp4';key=str(index)
        old=entries.get(key)
        if old and old['start']==start and old['frames']==count and file.exists() and sha(file)==old['sha256']:
            full_audit.update(old.get('cutAudit',{}));print(f"Motion Canvas section {index+1}: reusing verified frames {start}–{start+count-1}.",flush=True);continue
        if work.exists():shutil.rmtree(work)
        work.mkdir();result=render(project,work,start,count)
        if result.get('errors'):raise RuntimeError('Motion Canvas reported scene errors')
        for shot,frame in (result.get('cutAudit') or {}).items():
            if expected_cuts[shot]!=frame:raise RuntimeError(f'Native cut {shot} landed on {frame}, expected {expected_cuts[shot]}')
        full_audit.update(result.get('cutAudit') or {})
        encode(work,file,start,count,spec['fps'],spec['width'],spec['height'])
        for frame in selected:
            if start<=frame<start+count:shutil.copy2(work/'frames'/f'{frame:06}.png',qa/f'{frame:06}.png')
        if inventory(project)[0]!=fingerprint:raise RuntimeError('Source or timing changed during render; resume after reviewing the edit')
        entries[key]={'start':start,'frames':count,'sha256':sha(file),'cutAudit':result.get('cutAudit'),'renderSeconds':result.get('renderSeconds')}
        dump(cache,{'sourceFingerprint':fingerprint,'chunks':entries})
        render_seconds+=result['renderSeconds'];shutil.rmtree(work)
        print(f"Motion Canvas section {index+1}/{(spec['frames']+chunk_frames-1)//chunk_frames}: frames {start}–{start+count-1} verified.",flush=True)
    if full_audit!=expected_cuts:raise RuntimeError('Native cut audit is incomplete')
    listing=out/'concat.txt'
    listing.write_text(''.join(f"file 'chunks/{i:03}.mp4'\n" for i in range((spec['frames']+chunk_frames-1)//chunk_frames)))
    picture=ffmpeg.input(str(listing),format='concat',safe=1).video
    final=out/'unit-9-motion-canvas-v01.mp4'
    graph=ffmpeg.output(picture,ffmpeg.input(str(baseline)).audio,str(final),vcodec='copy',acodec='copy',t=spec['frames']/spec['fps'],movflags='+faststart',**{'bsf:v':BSF},**COLOR)
    ffmpeg.run(graph.global_args('-hide_banner','-loglevel','error'),cmd=binary('ffmpeg'),overwrite_output=True)
    video=check_video(final,spec['frames'],spec['fps'],(spec['width'],spec['height']))
    original_pcm=hashlib.sha256(pcm(baseline)).hexdigest()
    if hashlib.sha256(pcm(final)).hexdigest()!=original_pcm:raise RuntimeError('Delivery audio differs from original full film')
    if sha(p.audio)!=audio_sha or sha(baseline)!=baseline_sha:raise RuntimeError('Original film or recording changed')
    if inventory(project)[0]!=fingerprint:raise RuntimeError('Sources changed before delivery')
    decoded=contact_sheets(final,plan,out)
    picture_checks=quality_checks(final,qa,out)
    _,source_inventory=inventory(project)
    record={'engine':'Motion Canvas 3.17.2 / official Renderer + ImageExporter','file':str(p.public_path(final)),'sha256':sha(final),'frames':spec['frames'],'fps':spec['fps'],'duration':spec['frames']/spec['fps'],'width':spec['width'],'height':spec['height'],'color':COLOR,'nativeShots':len(plan['scenes']),'chosenActionAccents':sum(len(s['accents']) for s in plan['scenes']),'editableEvents':len(json.loads((project.parent/'film.meta').read_text())['timeEvents']),'nativeCutAudit':full_audit,'sourceAudioSha256':audio_sha,'baselineSha256':baseline_sha,'editorWavPcmSha256':window_sha,'decodedDeliveryPcmSha256':original_pcm,'audio':'Original full-film AAC track stream-copied; decoded PCM identical. Editor WAV is a byte-identical copy of the original recording.','sourceFingerprint':fingerprint,'sourceInventory':source_inventory,'renderSecondsThisRun':round(render_seconds,3),'totalBuildSecondsThisRun':round(time.perf_counter()-began,3),'decodedShotSamples':decoded,'sourceToDecodedPictureChecks':picture_checks,'nativeResolveImport':'not performed; original Resolve timeline preserved','humanScreening':'Decoded storyboard and selected physical contacts reviewed; uninterrupted human screening is separate.'}
    dump(out/'verification.json',record)
    print(json.dumps({k:record[k] for k in ['file','frames','fps','duration','nativeShots','chosenActionAccents','audio','totalBuildSecondsThisRun']},indent=2))
    return final
