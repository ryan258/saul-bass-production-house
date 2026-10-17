"""Generate this example's four-second original stereo PCM recording locally."""
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import wave


def prepare(root):
    edit=json.loads((root/'data/edit.json').read_text())
    rate=48000
    count,remainder=divmod(edit['frames']*rate,edit['fps'])
    if remainder:raise ValueError('Example duration must resolve to whole audio samples')
    samples=array('h')
    for index in range(count):
        t=index/rate
        fade=min(1,t/.03,(count-1-index)/rate/.03)
        amplitude=.04*math.sin(2*math.pi*110*t)
        for onset,frequency in [(0.1,330),(1.4,440),(3.45,660)]:
            elapsed=t-onset
            if 0<=elapsed<.3:
                envelope=math.sin(math.pi*elapsed/.3)**2
                amplitude+=.35*envelope*math.sin(2*math.pi*frequency*elapsed)
        value=round(amplitude*fade*32767)
        samples.extend([value,value])
    if sys.byteorder!='little':samples.byteswap()
    output=root/'audio/source.wav';output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='signal-audio-',dir=output.parent) as folder:
        generated=Path(folder)/'source.wav'
        with wave.open(str(generated),'wb') as stream:
            stream.setparams((2,2,rate,0,'NONE','not compressed'));stream.writeframes(samples.tobytes())
        digest=hashlib.sha256(generated.read_bytes()).hexdigest()
        if output.exists():
            if hashlib.sha256(output.read_bytes()).hexdigest()!=digest:
                raise ValueError('Existing example audio differs; preserve it before intentionally replacing audio/source.wav')
        else:generated.replace(output)
    print(f'Example audio ready: {count} samples per channel; SHA-256 {digest}')
    return output


if __name__=='__main__':prepare(Path(__file__).resolve().parents[1])
