"""Focused media and interchange checks, with explicit evidence limits."""
from pathlib import Path
import math,subprocess,shutil,tempfile
from fractions import Fraction
import numpy as np
from .project import binary,dump,sha
from .media import probe

def decode_mono(path):
    raw=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(path),'-ac','1','-ar','16000','-f','f32le','pipe:1'])
    return np.frombuffer(raw,dtype='<f4')


def _decode_source_window(path,start,duration):
    # Match proof encoding's source-time seek before resampling. Slicing a
    # pre-resampled waveform would round fractional 16 kHz frame boundaries
    # and introduce an artificial phase shift (e.g. frame 1 at 30 fps).
    raw=subprocess.check_output([binary('ffmpeg'),'-v','error','-ss',str(float(start)),
        '-i',str(path),'-t',str(float(duration)),'-ac','1','-ar','16000',
        '-f','f32le','pipe:1'])
    return np.frombuffer(raw,dtype='<f4')


def audio_comparison(source,delivered,*,source_window=None):
    """Compare all delivered audio against the full source or an explicit window.

    Only the source is cropped. Extra delivered audio must remain visible to
    the sample-count check, including when the original has an unused tail.
    """
    source_sha=sha(source)
    a,b=decode_mono(source),decode_mono(delivered)
    source_samples=len(a);source_window_report=None
    if source_window is not None:
        start,duration=map(Fraction,source_window)
        if start<0 or duration<=0:
            raise ValueError('Source audio window must have a nonnegative start and positive duration')
        first=round(start*16000);count=round(duration*16000)
        if count<1:raise ValueError('Source audio window is shorter than one decoded sample')
        if first+count>source_samples:
            raise ValueError('Source audio is shorter than the requested editorial window')
        a=_decode_source_window(source,start,duration) if start else a[:count]
        if len(a)!=count:
            raise ValueError('Source audio is shorter than the requested editorial window')
        source_window_report={'startSeconds':float(start),'durationSeconds':float(duration),
            'startSampleAt16k':first,'samplesAt16k':count}
    stream=next((s for s in probe(delivered)['streams'] if s['codec_type']=='audio'),None)
    if stream is None:raise ValueError('Delivery has no audio stream')
    # AAC may expose up to one padded 1024-sample packet after decoding.
    # Lossless deliveries have no sample-count tolerance.
    tolerance=math.ceil(1024*16000/int(stream['sample_rate'])) if stream.get('codec_name')=='aac' else 0
    if abs(len(b)-len(a))>tolerance:raise ValueError('Audio duration/sample count differs from source')
    n=min(len(a),len(b))
    if n<256:raise ValueError('Audio is too short for alignment verification')
    x=a[:n].astype(np.float64);y=b[:n].astype(np.float64)
    if not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Audio contains non-finite samples')
    silent=float(np.max(np.abs(x)))<1e-7
    offsets=[]
    if silent:
        if float(np.max(np.abs(y)))>1e-6:raise ValueError('Silent source acquired audible signal')
        correlation=None
        evidence='Silence only: sample count checked; temporal alignment cannot be measured.'
    else:
        x-=x.mean();y-=y.mean()
        denominator=float(np.sqrt(np.dot(x,x)*np.dot(y,y)))
        correlation=float(np.dot(x,y)/denominator) if denominator>0 else 0.0
        if not math.isfinite(correlation) or correlation<=.995:raise ValueError(f'Audio correlation failed: {correlation}')
        margin=min(max(32,tolerance+32),(n-96)//2)
        window_size=min(32000,(n-2*margin)//3)
        starts=set(int(v) for v in np.linspace(margin,n-window_size-margin,5))
        # A brief signal surrounded by silence still gets an energetic window.
        starts.add(max(margin,min(n-window_size-margin,int(np.argmax(np.abs(x)))-window_size//2)))
        for start in sorted(starts):
            window=x[start:start+window_size]
            energy=float(np.dot(window,window))
            if energy<1e-12:continue
            scores=[]
            for lag in range(-32,33):
                z=y[start+lag:start+lag+window_size]
                scores.append(float(np.dot(window,z)/(np.sqrt(energy*np.dot(z,z))+1e-12)))
            # Prefer zero when a periodic waveform yields exactly tied scores.
            lag=max(range(-32,33),key=lambda lag:(scores[lag+32],-abs(lag)))
            offsets.append({'seconds':start/16000,'estimatedOffsetSamplesAt16k':lag,'correlation':scores[lag+32]})
        if not offsets or any(abs(v['estimatedOffsetSamplesAt16k'])>1 or v['correlation']<=.995 for v in offsets):
            raise ValueError('Audio alignment failed: '+str(offsets))
        evidence='Correlation and duration-relative energetic windows checked at 16 kHz.'
    try:source_unchanged=sha(source)==source_sha
    except OSError as error:
        raise RuntimeError('Source audio changed during comparison') from error
    if not source_unchanged:raise RuntimeError('Source audio changed during comparison')
    report={'sourceSha256':source_sha,'monoCorrelationAt16k':correlation,'offsetWindows':offsets,'decodedSampleDifferenceAt16k':len(b)-len(a),'allowedSampleDifferenceAt16k':tolerance,'alignmentEvidence':evidence,'note':'AAC is lossy. Correlation does not assert bit-identical PCM; silence cannot establish temporal alignment.'}
    if source_window_report is not None:
        report.update({'sourceWindow':source_window_report,'decodedSourceSamplesAt16k':source_samples,
            'comparedSourceSamplesAt16k':len(a),'decodedDeliverySamplesAt16k':len(b)})
    return report


def project_audio_comparison(p,delivered,start=0,frames=None):
    """Verify the edit's source-zero audio window, or a bounded proof interval."""
    if frames is None:frames=p.frames-start
    if type(start) is not int or type(frames) is not int or start<0 or frames<1 or start+frames>p.frames:
        raise ValueError('Audio interval must be inside the editorial timeline')
    report=audio_comparison(p.audio,delivered,
        source_window=(Fraction(start,p.fps),Fraction(frames,p.fps)))
    report['sourceWindow'].update({'startFrame':start,'frames':frames,'fps':p.fps})
    return report

def verify(p, delivery=None, profile=None):
    """Verify a configured delivery; creative checks are explicitly opt-in."""
    from .validation import validate_shot_set
    from .delivery import delivery_path
    from .review import decode_frames,validate_references,compare_reference,contact_sheets
    records=validate_shot_set(p)
    settings=p.data.get('verification',{})
    if not isinstance(settings,dict):raise ValueError('verification must be an object')
    selected_profile=profile or settings.get('profile','generic')
    if selected_profile not in {'generic','unit9'}:raise ValueError('Unknown verification profile: '+str(selected_profile))
    references=settings.get('reference_frames',[])
    if not isinstance(references,list):raise ValueError('reference_frames must be a list')
    references=list(references);profile_checks=None
    if selected_profile=='unit9':
        from . import unit9_checks
        references+=unit9_checks.reference_frames(p)
        profile_checks=unit9_checks.inspect(p)
    validate_references(p,references)
    reference_hashes={row['file']:sha(p.root/row['file']) for row in references}
    movie=delivery_path(p,delivery)
    if not movie.is_file():raise ValueError('Delivery movie is missing: '+str(movie))
    movie_sha=sha(movie);info=probe(movie)
    videos=[s for s in info['streams'] if s['codec_type']=='video']
    audios=[s for s in info['streams'] if s['codec_type']=='audio']
    if len(videos)!=1 or len(audios)!=1:raise ValueError('Delivery requires one video and one audio stream')
    video=videos[0];sound=audios[0]
    if (video['width'],video['height'])!=(p.width,p.height):raise ValueError('Delivery dimensions differ from edit')
    if int(video.get('nb_frames',-1))!=p.frames or Fraction(video['avg_frame_rate'])!=p.fps:
        raise ValueError('Delivery frame count or rate differs from edit')
    if abs(float(info['format']['duration'])-p.frames/p.fps)>1/p.fps:
        raise ValueError('Delivery container duration differs from edit')
    if [video.get(k) for k in ['color_primaries','color_transfer','color_space','color_range']]!=['bt709','iec61966-2-1','bt709','tv']:
        raise ValueError('Delivery color tags differ from encoder contract')
    if int(sound['sample_rate'])!=48000 or sound['channels']!=2:
        raise ValueError('Delivery audio must be 48 kHz stereo')
    if abs(float(sound.get('duration',-1))-p.frames/p.fps)>.022:
        raise ValueError('Delivery audio duration differs from edit')
    audio=project_audio_comparison(p,movie)
    shot_frames=[{'id':s['id'],'name':s['name'],'frame':(s['start']+s['end']-1)//2} for s in p.edit['scenes']]
    selected=sorted({s['frame'] for s in shot_frames}|{r['frame'] for r in references})
    review_folder=p.output/'review'
    with tempfile.TemporaryDirectory(prefix='delivery-check-',dir=p.output) as folder:
        folder=Path(folder)
        decoded=decode_frames(movie,selected,folder)
        comparisons=[compare_reference(p.root/r['file'],decoded[r['frame']],r['frame']) for r in references]
        sheets=contact_sheets(p,shot_frames,decoded,folder)
        if sha(movie)!=movie_sha or p.source_inventory()[0]!=records['sourceFingerprint']:
            raise RuntimeError('Delivery or build sources changed during verification')
        if any(sha(p.root/file)!=digest for file,digest in reference_hashes.items()):
            raise RuntimeError('Reference pictures changed during verification')
        review_folder.mkdir(parents=True,exist_ok=True)
        contacts=[]
        for sheet in sheets:
            output=review_folder/sheet.name;shutil.copy2(sheet,output);contacts.append(str(p.public_path(output)))
        for frame in {r['frame'] for r in references}:
            shutil.copy2(decoded[frame],review_folder/f'frame-{frame:06d}.png')
    shot_checks=[{'id':s['id'],'frames':records['shots'][s['id']]['frames'],'handleIn':p.handles,'handleOut':p.handles,'hash':'passed'} for s in p.edit['scenes']]
    report={
        'schemaVersion':2,'status':'passed','scope':'Current shot set, delivery metadata, full video decode, audio comparison, all-shot contact sheets, and explicitly configured reference/profile checks.',
        'delivery':str(p.public_path(movie)),'deliverySha256':movie_sha,'sourceFingerprint':records['sourceFingerprint'],
        'video':{k:video.get(k) for k in ['codec_name','width','height','nb_frames','avg_frame_rate','duration','pix_fmt','color_primaries','color_transfer','color_space','color_range']},
        'audio':audio,'shotChecks':shot_checks,'decodedShotFrames':shot_frames,'contactSheets':contacts,
        'pixelComparisons':comparisons,'referenceHashes':reference_hashes,'profile':selected_profile,'profileChecks':profile_checks,
        'limits':['No native editor import or device playback acceptance is established.','Decoded contact sheets and optional reference checks do not replace a full human screening.','Animation is baked within shot media; editorial interchange does not preserve source rigs.'],
    }
    dump(p.output/'media-verification.json',report)
    print(f"Media checks passed: {p.frames} frames; {len(shot_checks)} shots; {len(contacts)} contact sheets; profile {selected_profile}.",flush=True)
    return report
