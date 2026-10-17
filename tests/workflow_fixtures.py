from pathlib import Path
import shutil
import wave
import numpy as np
from sbph.project import FRAMEWORK,Project


def project(root):
    root=Path(root).resolve()/'Film with spaces'
    shutil.copytree(FRAMEWORK/'examples/signal',root,ignore=shutil.ignore_patterns('audio','production','.sbph','__pycache__'))
    (root/'audio').mkdir()
    time=np.arange(192000)/48000
    values=(np.sin(2*np.pi*(110*time+12*time*time))*10000).astype('<i2')
    with wave.open(str(root/'audio/source.wav'),'wb') as stream:
        stream.setparams((2,2,48000,0,'NONE','not compressed'));stream.writeframes(np.column_stack((values,values)).tobytes())
    return Project.load(root/'production.json')


def files(root):
    from sbph.project import sha
    return {str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
