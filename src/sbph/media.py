from pathlib import Path
import json, subprocess, time
import ffmpeg
from .project import binary, dump, sha, FRAMEWORK

COLOR=dict(color_primaries='bt709',color_trc='iec61966-2-1',colorspace='bt709',color_range='tv')
BSF='h264_metadata=colour_primaries=1:transfer_characteristics=13:matrix_coefficients=1'

def probe(path):return ffmpeg.probe(str(path),cmd=binary('ffprobe'))

def render_picture(p,destination,start,count,shot=None):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    options=dict(driver=str(p.driver),start=start,count=count,shot=shot,width=p.width,height=p.height)
    producer=subprocess.Popen([binary('node'),str(FRAMEWORK/'render/emit.cjs'),json.dumps(options)],stdout=subprocess.PIPE)
    picture=ffmpeg.input('pipe:0',format='rawvideo',pix_fmt='rgba',s=f'{p.width}x{p.height}',framerate=p.fps).video
    picture=picture.filter('scale',out_color_matrix='bt709',out_range='tv')
    graph=ffmpeg.output(picture,str(destination),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=p.fps,threads=6,g=p.fps,movflags='+faststart',**COLOR).global_args('-hide_banner','-loglevel','error')
    command=ffmpeg.compile(graph,cmd=binary('ffmpeg'),overwrite_output=True)
    consumer=subprocess.Popen(command,stdin=producer.stdout)
    producer.stdout.close()
    code=consumer.wait();producer_code=producer.wait()
    if code or producer_code:raise RuntimeError(f'Frame producer/encoder failed: {producer_code}/{code}')
    tagged=destination.with_name(destination.stem+'.tagged.mp4')
    graph=ffmpeg.output(ffmpeg.input(str(destination)).video,str(tagged),vcodec='copy',**{'bsf:v':BSF},movflags='+faststart',**COLOR)
    ffmpeg.run(graph,cmd=binary('ffmpeg'),overwrite_output=True,quiet=True);tagged.replace(destination)
    actual=probe(destination)['streams'][0]
    if int(actual.get('nb_frames',-1))!=count:raise RuntimeError('Encoder did not deliver the requested frame count')
    return {'file':str(p.public_path(destination)),'frames':count,'sha256':sha(destination),'fps':p.fps,'color':COLOR}

def render_shots(p,selected=None):
    from .fingerprint import BUILD_SCHEMA
    from .shot_backend import backend, renderer_record
    from .validation import validate_edit,validate_source_audio
    validate_edit(p);validate_source_audio(p)
    if selected is not None:
        unknown=selected-{s['id'] for s in p.edit['scenes']}
        if unknown:raise ValueError('Unknown shot IDs: '+', '.join(sorted(unknown)))
    manifest_path=p.output/'shots.json'
    prior=json.loads(manifest_path.read_text()) if manifest_path.exists() else {'shots':{}}
    fingerprint,inventory=p.source_inventory()
    records=prior['shots'] if prior.get('schemaVersion')==BUILD_SCHEMA and prior.get('sourceFingerprint')==fingerprint else {}
    scenes=[s for s in p.edit['scenes'] if selected is None or s['id'] in selected]
    for i,s in enumerate(scenes):
        body=s['end']-s['start'];count=body+2*p.handles
        file=p.output/'shots'/f"{s['id']}-{s['kind']}.mp4"
        if backend(p)=='motion-canvas':
            from .motion_shots import render_shot
            record=render_shot(p,s,file)
        else:record=render_picture(p,file,-p.handles,count,s['id'])
        if p.source_inventory()[0]!=fingerprint:raise RuntimeError('Sources changed during render; rebuild before export')
        record.update(sourceFingerprint=fingerprint,id=s['id'],bodyFrames=body,handleIn=p.handles,handleOut=p.handles,sourceStart=p.handles,timelineStart=s['start'],handlePolicy='Same-shot renderer extension. Normalized progress clamps at the shot boundary; time-based details may continue. Some handles are holds. SVG rig/effects are baked in this clip.')
        if backend(p)=='motion-canvas':record['handlePolicy']='Explicit Motion Canvas body window; first/last body frames held for handles. Motion and effects are baked.'
        records[s['id']]=record
        dump(manifest_path,{'schemaVersion':BUILD_SCHEMA,'project':p.edit['title'],'fps':p.fps,'sourceFingerprint':fingerprint,'sourceInventory':inventory,'sourceEditSha256':sha(p.root/p.data.get('edit','data/edit.json')),**renderer_record(p),'shots':records})
        print(f"Shot {s['id']} / {i+1} of {len(scenes)}: {count} frames including handles.",flush=True)
    return manifest_path

def mux_master(p,picture,output):
    video=ffmpeg.input(str(picture)).video;audio=ffmpeg.input(str(p.audio)).audio
    graph=ffmpeg.output(video,audio,str(output),vcodec='copy',acodec='aac',audio_bitrate='320k',ar=48000,ac=2,t=p.frames/p.fps,movflags='+faststart',**{'bsf:v':BSF},**COLOR)
    ffmpeg.run(graph,cmd=binary('ffmpeg'),overwrite_output=True,quiet=True)


def assemble(p):
    """Assemble the editorial bodies with FFmpeg, leaving shot handles out of the master."""
    from .validation import validate_shot_set
    manifest=validate_shot_set(p);streams=[]
    for s in p.edit['scenes']:
        rec=manifest['shots'][s['id']];file=p.output/'shots'/Path(rec['file']).name
        # Trimming uses integer frame boundaries; timestamps restart before concat.
        stream=ffmpeg.input(str(file),threads=1).video.filter('trim',start_frame=rec['sourceStart'],end_frame=rec['sourceStart']+rec['bodyFrames']).filter('setpts','PTS-STARTPTS')
        streams.append(stream)
    picture=p.output/'assembly.picture.mp4';picture.parent.mkdir(parents=True,exist_ok=True)
    graph=ffmpeg.output(ffmpeg.concat(*streams,v=1,a=0),str(picture),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=p.fps,threads=6,movflags='+faststart',**COLOR).global_args('-filter_complex_threads','2','-hide_banner','-loglevel','error')
    ffmpeg.run(graph,cmd=binary('ffmpeg'),overwrite_output=True,quiet=True)
    output=p.output/'assembly.mp4';mux_master(p,picture,output);picture.unlink();return output
