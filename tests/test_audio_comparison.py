import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import wave

import numpy as np
from sbph.project import binary
from sbph.verify import audio_comparison


class AudioComparison(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'source.wav';self.delivery=Path(self.temp.name)/'delivery.wav'
        self.signal=np.sin(np.arange(8000)*2*np.pi*100/16000).astype(np.float32)*.5
        self.source.write_bytes(b'source');self.delivery.write_bytes(b'delivery')

    def compare(self,source,delivery,codec='pcm_s16le'):
        with patch('sbph.verify.decode_mono',side_effect=[source,delivery]),patch('sbph.verify.probe',return_value={'streams':[{'codec_type':'audio','codec_name':codec,'sample_rate':'48000' if codec=='aac' else '16000'}]}):
            return audio_comparison(self.source,self.delivery)

    def test_short_recording_has_alignment_windows(self):
        report=self.compare(self.signal,self.signal.copy())
        self.assertGreater(len(report['offsetWindows']),0)
        self.assertTrue(all(w['estimatedOffsetSamplesAt16k']==0 for w in report['offsetWindows']))

    def test_truncated_or_extended_lossless_audio_rejected(self):
        for audio in [self.signal[:4000],np.append(self.signal,0)]:
            with self.assertRaisesRegex(ValueError,'sample count'):self.compare(self.signal,audio)

    def test_codec_padding_is_explicit_and_bounded(self):
        report=self.compare(self.signal,np.pad(self.signal,(0,341)),codec='aac')
        self.assertEqual(report['allowedSampleDifferenceAt16k'],342)
        with self.assertRaisesRegex(ValueError,'sample count'):
            self.compare(self.signal,np.pad(self.signal,(0,343)),codec='aac')

    def test_shift_with_high_global_correlation_rejected(self):
        delayed=np.concatenate([np.zeros(2,dtype=np.float32),self.signal[:-2]])
        with self.assertRaisesRegex(ValueError,'alignment'):self.compare(self.signal,delayed)

    def test_silence_has_honest_limits(self):
        report=self.compare(np.zeros(8000),np.zeros(8000))
        self.assertIsNone(report['monoCorrelationAt16k'])
        self.assertIn('cannot be measured',report['alignmentEvidence'])
        with self.assertRaisesRegex(ValueError,'audible'):self.compare(np.zeros(8000),self.signal)

    def test_nonfinite_constant_and_too_short_audio_rejected(self):
        for source,delivery in [(self.signal,np.full(8000,np.nan)),(np.ones(8000),np.ones(8000)),(np.zeros(10),np.zeros(10)),(np.zeros(128),np.zeros(128))]:
            with self.assertRaises(ValueError):self.compare(source,delivery)

    def test_actual_wav_and_aac_decoding(self):
        def write(path):
            with wave.open(str(path),'wb') as w:
                w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes((self.signal*32767).astype('<i2').tobytes())
        write(self.source);write(self.delivery)
        self.assertGreater(audio_comparison(self.source,self.delivery)['monoCorrelationAt16k'],.995)
        aac=Path(self.temp.name)/'delivery.m4a'
        subprocess.run([binary('ffmpeg'),'-v','error','-i',str(self.source),'-c:a','aac','-b:a','128k',str(aac)],check=True)
        self.assertGreater(audio_comparison(self.source,aac)['monoCorrelationAt16k'],.995)


if __name__=='__main__':unittest.main()
