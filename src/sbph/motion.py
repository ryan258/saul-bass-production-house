"""Motion Canvas backend: official browser renderer, shared delivery encoding."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile, time, wave
from fractions import Fraction
import ffmpeg
from PIL import Image, ImageDraw, ImageFont
from .project import FRAMEWORK, binary, dump, sha
from .media import COLOR, BSF, probe, _run_ffmpeg, _promote_files
from .fingerprint import BUILD_SCHEMA,browser_identity,digest


def source(p, override=None):
    path=Path(override).resolve() if override else (p.root/p.data.get('motion_canvas','motion-canvas/shutdown-proof-v01/project.ts')).resolve()
    if not path.is_file():raise ValueError('Motion Canvas project missing: '+str(path))
    return path


def editor(p, override=None):
    subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/render.mjs'),'editor',str(source(p,override)),str(p.output/'motion-canvas/editor-exports')],check=True)


def pcm(path):
    return subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(path),'-map','0:a:0','-f','s16le','-acodec','pcm_s16le','pipe:1'])


def verify_audio_window(p, project, spec):
    for key in ['sourceStartFrame','sourceStartSample','frames','sourceSamples','fps']:
        if type(spec.get(key)) is not int or spec[key]<(0 if key.startswith('sourceStart') else 1):
            raise ValueError('Invalid proof range field: '+key)
    with wave.open(str(p.audio),'rb') as r:
        rate=r.getframerate();channels=r.getnchannels();width=r.getsampwidth()
        expected_start=Fraction(spec['sourceStartFrame']*rate,spec['fps'])
        expected_samples=Fraction(spec['frames']*rate,spec['fps'])
        if expected_start!=spec['sourceStartSample'] or expected_samples!=spec['sourceSamples']:
            raise ValueError('Proof frame and audio sample ranges disagree')
        if spec['sourceStartSample']+spec['sourceSamples']>r.getnframes():
            raise ValueError('Proof audio window extends beyond the source WAV')
        r.setpos(spec['sourceStartSample']);expected=r.readframes(spec['sourceSamples'])
    with wave.open(str(project.parent/'audio.wav'),'rb') as r:
        if (r.getframerate(),r.getnchannels(),r.getsampwidth())!=(rate,channels,width):
            raise ValueError('Editor WAV format differs from source')
        if r.getnframes()!=spec['sourceSamples']:raise ValueError('Editor WAV sample count differs from proof range')
        actual=r.readframes(r.getnframes())
    expected_bytes=spec['sourceSamples']*channels*width
    if len(expected)!=expected_bytes or len(actual)!=expected_bytes:raise ValueError('Short WAV read in proof audio window')
    if actual!=expected:raise ValueError('Editor WAV is not the exact original audio window')
    return hashlib.sha256(actual).hexdigest()


def validate_baseline(p, project, spec, baseline):
    """Bind A/B audio to the intended source interval before any render starts.

    Original proof sidecars lack an audio-source hash. They remain usable only
    after their file hash, interval, media metadata, and actual audio pass.
    """
    from .verify import audio_comparison
    if not baseline.is_file():raise ValueError('Build the original proof first')
    sidecar=baseline.with_suffix('.json')
    if not sidecar.is_file():raise ValueError('Baseline proof metadata is missing: '+str(sidecar))
    metadata=json.loads(sidecar.read_text())
    if any(type(metadata.get(k)) is not int or metadata[k]!=spec[k] for k in ['sourceStartFrame','frames','fps']):
        raise ValueError('Baseline proof source window or rate differs from Motion Canvas proof')
    if metadata.get('sha256')!=sha(baseline):raise ValueError('Baseline proof hash differs from its metadata')
    if metadata.get('sourceAudioSha256',sha(p.audio))!=sha(p.audio):raise ValueError('Baseline proof uses a different source recording')
    info=probe(baseline);video=next((s for s in info['streams'] if s['codec_type']=='video'),None)
    if video is None or int(video.get('nb_frames',-1))!=spec['frames'] or Fraction(video['avg_frame_rate'])!=spec['fps'] or (video['width'],video['height'])!=(spec['width'],spec['height']):
        raise ValueError('Baseline proof media does not match the requested range, rate, or size')
    audio=next((s for s in info['streams'] if s['codec_type']=='audio'),None)
    if audio is None or abs(float(audio.get('duration',-1))-spec['frames']/spec['fps'])>1024/int(audio['sample_rate']):
        raise ValueError('Baseline proof audio duration differs from requested source window')
    with wave.open(str(project.parent/'audio.wav'),'rb') as reader:
        if int(audio['sample_rate'])!=reader.getframerate() or audio['channels']!=reader.getnchannels():
            raise ValueError('Baseline proof audio format differs from the verified editor WAV')
    return audio_comparison(project.parent/'audio.wav',baseline)


def motion_inventory(project):
    return {f.resolve():sha(f) for f in project.parent.rglob('*') if f.is_file() and not any(part in {'node_modules','.vite','__pycache__','.git'} for part in f.relative_to(project.parent).parts)}


def comparison(baseline, new, output, work, spec):
    """Two pictures, one unchanged AAC track, labels outside the images."""
    header=work/'labels.png'
    im=Image.new('RGB',(1920,60),'#13252B');draw=ImageDraw.Draw(im)
    from .review import label_font
    font=label_font(24)
    draw.text((24,16),'A  ORIGINAL SVG / SHARP',font=font,fill='#E7D9BB')
    draw.text((984,16),'B  MOTION CANVAS / NATIVE TWEENS',font=font,fill='#E7D9BB')
    im.save(header)
    a=ffmpeg.input(str(baseline)).video.filter('scale',960,540)
    b=ffmpeg.input(str(new)).video.filter('scale',960,540)
    label=ffmpeg.input(str(header),loop=1,framerate=spec['fps']).video
    picture=ffmpeg.filter([label,ffmpeg.filter([a,b],'hstack',inputs=2)],'vstack',inputs=2)
    graph=ffmpeg.output(picture,ffmpeg.input(str(baseline)).audio,str(output),
        vcodec='libx264',crf=18,preset='medium',pix_fmt='yuv420p',r=spec['fps'],threads=6,
        acodec='copy',t=spec['frames']/spec['fps'],movflags='+faststart',**{'bsf:v':BSF},**COLOR)
    _run_ffmpeg(graph.global_args('-hide_banner','-loglevel','error','-filter_complex_threads','2'))


def build(p, override=None, keep_frames=False):
    project=source(p,override)
    out=(p.output/'motion-canvas').resolve()
    if out.is_relative_to(project.parent) or project.parent.is_relative_to(out):
        raise ValueError('Keep Motion Canvas proof sources and output in separate folders')
    baseline=(p.root/p.data.get('motion_baseline','production/proof.mp4')).resolve()
    final=out/'unit-9-shutdown-motion-canvas.mp4';compare=out/'unit-9-shutdown-comparison.mp4'
    managed=[final,compare,out/'proof.json',out/'source-frames',out/'render-work']
    for file in [Path(p.audio).resolve(),baseline,baseline.with_suffix('.json').resolve()]:
        if any(file.is_relative_to(target.resolve()) for target in managed):
            raise ValueError('Motion proof original audio and baseline must be outside managed output paths: '+str(file))
    initial_sources=motion_inventory(project)
    spec=json.loads((project.parent/'proof.json').read_text())
    baseline_sha=sha(baseline)
    baseline_metadata_sha=sha(baseline.with_suffix('.json'))
    original_audio_sha=sha(p.audio)
    cropped_pcm_sha=verify_audio_window(p,project,spec)
    baseline_audio=validate_baseline(p,project,spec,baseline)
    build_fingerprint,build_inventory=p.source_inventory()
    framework_sources={f:sha(FRAMEWORK/f) for f in ['motion-canvas/render.mjs','motion-canvas/render.html','motion-canvas/vite.config.ts','motion-canvas/typecheck.mjs']}
    browser=browser_identity()
    motion_fingerprint=digest({'build':build_fingerprint,'sources':{str(f):value for f,value in initial_sources.items()},'framework':framework_sources,'baseline':baseline_sha,'baselineMetadata':baseline_metadata_sha,'browser':browser})
    def check_sources():
        if sha(baseline)!=baseline_sha or sha(baseline.with_suffix('.json'))!=baseline_metadata_sha:
            raise RuntimeError('Original proof or baseline metadata changed')
        if sha(p.audio)!=original_audio_sha:raise RuntimeError('Original WAV changed')
        if motion_inventory(project)!=initial_sources:
            raise RuntimeError('Motion Canvas source or cue metadata changed during rendering')
        if p.source_inventory()[0]!=build_fingerprint or any(sha(FRAMEWORK/f)!=value for f,value in framework_sources.items()) or browser_identity()!=browser:
            raise RuntimeError('Production configuration, framework, or tools changed during Motion Canvas delivery')

    out.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.proof-build-',dir=out)).resolve()
    began=time.perf_counter()
    try:
        copied=stage/'source'
        shutil.copytree(project.parent,copied,ignore=shutil.ignore_patterns('node_modules','.git','.vite','__pycache__'))
        copied_project=copied/project.name
        original={str(f.relative_to(project.parent)):value for f,value in initial_sources.items()}
        if {str(f.relative_to(copied)):value for f,value in motion_inventory(copied_project).items()}!=original:
            raise RuntimeError('Motion Canvas source changed while taking render snapshot')
        subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/typecheck.mjs'),str(copied_project)],check=True)
        work=stage/'render-work';work.mkdir()
        subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/render.mjs'),'render',str(copied_project),str(work)],check=True)
        check_sources()
        frames=sorted((work/'frames').glob('*.png'))
        if [f.name for f in frames]!=[f'{i:06}.png' for i in range(spec['frames'])]:
            raise RuntimeError(f'Incomplete Motion Canvas sequence: {len(frames)} frames')
        picture=stage/'picture.mp4';candidate=stage/final.name;candidate_compare=stage/compare.name
        video=ffmpeg.input(str(work/'frames/%06d.png'),framerate=spec['fps']).video.filter('scale',out_color_matrix='bt709',out_range='tv')
        graph=ffmpeg.output(video,str(picture),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=spec['fps'],threads=6,g=spec['fps'],**COLOR)
        _run_ffmpeg(graph.global_args('-hide_banner','-loglevel','error'))
        graph=ffmpeg.output(ffmpeg.input(str(picture)).video,ffmpeg.input(str(baseline)).audio,str(candidate),
            vcodec='copy',acodec='copy',t=spec['frames']/spec['fps'],movflags='+faststart',**{'bsf:v':BSF},**COLOR)
        _run_ffmpeg(graph.global_args('-hide_banner','-loglevel','error'))
        comparison(baseline,candidate,candidate_compare,work,spec)
        decoded_hash=hashlib.sha256(pcm(baseline)).hexdigest()
        for file in [candidate,candidate_compare]:
            streams=probe(file)['streams'];v=next(s for s in streams if s['codec_type']=='video')
            if int(v.get('nb_frames',-1))!=spec['frames'] or v['avg_frame_rate']!=f"{spec['fps']}/1":
                raise RuntimeError('Delivery frame count/rate mismatch')
            expected_size=(spec['width'],spec['height']) if file==candidate else (1920,600)
            if (v['width'],v['height'])!=expected_size:raise RuntimeError('Delivery size mismatch')
            expected_color={'color_primaries':'bt709','color_transfer':'iec61966-2-1','color_space':'bt709','color_range':'tv'}
            if any(v.get(k)!=value for k,value in expected_color.items()):raise RuntimeError('Delivery color tags mismatch')
            if hashlib.sha256(pcm(file)).hexdigest()!=decoded_hash:raise RuntimeError('Comparison audio changed')
        qa=stage/'source-frames';qa.mkdir()
        selected=sorted({len(frames)-1}|{i for i in [0,75,87,99,141,188,210,231,267,312,366,449] if i<len(frames)})
        for index in selected:shutil.copy2(frames[index],qa/frames[index].name)
        check_sources()
        record={
            'schemaVersion':BUILD_SCHEMA,'sourceFingerprint':motion_fingerprint,'buildInventory':build_inventory,'browserIdentity':browser,
            'engine':'Motion Canvas 3.17.2 / official Renderer + ImageExporter',
            'file':str(p.public_path(final)), 'comparison':str(p.public_path(compare)),
            'sha256':sha(candidate),'comparisonSha256':sha(candidate_compare), 'baselineSha256':baseline_sha,
            'sourceAudioSha256':original_audio_sha,
            'baselineMetadataSha256':baseline_metadata_sha,'baselineAudioVerification':baseline_audio,
            'sourceStartFrame':spec['sourceStartFrame'],'frames':spec['frames'],'fps':spec['fps'],
            'duration':spec['frames']/spec['fps'],'cuts':spec['cuts'],
            'editorWavPcmSha256':cropped_pcm_sha,'decodedDeliveryPcmSha256':decoded_hash,
            'audio':'AAC track stream-copied from original proof; decoded PCM identical in A, B and comparison.',
            'color':COLOR,'renderAndEncodeSeconds':round(time.perf_counter()-began,3),
            'creativeDifferences':spec['notes'],
            'sourceInventory':[{'file':str(f.relative_to(project.parent)),'sha256':initial_sources[f]} for f in sorted(initial_sources)],
            'frameworkInventory':[{'file':f,'sha256':sha(FRAMEWORK/f)} for f in ['motion-canvas/render.mjs','motion-canvas/render.html','motion-canvas/vite.config.ts','motion-canvas/typecheck.mjs','src/sbph/motion.py','package-lock.json']],
            'sourceFrames':[{'file':'source-frames/'+f.name,'sha256':sha(f)} for f in sorted(qa.glob('*.png'))],
            'retainedRenderWork':keep_frames,
        }
        receipt=stage/'proof.json';dump(receipt,record)
        check_sources()
        pairs=[(candidate,final),(candidate_compare,compare),(receipt,out/'proof.json'),(qa,out/'source-frames')]
        if keep_frames:pairs.append((work,out/'render-work'))
        _promote_files(pairs,stage,remove=() if keep_frames else (out/'render-work',))
    except BaseException:
        print('Motion proof failed; diagnostic work retained: '+str(stage),file=sys.stderr)
        raise
    else:
        try:shutil.rmtree(stage)
        except BaseException:
            print('Motion proof delivered; temporary work could not be removed: '+str(stage),file=sys.stderr)
    print(json.dumps({key:record[key] for key in ['file','comparison','frames','fps','duration','audio','renderAndEncodeSeconds']},indent=2))
    return final
