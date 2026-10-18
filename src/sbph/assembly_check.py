"""Conform a library-built assembly against the original full-frame viewing reference."""
import subprocess,json
from fractions import Fraction
import numpy as np
from .media import probe
from .verify import project_audio_comparison
from .project import binary,dump,sha

def sample(path,frames,size=(512,288)):
    def expression(values):
        if len(values)==1:return f'eq(n,{values[0]})'
        mid=len(values)//2
        return '('+expression(values[:mid])+'+'+expression(values[mid:])+')'
    select=expression(frames)
    vf=f"select='{select}',scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int,scale={size[0]}:{size[1]}"
    raw=subprocess.check_output([binary('ffmpeg'),'-v','error','-xerror','-i',str(path),'-vf',vf,'-fps_mode','vfr','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    result=np.frombuffer(raw,np.uint8).reshape(-1,size[1],size[0],3)
    if len(result)!=len(frames):raise ValueError('Movie did not decode every requested conform frame')
    return result

def conform_frames(scenes,offset=0):
    """First (optionally lagged), middle, and last frame of every shot.

    A reference cut from one continuous timeline may still show the previous
    shot on a shot's first frame. verification.conform_first_frame_offset names
    that lag explicitly; it never skips the other two samples.
    """
    if type(offset) is not int or offset<0:raise ValueError('conform_first_frame_offset must be a nonnegative integer')
    return sorted(set(n for s in scenes for n in [min(s['start']+offset,s['end']-1),(s['start']+s['end'])//2,s['end']-1]))


def check(p,reference_override=None):
    from .validation import validate_shot_set
    from .delivery import reference_path
    records=validate_shot_set(p)
    assembled=p.output/'assembly.mp4';reference=reference_path(p,reference_override)
    assembly_hash=sha(assembled);reference_hash=sha(reference)
    for file in [assembled,reference]:
        v=next(s for s in probe(file)['streams'] if s['codec_type']=='video')
        if int(v.get('nb_frames',-1))!=p.frames or Fraction(v['avg_frame_rate'])!=p.fps or (v['width'],v['height'])!=(p.width,p.height):
            raise ValueError('Conform movie metadata differs from edit: '+str(file))
    offset=(p.data.get('verification') or {}).get('conform_first_frame_offset',0);frames=conform_frames(p.edit['scenes'],offset)
    size=(512,max(1,round(512*p.height/p.width)))
    a=sample(reference,frames,size);b=sample(assembled,frames,size)
    errors=[float(np.abs(a[i].astype(np.int16)-b[i].astype(np.int16)).mean()) for i in range(len(frames))]
    if max(errors)>=2:raise ValueError(f'Assembly picture differs from reference at frame {frames[errors.index(max(errors))]}: {max(errors)}')
    audio=project_audio_comparison(p,assembled)
    if sha(assembled)!=assembly_hash or sha(reference)!=reference_hash:raise RuntimeError('Conform movies changed during verification')
    report={'status':'passed','assembly':str(p.public_path(assembled)),'sha256':assembly_hash,'sourceFingerprint':records['sourceFingerprint'],'frames':p.frames,'reference':str(p.public_path(reference)),'referenceSha256':reference_hash,'comparedFrames':frames,'firstFrameOffset':offset,'sampleSize':list(size),'method':'First, middle, and final editorial frame of every shot, decoded at an aspect-preserving 512-pixel width using explicit color matrix/range.','maximumRgbMae':max(errors),'meanRgbMae':float(np.mean(errors)),'audio':audio,'limit':'This confirms the generated assembly conforms to the explicitly selected viewing reference at sampled editorial boundaries. It does not replace native editor import or a full human screening.'}
    if p.source_inventory()[0]!=records['sourceFingerprint'] or sha(p.audio)!=audio['sourceSha256']:
        raise RuntimeError('Build sources changed during conform verification')
    dump(p.output/'assembly-verification.json',report);print(f"Assembly conforms: {len(frames)} boundary/midpoint samples; maximum RGB error {max(errors):.3f}; audio checks complete.")
    return report
