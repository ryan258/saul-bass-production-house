"""Motion Canvas backend: official browser renderer, shared delivery encoding."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, time, wave
from fractions import Fraction
import ffmpeg
from PIL import Image, ImageDraw, ImageFont
from .project import FRAMEWORK, binary, dump, sha
from .media import COLOR, BSF, probe
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
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',24)
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
    ffmpeg.run(graph.global_args('-hide_banner','-loglevel','error','-filter_complex_threads','2'),cmd=binary('ffmpeg'),overwrite_output=True)


def build(p, override=None, keep_frames=False):
    project=source(p,override);spec=json.loads((project.parent/'proof.json').read_text())
    baseline=(p.root/p.data.get('motion_baseline','production/proof.mp4')).resolve()
    initial_sources=motion_inventory(project)
    baseline_sha=sha(baseline)
    baseline_metadata_sha=sha(baseline.with_suffix('.json'))
    original_audio_sha=sha(p.audio)
    cropped_pcm_sha=verify_audio_window(p,project,spec)
    baseline_audio=validate_baseline(p,project,spec,baseline)
    build_fingerprint,build_inventory=p.source_inventory()
    framework_sources={f:sha(FRAMEWORK/f) for f in ['motion-canvas/render.mjs','motion-canvas/render.html','motion-canvas/vite.config.ts','motion-canvas/typecheck.mjs']}
    browser=browser_identity()
    motion_fingerprint=digest({'build':build_fingerprint,'sources':{str(f):value for f,value in initial_sources.items()},'framework':framework_sources,'baseline':baseline_sha,'baselineMetadata':baseline_metadata_sha,'browser':browser})
    subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/typecheck.mjs'),str(project)],check=True)
    out=p.output/'motion-canvas';out.mkdir(parents=True,exist_ok=True)
    work=out/'render-work'
    if work.exists():shutil.rmtree(work)
    work.mkdir()
    began=time.perf_counter()
    subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/render.mjs'),'render',str(project),str(work)],check=True)
    if motion_inventory(project)!=initial_sources:raise RuntimeError('Motion Canvas source or cue metadata changed during rendering')
    if p.source_inventory()[0]!=build_fingerprint or any(sha(FRAMEWORK/f)!=value for f,value in framework_sources.items()):
        raise RuntimeError('Production configuration, framework, or tools changed during Motion Canvas rendering')
    frames=sorted((work/'frames').glob('*.png'))
    if [f.name for f in frames]!=[f'{i:06}.png' for i in range(spec['frames'])]:
        raise RuntimeError(f'Incomplete Motion Canvas sequence: {len(frames)} frames')
    picture=out/'picture.mp4';final=out/'unit-9-shutdown-motion-canvas.mp4'
    video=ffmpeg.input(str(work/'frames/%06d.png'),framerate=spec['fps']).video.filter('scale',out_color_matrix='bt709',out_range='tv')
    graph=ffmpeg.output(video,str(picture),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=spec['fps'],threads=6,g=spec['fps'],**COLOR)
    ffmpeg.run(graph.global_args('-hide_banner','-loglevel','error'),cmd=binary('ffmpeg'),overwrite_output=True)
    graph=ffmpeg.output(ffmpeg.input(str(picture)).video,ffmpeg.input(str(baseline)).audio,str(final),
        vcodec='copy',acodec='copy',t=spec['frames']/spec['fps'],movflags='+faststart',**{'bsf:v':BSF},**COLOR)
    ffmpeg.run(graph.global_args('-hide_banner','-loglevel','error'),cmd=binary('ffmpeg'),overwrite_output=True)
    picture.unlink()
    compare=out/'unit-9-shutdown-comparison.mp4'
    comparison(baseline,final,compare,work,spec)
    decoded_hash=hashlib.sha256(pcm(baseline)).hexdigest()
    for file in [final,compare]:
        streams=probe(file)['streams'];v=next(s for s in streams if s['codec_type']=='video')
        if int(v.get('nb_frames',-1))!=spec['frames'] or v['avg_frame_rate']!=f"{spec['fps']}/1":
            raise RuntimeError('Delivery frame count/rate mismatch')
        expected_size=(spec['width'],spec['height']) if file==final else (1920,600)
        if (v['width'],v['height'])!=expected_size:raise RuntimeError('Delivery size mismatch')
        expected_color={'color_primaries':'bt709','color_transfer':'iec61966-2-1','color_space':'bt709','color_range':'tv'}
        if any(v.get(k)!=value for k,value in expected_color.items()):raise RuntimeError('Delivery color tags mismatch')
        if hashlib.sha256(pcm(file)).hexdigest()!=decoded_hash:raise RuntimeError('Comparison audio changed')
    if sha(baseline)!=baseline_sha or sha(baseline.with_suffix('.json'))!=baseline_metadata_sha:raise RuntimeError('Original proof or baseline metadata changed')
    if sha(p.audio)!=original_audio_sha:raise RuntimeError('Original WAV changed')
    if motion_inventory(project)!=initial_sources:raise RuntimeError('Motion Canvas source or cue metadata changed during rendering')
    if p.source_inventory()[0]!=build_fingerprint or any(sha(FRAMEWORK/f)!=value for f,value in framework_sources.items()) or browser_identity()!=browser:
        raise RuntimeError('Production configuration, framework, or tools changed during Motion Canvas delivery')
    record={
        'schemaVersion':BUILD_SCHEMA,'sourceFingerprint':motion_fingerprint,'buildInventory':build_inventory,'browserIdentity':browser,
        'engine':'Motion Canvas 3.17.2 / official Renderer + ImageExporter',
        'file':str(p.public_path(final)), 'comparison':str(p.public_path(compare)),
        'sha256':sha(final),'comparisonSha256':sha(compare), 'baselineSha256':baseline_sha,
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
    }
    dump(out/'proof.json',record)
    # Keep useful source frames for inspection without retaining 450 PNGs.
    qa=out/'source-frames';qa.mkdir(exist_ok=True)
    for index in [0,75,87,99,141,188,210,231,267,312,366,449]:
        shutil.copy2(frames[index],qa/frames[index].name)
    if not keep_frames:shutil.rmtree(work)
    print(json.dumps({key:record[key] for key in ['file','comparison','frames','fps','duration','audio','renderAndEncodeSeconds']},indent=2))
    return final
