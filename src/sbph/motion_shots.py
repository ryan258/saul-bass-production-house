"""Bake isolated Motion Canvas bodies, then add same-shot edge holds as handles."""
from pathlib import Path
import json, shutil, subprocess, tempfile
import ffmpeg
from .project import FRAMEWORK, binary, sha
from .shot_backend import motion_projects,motion_start
from .media import COLOR, BSF, probe


def export_body(p,project,work,count,start=0):
    # Work on a source copy: Motion Canvas may save .meta caches while rendering.
    copied=work/'source'
    shutil.copytree(project.parent,copied,ignore=shutil.ignore_patterns('node_modules','.git','.vite','__pycache__'))
    project=copied/project.name
    subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/typecheck.mjs'),str(project)],check=True)
    options={'width':p.width,'height':p.height,'fps':p.fps,'frames':count,'startFrame':start}
    result=subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/render.mjs'),'render',str(project),str(work),json.dumps(options)],capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Motion shot render failed:\n'+result.stderr[-3000:]+'\n'+result.stdout[-3000:])
    records=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    if not records or records[-1].get('result')!=0 or records[-1].get('errors'):
        raise RuntimeError('Motion shot renderer did not report successful completion')


def render_shot(p,scene,destination):
    project=motion_projects(p)[scene['id']];body=scene['end']-scene['start'];count=body+2*p.handles
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.motion-shot-',dir=p.output) as folder:
        work=Path(folder);start=motion_start(p,scene['id']);export_body(p,project,work,body,start)
        frames=sorted((work/'frames').glob('*.png'))
        if [f.name for f in frames]!=[f'{i:06}.png' for i in range(start,start+body)]:
            raise RuntimeError('Incomplete or incorrectly numbered Motion shot body')
        from PIL import Image
        for file in frames:
            with Image.open(file) as picture:
                if picture.size!=(p.width,p.height):raise RuntimeError('Motion shot frame dimensions differ from the edit')
        sequence=work/'handled';sequence.mkdir()
        for i in range(count):
            source=frames[min(body-1,max(0,i-p.handles))]
            # Hard links avoid duplicating large edge PNGs; all paths are temporary.
            (sequence/f'{i:06}.png').hardlink_to(source)
        output=work/'shot.mp4'
        video=ffmpeg.input(str(sequence/'%06d.png'),framerate=p.fps).video.filter('scale',out_color_matrix='bt709',out_range='tv')
        graph=ffmpeg.output(video,str(output),vcodec='libx264',crf=17,preset='medium',pix_fmt='yuv420p',r=p.fps,vframes=count,threads=2,**{'bsf:v':BSF},movflags='+faststart',**COLOR)
        ffmpeg.run(graph,cmd=binary('ffmpeg'),overwrite_output=True,quiet=True)
        v=next(s for s in probe(output)['streams'] if s['codec_type']=='video')
        if int(v.get('nb_frames',-1))!=count:raise RuntimeError('Motion shot encoder frame count mismatch')
        output.replace(destination)
    return {'file':str(p.public_path(destination)),'frames':count,'sha256':sha(destination),'fps':p.fps,'color':COLOR}
