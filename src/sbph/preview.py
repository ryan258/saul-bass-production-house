from pathlib import Path
import ffmpeg
from .media import render_picture,COLOR,BSF,probe
from .project import binary,dump,sha

def preview(p,start_seconds=None,duration_seconds=None):
    from .validation import validate_edit,validate_source_audio
    from .fingerprint import BUILD_SCHEMA
    validate_edit(p);validate_source_audio(p)
    if start_seconds is None:start_seconds=p.data.get('proof_start',0)
    if duration_seconds is None:duration_seconds=p.data.get('proof_duration',15)
    fingerprint,inventory=p.source_inventory();audio_sha=sha(p.audio)
    start=round(start_seconds*p.fps);count=min(p.frames-start,round(duration_seconds*p.fps))
    if start<0 or count<1:raise ValueError('Proof interval is outside the edit')
    picture=p.output/'proof.picture.mp4';output=p.output/'proof.mp4'
    render_picture(p,picture,start,count)
    video=ffmpeg.input(str(picture)).video;audio=ffmpeg.input(str(p.audio),ss=start/p.fps).audio
    graph=ffmpeg.output(video,audio,str(output),vcodec='copy',acodec='aac',audio_bitrate='320k',ar=48000,ac=2,t=count/p.fps,movflags='+faststart',**{'bsf:v':BSF},**COLOR)
    ffmpeg.run(graph,cmd=binary('ffmpeg'),overwrite_output=True,quiet=True);picture.unlink()
    v=next(s for s in probe(output)['streams'] if s['codec_type']=='video')
    if int(v['nb_frames'])!=count:raise RuntimeError('Proof frame count mismatch')
    if p.source_inventory()[0]!=fingerprint:raise RuntimeError('Sources changed during proof rendering')
    dump(p.output/'proof.json',{'schemaVersion':BUILD_SCHEMA,'sourceFingerprint':fingerprint,'sourceInventory':inventory,'sourceAudioSha256':audio_sha,'width':p.width,'height':p.height,'file':str(p.public_path(output)),'sha256':sha(output),'sourceStartFrame':start,'frames':count,'fps':p.fps,'duration':count/p.fps,'audio':'Matching source interval; AAC delivery encode, original WAV unchanged.','backend':'ffmpeg-python + shared SVG frame producer'})
    print(f'Proof: {count} frames from source frame {start}, with matching audio.')
    return output
