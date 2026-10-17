from pathlib import Path
from dataclasses import dataclass
import json, os, shutil, hashlib, tempfile

FRAMEWORK=Path(__file__).resolve().parents[2]

def dump(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def binary(name):
    value=os.environ.get('SBPH_'+name.upper()) or shutil.which(name)
    if not value:raise ValueError(f'{name} is missing; install it or set SBPH_{name.upper()}')
    return value

@dataclass
class Project:
    config:Path
    data:dict
    edit:dict
    root:Path
    deliver_root:Path
    output:Path
    audio:Path
    driver:Path
    fps:int
    width:int
    height:int
    frames:int
    handles:int

    @classmethod
    def load(cls,config,require_audio=True):
        config=Path(config).resolve();data=json.loads(config.read_text());root=(config.parent/data.get('root','.')).resolve()
        def resolve(key,default):return (root/data.get(key,default)).resolve()
        edit=json.loads(resolve('edit','data/edit.json').read_text())
        fps=edit['fps'];frames=edit['frames'];scenes=edit['scenes']
        if type(fps) is not int or fps<=0:raise ValueError('Use a positive integer fps')
        for key in ['frames','width','height']:
            if type(edit[key]) is not int or edit[key]<=0:raise ValueError(key+' must be a positive integer')
        if edit['width']%2 or edit['height']%2:raise ValueError('H.264 delivery requires even width and height')
        if not scenes or scenes[0]['start']!=0 or scenes[-1]['end']!=frames:raise ValueError('Edit must cover the whole timeline')
        for i,s in enumerate(scenes):
            if type(s['start']) is not int or type(s['end']) is not int or s['end']<=s['start']:raise ValueError('Shot frame ranges must be non-empty integer intervals')
            if i and scenes[i-1]['end']!=s['start']:raise ValueError('Timeline has a gap or overlapping shots')
        if len({s['id'] for s in scenes})!=len(scenes):raise ValueError('Shot IDs must be unique')
        for s in scenes:
            if not isinstance(s['id'],str) or not s['id'] or any(c not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_' for c in s['id']):raise ValueError('Unsafe shot ID')
            if 'kind' in s and (not isinstance(s['kind'],str) or not s['kind'] or any(c not in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_' for c in s['kind'])):raise ValueError('Unsafe shot kind')
        audio=resolve('audio',edit.get('audio','audio.wav'))
        if require_audio and not audio.is_file():raise ValueError('Source audio is missing: '+str(audio))
        handles=data.get('handles',12)
        if type(handles) is not int or handles<0:raise ValueError('handles must be a nonnegative frame count')
        return cls(config,data,edit,root,Path(data.get('deliver_root',str(root))).resolve(),resolve('output','production'),audio,resolve('driver','src/film.cjs'),fps,edit['width'],edit['height'],frames,handles)

    def source_inventory(self):
        from .fingerprint import build_inventory
        current=Project.load(self.config)
        if current.data!=self.data or current.edit!=self.edit:
            raise ValueError('Project configuration or edit changed; reload the project before building')
        return build_inventory(self)

    def public_path(self,path):
        path=Path(path).resolve()
        try:return self.deliver_root/path.relative_to(self.root)
        except ValueError:return path
