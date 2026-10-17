"""Use librosa for candidate onsets and beats; editorial intent stays human-owned."""
import json, subprocess, importlib.metadata
import numpy as np
import librosa
from .project import binary,dump,sha

def analyze(p):
    sr=22050;hop=256
    raw=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(p.audio),'-ac','1','-ar',str(sr),'-f','f32le','pipe:1'])
    y=np.frombuffer(raw,dtype='<f4').copy()
    envelope=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop)
    onsets=librosa.onset.onset_detect(onset_envelope=envelope,sr=sr,hop_length=hop,units='frames',backtrack=False)
    tempo,beats=librosa.beat.beat_track(onset_envelope=envelope,sr=sr,hop_length=hop,units='time')
    max_strength=float(max(envelope.max(),1e-8));events=[]
    for n in onsets:
        seconds=float(n*hop/sr)
        events.append({'seconds':round(seconds,6),'frame':int(round(seconds*p.fps)),'strength':float(envelope[n]/max_strength),'kind':'onset-candidate'})
    chosen=[]
    for e in sorted(events,key=lambda e:e['strength'],reverse=True):
        if all(abs(e['frame']-a['frame'])>=round(p.fps*.5) for a in chosen):chosen.append(e)
        if len(chosen)>=48:break
    chosen.sort(key=lambda e:e['frame'])
    data={'source':str(p.public_path(p.audio)),'sourceSha256':sha(p.audio),'library':'librosa '+importlib.metadata.version('librosa'),'method':'onset_strength + onset_detect + beat_track; no remote calls','sampleRate':sr,'hopLength':hop,'nominalTimeResolutionSeconds':hop/sr,'tempoEstimateBpm':float(np.asarray(tempo).reshape(-1)[0]),'beatsSeconds':[float(v) for v in beats],'onsets':events,'markerCandidates':chosen,'interpretation':'Candidates for review, not proof of a perceptually biggest hit or a compulsory cut. Spoken-word passages and tempo changes can mislead beat tracking.'}
    dump(p.output/'audio-cues.json',data)
    print(f"librosa: {len(events)} onset candidates; {len(chosen)} strongest spaced candidates for markers. Audio stayed local.",flush=True)
    return data
