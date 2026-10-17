"""Optional Unit 9 source/asset assertions, separate from generic delivery QA.

These read the film's existing review evidence. They do not generate new source
geometry or establish human editorial acceptance.
"""
import json
from PIL import Image
from .project import sha


def reference_frames(p):
    samples=json.loads((p.root/'review/samples.json').read_text())
    return [{'frame':frame,'file':f'review/references/{frame:05d}.png'} for frame in samples['sourceReferenceFrames']]


def inspect(p):
    assets=[]
    for file in sorted((p.root/'assets/webp').glob('*.webp')):
        with Image.open(file) as im:
            if im.format!='WEBP' or b'VP8L' not in file.read_bytes()[:40] or im.mode!='RGBA':
                raise ValueError('Unit 9 requires lossless RGBA WebP: '+str(file))
            assets.append({'file':str(file.relative_to(p.root)),'size':list(im.size),'losslessWebP':True,'alphaRange':list(im.getchannel('A').getextrema()),'sha256':sha(file)})
    if not assets:raise ValueError('Unit 9 WebP inventory is missing')
    geometry_file=p.root/'review/geometry-samples.json'
    geometry=json.loads(geometry_file.read_text())
    seams=[m['seam']['gap'] for m in geometry if 'seam' in m]
    shutdown=next((m['lever'] for m in geometry if m['frame']==round(38.8*p.fps)),None)
    on=next((m['lever'] for m in geometry if m['frame']==round(41.1*p.fps)),None)
    if not seams or not min(seams)>=28-1e-8:raise ValueError('Unit 9 final connection gap failed')
    if shutdown is None or on is None or not shutdown['grip'][1]>on['grip'][1]+200:
        raise ValueError('Unit 9 shutdown/return geometry failed')
    return {'profile':'unit9','webpAssets':assets,'modelGeometry':{'finalGapMinimumAt1280Stage':min(seams),'shutdownGripY':shutdown['grip'][1],'returnedOnGripY':on['grip'][1]},'geometryEvidenceSha256':sha(geometry_file),'limit':'Stored source geometry and asset checks; not regenerated motion or human timing acceptance.'}
