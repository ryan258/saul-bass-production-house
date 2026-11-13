"""Clearly marked, unique draft outputs. Never overwrite production artifacts."""
from fractions import Fraction
from pathlib import Path
import json
import math
import subprocess
import tempfile
import uuid

import ffmpeg
from PIL import Image,ImageDraw,ImageFont,__version__ as pillow_version

from .project import FRAMEWORK,Project,binary,dump,sha
from .fingerprint import digest,tool_identity
from .media import COLOR,BSF,probe,locked_output,_candidate_directory,_promote_files,_run_ffmpeg
from .validation import validate_edit,validate_source_audio
from . import workflow as flow

MAX_REVISION_SECONDS=30
BANNER_HEIGHT=52


def size(p,width):
    if type(width) is not int or not 160<=width<=1280:raise ValueError('Draft width must be 160–1280 pixels')
    width=min(width,max(160,p.width));width-=width%2
    height=round(width*p.height/p.width);height-=height%2
    if height<80:raise ValueError('Draft aspect ratio is too wide for readable labels')
    return width,height


def revision_parameters(p,identifier=None,note_id=None,before=.5,after=.5,start=None,duration=None,width=640):
    if identifier and note_id:raise ValueError('Select a shot or a note, not both')
    if note_id:
        note=flow.find_note(p,note_id)
        if note['location']['frame'] is None:raise ValueError('Note anchor needs review: '+note['location']['status'])
        identifier=note['anchor']['shotId']
    if not identifier:
        saved=flow.checkpoint(p)
        if saved and saved.get('anchor') and saved['location']['frame'] is not None:identifier=saved['anchor']['shotId']
    if not identifier:raise ValueError('Choose --shot or --note, or save a shot checkpoint with resume')
    scene=flow.shot(p,identifier)
    if any(type(n) not in (int,float) or not math.isfinite(n) or n<0 for n in [before,after]):
        raise ValueError('Revision context must be nonnegative finite seconds')
    if (start is None)!=(duration is None):raise ValueError('An explicit revision window needs both --start and --duration')
    if start is None:
        first=max(0,scene['start']-round(before*p.fps));last=min(p.frames,scene['end']+round(after*p.fps))
    else:
        if any(type(n) not in (int,float) or not math.isfinite(n) for n in [start,duration]) or start<0 or duration<=0:
            raise ValueError('Revision start/duration must be finite and positive (start may be zero)')
        first=round(start*p.fps);last=min(p.frames,first+round(duration*p.fps))
        if first>=scene['end'] or last<=scene['start']:raise ValueError('Revision window must overlap the selected shot')
    if last<=first or last-first>MAX_REVISION_SECONDS*p.fps:
        raise ValueError('Revision previews are limited to 30 seconds; choose --start and --duration for a smaller window')
    w,h=size(p,width)
    return {'kind':'revision','shotId':identifier,'noteId':note_id.upper() if note_id else None,'noteAnchor':note['anchor'] if note_id else None,'start':first,'frames':last-first,'width':w,'pictureHeight':h,'height':h+BANNER_HEIGHT,'renderStills':False}


def animatic_parameters(p,width=640,render_stills=False):
    w,h=size(p,width)
    return {'kind':'animatic','start':0,'frames':p.frames,'width':w,'pictureHeight':h,'height':h+BANNER_HEIGHT,'renderStills':render_stills}


def basis(p,params):
    """Draft identity includes planning text; production identity does not."""
    current=Project.load(p.config)
    if current.data!=p.data or current.edit!=p.edit:raise ValueError('Project configuration or edit changed; reload before drafting')
    references={}
    if params['kind']=='animatic':
        for scene in p.edit['scenes']:
            image=scene.get('storyboard')
            if image is not None:
                if not isinstance(image,str) or not (p.root/image).is_file():raise ValueError('Missing storyboard image for '+scene['id'])
                references[scene['id']]={'file':image,'sha256':sha(p.root/image)}
    production=None
    if params['kind']=='revision' or params['renderStills']:production=p.source_inventory()[0]
    current_edit=json.loads((p.root/p.data.get('edit','data/edit.json')).read_text())
    if current_edit!=p.edit:raise ValueError('Edit changed; reload the project before drafting')
    selected_note=flow.find_note(p,params['noteId']) if params.get('noteId') else None
    return {
        'parameters':params,'editSha256':sha(p.root/p.data.get('edit','data/edit.json')),
        'sourceAudioSha256':sha(p.audio),'intent':{s['id']:flow.shot_intent(p,s['id']) for s in p.edit['scenes']},
        'storyboards':references,'productionFingerprint':production,'ffmpeg':tool_identity('ffmpeg'),
        'noteAnchor':selected_note['anchor'] if selected_note else None,
        'pillow':pillow_version,'framework':{name:sha(FRAMEWORK/name) for name in ['src/sbph/drafts.py','src/sbph/workflow.py','render/draft.cjs','src/sbph/media.py','src/sbph/verify.py']},
    }


def wrap(draw,text,font,width):
    words=str(text).split();lines=[];line=''
    for word in words:
        candidate=(line+' '+word).strip()
        if line and draw.textlength(candidate,font=font)>width:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    return lines


def label(image,title,subtitle):
    draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=max(11,min(18,image.width//25)))
    height=BANNER_HEIGHT
    draw.rectangle((0,0,image.width,height),fill='#15283F')
    draw.text((8,3),title,fill='#F3AE35',font=font)
    draw.text((8,height//2),subtitle,fill='white',font=font)
    return image


def make_cards(p,params,work):
    w,h=params['width'],params['pictureHeight'];sampled={}
    if params['renderStills']:
        frames=[{'frame':(s['start']+s['end']-1)//2,'file':str(work/f"sample-{s['id']}.png")} for s in p.edit['scenes'] if not s.get('storyboard')]
        if frames:
            options={'mode':'stills','driver':str(p.driver),'width':w,'height':h,'frames':frames}
            subprocess.run([binary('node'),str(FRAMEWORK/'render/draft.cjs'),json.dumps(options)],check=True)
        sampled={s['id']:work/f"sample-{s['id']}.png" for s in p.edit['scenes'] if not s.get('storyboard')}
    cards=[];sections=[]
    for scene in p.edit['scenes']:
        mode='placeholder';source=None
        if scene.get('storyboard'):source=p.root/scene['storyboard'];mode='storyboard'
        elif scene['id'] in sampled:source=sampled[scene['id']];mode='renderer-still'
        if source:
            with Image.open(source) as im:image=im.convert('RGB').resize((w,h),Image.Resampling.LANCZOS)
        else:
            image=Image.new('RGB',(w,h),'#F5E9CA');draw=ImageDraw.Draw(image)
            font=ImageFont.load_default(size=max(11,min(22,w//22)))
            intent=flow.shot_intent(p,scene['id'])
            body=scene['name']+'\n'+scene['action']
            for field in ['goal','change']:
                if intent['fields'].get(field):body+='\n'+field.title()+': '+intent['fields'][field]
            y=min(h//3,60)
            for paragraph in body.splitlines():
                for line in wrap(draw,paragraph,font,w-20):
                    if y+font.size+4>h-8:break
                    draw.text((10,y),line,fill='#15283F',font=font);y+=font.size+4
        interval=f"{scene['id']}  {flow.timecode(scene['start'],p.fps)}–{flow.timecode(scene['end'],p.fps)}"
        framed=Image.new('RGB',(w,h+BANNER_HEIGHT),'#15283F');framed.paste(image,(0,BANNER_HEIGHT))
        image=label(framed,'DRAFT ANIMATIC',interval)
        file=work/f"card-{scene['id']}.png";image.save(file)
        cards.append((image.tobytes(),scene['end']-scene['start']))
        sections.append({'shotId':scene['id'],'start':scene['start'],'end':scene['end'],'mode':mode})
    return cards,sections


def encode(p,params,candidate,work,cards):
    w,h=params['width'],params['height'];count=params['frames'];start=params['start']
    source=ffmpeg.input('pipe:0',format='rawvideo',pix_fmt='rgb24',s=f'{w}x{h}',framerate=p.fps).video
    source=source.filter('scale',out_color_matrix='bt709',out_range='tv')
    audio=ffmpeg.input(str(p.audio),ss=start/p.fps).audio
    graph=ffmpeg.output(source,audio,str(candidate),vcodec='libx264',crf=23,preset='veryfast',pix_fmt='yuv420p',r=p.fps,
        acodec='aac',audio_bitrate='192k',ar=48000,ac=2,t=count/p.fps,vframes=count,threads=2,movflags='+faststart',**{'bsf:v':BSF},**COLOR).global_args('-hide_banner','-loglevel','error')
    producer=None;consumer=None
    with tempfile.TemporaryFile() as log:
        try:
            if cards is None:
                banner=label(Image.new('RGB',(w,BANNER_HEIGHT),'#15283F'),'DRAFT REVISION',f"{params['shotId']}  {flow.timecode(start,p.fps)}–{flow.timecode(start+count,p.fps)}")
                banner_path=work/'banner.png';banner.save(banner_path)
                options={'mode':'motion','driver':str(p.driver),'width':w,'height':h,'pictureHeight':params['pictureHeight'],'bannerHeight':BANNER_HEIGHT,'start':start,'count':count,'banner':str(banner_path)}
                producer=subprocess.Popen([binary('node'),str(FRAMEWORK/'render/draft.cjs'),json.dumps(options)],stdout=subprocess.PIPE,stderr=log)
            consumer=subprocess.Popen(ffmpeg.compile(graph,cmd=binary('ffmpeg'),overwrite_output=True),stdin=producer.stdout if producer else subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
            if producer:producer.stdout.close()
            else:
                try:
                    for raw,frames in cards:
                        for _ in range(frames):consumer.stdin.write(raw)
                except BrokenPipeError:pass
                finally:consumer.stdin.close()
            code=consumer.wait();producer_code=producer.wait() if producer else 0
            if code or producer_code:
                log.seek(0);raise RuntimeError('Draft producer/encoder failed: '+log.read().decode(errors='replace')[-4000:])
        finally:
            for process in [consumer,producer]:
                if process and process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()


@locked_output
def render(p,params):
    validate_edit(p);validate_source_audio(p)
    if params.get('noteId') and flow.find_note(p,params['noteId'])['anchor']!=params.get('noteAnchor'):
        raise ValueError('Note anchor changed; select the note again before previewing')
    inputs=basis(p,params);fingerprint=digest(inputs)
    folder=p.output/'drafts';folder.mkdir(parents=True,exist_ok=True)
    identifier=('A' if params['kind']=='animatic' else 'R')+uuid.uuid4().hex[:12]
    final=folder/(identifier+'.mp4');sidecar=final.with_suffix('.json')
    if final.exists() or sidecar.exists():raise ValueError('Draft filename collision; retry')
    with _candidate_directory(prefix='.draft-work-',dir=folder) as temporary:
        work=Path(temporary);candidate=work/'candidate.mp4';cards=None;sections=[]
        if params['kind']=='animatic':cards,sections=make_cards(p,params,work)
        encode(p,params,candidate,work,cards)
        video=next(s for s in probe(candidate)['streams'] if s['codec_type']=='video')
        if int(video.get('nb_frames',-1))!=params['frames'] or Fraction(video['avg_frame_rate'])!=p.fps or (video['width'],video['height'])!=(params['width'],params['height']):
            raise RuntimeError('Draft frame count, rate, or size mismatch')
        from .verify import audio_comparison
        expected=work/'audio-window.wav'
        stream=ffmpeg.input(str(p.audio)).audio.filter('atrim',start=params['start']/p.fps,end=(params['start']+params['frames'])/p.fps).filter('asetpts','PTS-STARTPTS')
        _run_ffmpeg(ffmpeg.output(stream,str(expected),acodec='pcm_s16le').global_args('-hide_banner','-loglevel','error'))
        audio=audio_comparison(expected,candidate)
        if digest(basis(p,params))!=fingerprint:raise RuntimeError('Draft inputs changed during rendering; output was not promoted')
        record={'schemaVersion':1,'id':identifier,'kind':params['kind'],'draft':True,'createdAt':flow.now(),
            'backend':'svg-driver' if params['kind']=='revision' or params['renderStills'] else 'storyboard-cards',
            'file':flow.relative_path(p,final),'sha256':sha(candidate),'parameters':params,'sourceFingerprint':fingerprint,
            'inputs':inputs,'fps':p.fps,'frames':params['frames'],'duration':params['frames']/p.fps,'sections':sections,'audio':audio,
            'limit':'Draft review material, not a production delivery, approved baseline, or editorial acceptance.'}
        staged=work/'draft.json';dump(staged,record)
        if digest(basis(p,params))!=fingerprint:raise RuntimeError('Draft inputs changed before promotion')
        _promote_files([(candidate,final),(staged,sidecar)],work)
    flow.register_artifact(p,{key:record[key] for key in ['id','kind','createdAt','file','sha256','parameters','sourceFingerprint']})
    return record


def artifact_status(p,row):
    if not isinstance(row,dict) or any(key not in row for key in ['file','sha256','parameters','sourceFingerprint']):raise ValueError('Malformed saved draft record')
    if not isinstance(row['file'],str) or not isinstance(row['parameters'],dict):raise ValueError('Malformed saved draft file or parameters')
    file=p.root/row['file']
    if not file.is_file():return {**row,'status':'missing'}
    if sha(file)!=row['sha256']:return {**row,'status':'changed'}
    try:current=digest(basis(p,row['parameters']))==row['sourceFingerprint']
    except (ValueError,OSError,subprocess.SubprocessError) as error:return {**row,'status':'unverified','reason':str(error)}
    return {**row,'status':'current' if current else 'stale'}
