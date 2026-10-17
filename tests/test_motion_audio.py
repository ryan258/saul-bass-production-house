import hashlib, tempfile, unittest, wave
from pathlib import Path
from types import SimpleNamespace
from sbph.motion import verify_audio_window


class MotionAudioContract(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.audio=self.root/'source.wav'
        self.project=self.root/'scene/project.ts';self.project.parent.mkdir()
        self.samples=bytes(range(256))*200
        self.write(self.audio,self.samples)
        self.spec={'sourceStartFrame':2,'fps':30,'frames':3,'sourceStartSample':3200,'sourceSamples':4800}
        self.expected=self.samples[3200*4:(3200+4800)*4]
        self.crop=self.project.parent/'audio.wav';self.write(self.crop,self.expected)
        self.p=SimpleNamespace(audio=self.audio)

    def write(self,file,data):
        with wave.open(str(file),'wb') as w:
            w.setparams((2,2,48000,0,'NONE','not compressed'));w.writeframes(data)

    def test_exact_source_samples(self):
        self.assertEqual(verify_audio_window(self.p,self.project,self.spec),hashlib.sha256(self.expected).hexdigest())

    def test_offset_crop_rejected(self):
        self.write(self.crop,self.samples[3201*4:(3201+4800)*4])
        with self.assertRaisesRegex(ValueError,'exact original'):
            verify_audio_window(self.p,self.project,self.spec)

    def test_frame_sample_disagreement_rejected(self):
        self.spec['sourceStartSample']+=1
        with self.assertRaisesRegex(ValueError,'disagree'):
            verify_audio_window(self.p,self.project,self.spec)

    def test_short_source_and_matching_short_crop_rejected(self):
        self.write(self.audio,self.samples[:6000*4])
        self.write(self.crop,self.samples[3200*4:6000*4])
        with self.assertRaisesRegex(ValueError,'beyond'):
            verify_audio_window(self.p,self.project,self.spec)

    def test_short_editor_crop_rejected(self):
        self.write(self.crop,self.expected[:-4])
        with self.assertRaisesRegex(ValueError,'sample count'):
            verify_audio_window(self.p,self.project,self.spec)

    def test_truncated_wav_payload_rejected(self):
        data=self.crop.read_bytes();self.crop.write_bytes(data[:-4])
        with self.assertRaisesRegex(ValueError,'Short WAV'):
            verify_audio_window(self.p,self.project,self.spec)

    def test_invalid_proof_ranges_rejected(self):
        for key,value in [('fps',0),('frames',True),('sourceStartSample',-1)]:
            with self.subTest(key=key):
                spec={**self.spec,key:value}
                with self.assertRaisesRegex(ValueError,'range field'):
                    verify_audio_window(self.p,self.project,spec)


if __name__=='__main__':unittest.main()
