import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import wave

import numpy as np
from sbph.project import binary
from sbph.verify import audio_comparison,compare_channels


class AudioComparison(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'source.wav';self.delivery=Path(self.temp.name)/'delivery.wav'
        self.signal=np.sin(np.arange(8000)*2*np.pi*100/16000).astype(np.float32)*.5
        self.source.write_bytes(b'source');self.delivery.write_bytes(b'delivery')

    def compare(self,source,delivery,codec='pcm_s16le'):
        with patch('sbph.verify.decode_mono',side_effect=[source,delivery]),patch('sbph.verify.channel_comparison',return_value={'fixture':'mono checks only'}),patch('sbph.verify.probe',return_value={'streams':[{'codec_type':'audio','codec_name':codec,'sample_rate':'48000' if codec=='aac' else '16000'}]}):
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

    def test_source_replaced_or_removed_during_decode_cannot_acquire_new_hash(self):
        for change in ['replace','remove']:
            with self.subTest(change=change):
                self.source.write_bytes(b'original source')
                def decode(path):
                    if path==self.delivery:
                        if change=='replace':self.source.write_bytes(b'replacement source')
                        else:self.source.unlink()
                    return self.signal.copy()
                stream={'codec_type':'audio','codec_name':'pcm_s16le','sample_rate':'16000'}
                with patch('sbph.verify.decode_mono',side_effect=decode),patch('sbph.verify.probe',return_value={'streams':[stream]}):
                    with self.assertRaisesRegex(RuntimeError,'Source audio changed during comparison'):
                        audio_comparison(self.source,self.delivery)

    def test_channel_content_and_level_cannot_hide_in_identical_mono_sum(self):
        t=np.arange(48000)/48000
        stereo=np.column_stack((.3*np.sin(2*np.pi*191*t),.2*np.sin(2*np.pi*431*t))).astype(np.float32)
        self.assertEqual(len(compare_channels(stereo,stereo.copy())['channels']),2)
        for changed in [stereo[:,::-1],np.repeat(stereo.mean(axis=1)[:,None],2,axis=1),stereo*.5,stereo*1.1]:
            with self.subTest(change=changed.shape),self.assertRaisesRegex(ValueError,'channel'):
                compare_channels(stereo,changed)

    def test_one_silent_channel_is_checked_independently(self):
        stereo=np.column_stack((self.signal,np.zeros_like(self.signal)))
        self.assertIsNone(compare_channels(stereo,stereo)['channels'][1]['correlation'])
        changed=stereo.copy();changed[:,1]=self.signal*.1
        with self.assertRaisesRegex(ValueError,'Silent audio channel'):compare_channels(stereo,changed)

    def test_actual_stereo_swap_and_gain_change_are_rejected(self):
        t=np.arange(24000)/48000
        samples=np.column_stack((np.sin(2*np.pi*191*t),np.sin(2*np.pi*431*t)))*8000
        def write(path,values):
            with wave.open(str(path),'wb') as stream:
                stream.setparams((2,2,48000,0,'NONE','not compressed'));stream.writeframes(values.astype('<i2').tobytes())
        write(self.source,samples)
        for values in [samples[:,::-1],samples*.5]:
            write(self.delivery,values)
            with self.assertRaises(ValueError):audio_comparison(self.source,self.delivery)


if __name__=='__main__':unittest.main()
