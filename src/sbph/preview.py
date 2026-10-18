from pathlib import Path
import ffmpeg
from .media import render_picture,COLOR,BSF,_run_ffmpeg,_validate_video,_promote_files,_candidate_directory,_protect_output_inputs
from .project import binary,dump,sha

def preview(p,start_seconds=None,duration_seconds=None):
    from .validation import validate_edit,validate_source_audio
    from .fingerprint import BUILD_SCHEMA
    from .verify import project_audio_comparison
    output=p.output/'proof.mp4'
    _protect_output_inputs(p,[output,p.output/'proof.json'])
    validate_edit(p);validate_source_audio(p)
    if start_seconds is None:start_seconds=p.data.get('proof_start',0)
    if duration_seconds is None:duration_seconds=p.data.get('proof_duration',15)
    fingerprint,inventory=p.source_inventory();audio_sha=sha(p.audio)
    start=round(start_seconds*p.fps);count=min(p.frames-start,round(duration_seconds*p.fps))
    if start<0 or count<1:raise ValueError('Proof interval is outside the edit')
    output.parent.mkdir(parents=True,exist_ok=True)
    with _candidate_directory(prefix='.proof-',dir=output.parent) as folder:
        work=Path(folder);picture=work/'picture.mp4';candidate=work/'proof.mp4';receipt=work/'proof.json'
        render_picture(p,picture,start,count)
        video=ffmpeg.input(str(picture)).video;audio=ffmpeg.input(str(p.audio),ss=start/p.fps).audio
        graph=ffmpeg.output(video,audio,str(candidate),vcodec='copy',acodec='aac',audio_bitrate='320k',ar=48000,ac=2,t=count/p.fps,movflags='+faststart',**{'bsf:v':BSF},**COLOR)
        _run_ffmpeg(graph);_validate_video(candidate,p,count,with_audio=True)
        audio_check=project_audio_comparison(p,candidate,start=start,frames=count)
        dump(receipt,{'schemaVersion':BUILD_SCHEMA,'sourceFingerprint':fingerprint,'sourceInventory':inventory,'sourceAudioSha256':audio_sha,'width':p.width,'height':p.height,'file':str(p.public_path(output)),'sha256':sha(candidate),'sourceStartFrame':start,'frames':count,'fps':p.fps,'duration':count/p.fps,'audio':'Matching source interval; AAC delivery encode, original WAV unchanged.','audioComparison':audio_check,'backend':'ffmpeg-python + shared SVG frame producer'})
        if p.source_inventory()[0]!=fingerprint:raise RuntimeError('Sources changed during proof rendering')
        _promote_files([(candidate,output),(receipt,p.output/'proof.json')],work)
    print(f'Proof: {count} frames from source frame {start}, with matching audio.')
    return output
