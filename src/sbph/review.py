"""Generic decoded-picture evidence and contact sheets for any shot count."""
from pathlib import Path
import math
import subprocess

import numpy as np
from PIL import Image,ImageDraw,ImageFont
from .project import binary


def decode_frames(movie, frames, folder):
    def expression(values):
        if len(values)==1:return f'eq(n,{values[0]})'
        mid=len(values)//2
        return '('+expression(values[:mid])+'+'+expression(values[mid:])+')'
    selector=expression(frames)
    filt=f"select='{selector}',scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int"
    subprocess.run([binary('ffmpeg'),'-v','error','-xerror','-err_detect','explode','-i',str(movie),'-map','0:v:0','-vf',filt,'-fps_mode','vfr','-y',str(folder/'%06d.png')],check=True)
    files=sorted(folder.glob('*.png'))
    if len(files)!=len(frames):raise ValueError('Delivery did not decode all requested review frames')
    return dict(zip(frames,files))


def validate_references(p,references):
    for row in references:
        if not isinstance(row,dict) or type(row.get('frame')) is not int or not 0<=row['frame']<p.frames:
            raise ValueError('Reference picture frame must be inside the edit')
        if not isinstance(row.get('file'),str) or not (p.root/row['file']).is_file():
            raise ValueError('Reference picture file is missing')


def compare_reference(reference,decoded,frame):
    with Image.open(reference) as im:ref=np.asarray(im.convert('RGB')).astype(np.float32)
    with Image.open(decoded) as im:got=np.asarray(im.convert('RGB')).astype(np.float32)
    if ref.shape!=got.shape:raise ValueError(f'Reference picture dimensions differ at frame {frame}')
    delta=np.abs(ref-got);luma=((ref-got)*np.array([.2126,.7152,.0722])).sum(axis=2)
    psnr=10*math.log10(255**2/max(float(np.mean(luma*luma)),1e-12))
    flat=np.ones(ref.shape[:2],bool)
    for axis in [0,1]:
        for step in [-1,1]:flat&=np.max(np.abs(ref-np.roll(ref,step,axis)),axis=2)<4
    flat[:2]=False;flat[-2:]=False;flat[:,:2]=False;flat[:,-2:]=False
    flat_mae=float(delta[flat].mean()) if flat.any() else None
    if psnr<=38 or (flat_mae is not None and flat_mae>=3):
        raise ValueError(f'Reference picture comparison failed at frame {frame}: PSNR={psnr}, flat RGB error={flat_mae}')
    return {'frame':frame,'lumaPsnrDb':psnr,'flatInteriorRgbMae':flat_mae,'allPixelRgbMae':float(delta.mean())}


def contact_sheets(p,shot_frames,decoded,folder):
    """Paginate the actual shot list; no external font or 60-shot ceiling."""
    width=480;height=max(1,round(width*p.height/p.width));cell_height=height+52
    font=ImageFont.load_default(size=17);files=[]
    for offset in range(0,len(shot_frames),20):
        shots=shot_frames[offset:offset+20]
        sheet=Image.new('RGB',(width*4,math.ceil(len(shots)/4)*cell_height),'#E7D9BB')
        draw=ImageDraw.Draw(sheet)
        for i,shot in enumerate(shots):
            x=i%4*width;y=i//4*cell_height
            with Image.open(decoded[shot['frame']]) as im:
                sheet.paste(im.convert('RGB').resize((width,height),Image.Resampling.LANCZOS),(x,y))
            text=f"{shot['id']} / {shot['frame']/p.fps:.2f}s / {shot['name']}"
            while draw.textlength(text,font=font)>width-16:text=text[:-2]+'…'
            draw.text((x+8,y+height+6),text,fill='#13252B',font=font)
        file=folder/f'decoded-storyboard-{offset//20+1}.jpg';sheet.save(file,quality=90);files.append(file)
    return files
