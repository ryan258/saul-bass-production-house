"""Small real-media checks for editorial audio windows and their consumers."""
import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import numpy as np

from sbph.assembly_check import check as conform
from sbph.media import BSF
from sbph.project import binary,sha
from sbph.verify import audio_comparison,project_audio_comparison,verify


def write_wav(path,samples):
    pcm=np.column_stack((samples,samples)).astype('<i2')
    with wave.open(str(path),'wb') as stream:
        stream.setparams((2,2,48000,0,'NONE','not compressed'))
        stream.writeframes(pcm.tobytes())


class EditorialAudioWindows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.media.cleanup)
        folder=Path(cls.media.name)
        t=np.arange(48000)/48000
        cls.samples=(np.sin(2*np.pi*(191*t+850*t*t))*12000).astype('<i2')
        cls.source=folder/'source-with-tail.wav';write_wav(cls.source,cls.samples)
        cls.exact=folder/'edit.wav';write_wav(cls.exact,cls.samples[:24000])
        cls.movie=folder/'edit.mp4'
        subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=red:s=32x24:r=24',
            '-i',str(cls.source),'-frames:v','12','-t','0.5',
            '-vf','scale=out_color_matrix=bt709:out_range=tv','-c:v','libx264',
            '-pix_fmt','yuv420p','-bsf:v',BSF,'-c:a','aac','-b:a','320k',
            '-ar','48000','-ac','2','-color_primaries','bt709','-color_trc','iec61966-2-1',
            '-colorspace','bt709','-color_range','tv',str(cls.movie)],check=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.output=self.root/'production';self.output.mkdir()
        self.audio=self.root/'source.wav';shutil.copy2(self.source,self.audio)
        self.original_hash=sha(self.audio)
        self.p=SimpleNamespace(audio=self.audio,frames=12,fps=24)

    def assert_original_unchanged(self):
        self.assertEqual(sha(self.audio),self.original_hash)

    def test_long_source_tail_uses_edit_window_and_keeps_original_identity(self):
        report=project_audio_comparison(self.p,self.exact)
        self.assertEqual(report['sourceSha256'],self.original_hash)
        self.assertEqual(report['sourceWindow'],{'startSeconds':0.0,'durationSeconds':0.5,
            'startSampleAt16k':0,'samplesAt16k':8000,'startFrame':0,'frames':12,'fps':24})
        self.assertEqual(report['decodedSourceSamplesAt16k'],16000)
        self.assertEqual(report['comparedSourceSamplesAt16k'],8000)
        self.assertEqual(report['decodedDeliverySamplesAt16k'],8000)
        self.assertEqual(report['decodedSampleDifferenceAt16k'],0)
        self.assert_original_unchanged()
        # Existing two-argument callers still compare the complete recording.
        with self.assertRaisesRegex(ValueError,'sample count'):
            audio_comparison(self.audio,self.exact)

    def test_shifted_short_and_extended_delivery_cannot_hide_in_source_tail(self):
        deliveries={
            'shifted':np.concatenate((np.zeros(960,dtype='<i2'),self.samples[:23040])),
            'short':self.samples[:21600],
            'extended':self.samples[:26400],
        }
        for label,samples in deliveries.items():
            with self.subTest(delivery=label):
                path=self.root/(label+'.wav');write_wav(path,samples)
                with self.assertRaises(ValueError):project_audio_comparison(self.p,path)
                self.assert_original_unchanged()

    def test_proof_interval_uses_its_matching_source_window(self):
        path=self.root/'proof.wav';write_wav(path,self.samples[6000:18000])
        report=project_audio_comparison(self.p,path,start=3,frames=6)
        self.assertEqual(report['sourceWindow']['startSeconds'],.125)
        self.assertEqual(report['sourceWindow']['durationSeconds'],.25)
        self.assertEqual(report['sourceWindow']['startFrame'],3)
        self.assertEqual(report['sourceWindow']['frames'],6)
        self.assert_original_unchanged()

    def test_nonzero_thirty_fps_aac_window_is_trimmed_before_resampling(self):
        # 1/30 second is 1600 source samples but 533 1/3 samples at 16 kHz.
        # Rounding a pre-resampled source introduces a false phase mismatch.
        source=self.root/'high-frequency-source.wav'
        t=np.arange(48000)/48000
        samples=(np.sin(2*np.pi*(1100*t+3000*t*t))*12000).astype('<i2')
        write_wav(source,samples);before=sha(source)
        delivery=self.root/'frame-one-proof.m4a'
        subprocess.run([binary('ffmpeg'),'-v','error','-ss',str(1/30),'-i',str(source),
            '-t','0.5','-c:a','aac','-b:a','320k','-ar','48000','-ac','2',str(delivery)],check=True)
        project=SimpleNamespace(audio=source,frames=30,fps=30)
        report=project_audio_comparison(project,delivery,start=1,frames=15)
        self.assertGreater(report['monoCorrelationAt16k'],.995)
        self.assertEqual(report['sourceWindow']['startFrame'],1)
        self.assertEqual(report['sourceWindow']['frames'],15)
        self.assertEqual(sha(source),before)

    def test_invalid_editorial_intervals_and_short_source_fail(self):
        for start,frames in [(-1,6),(0,0),(7,6),(0,1.0)]:
            with self.subTest(start=start,frames=frames):
                with self.assertRaisesRegex(ValueError,'inside the editorial'):
                    project_audio_comparison(self.p,self.exact,start=start,frames=frames)
        short=self.root/'short-source.wav';write_wav(short,self.samples[:12000])
        with self.assertRaisesRegex(ValueError,'shorter than the requested editorial'):
            audio_comparison(short,self.exact,source_window=(0,.5))

    def test_generic_verification_and_conform_use_editorial_window(self):
        movie=self.output/'assembly.mp4';shutil.copy2(self.movie,movie)
        reference=self.root/'reference.mp4';shutil.copy2(self.movie,reference)
        self.p=SimpleNamespace(root=self.root,output=self.output,audio=self.audio,
            data={'reference':'reference.mp4'},fps=24,frames=12,width=32,height=24,handles=2,
            edit={'title':'Window fixture','scenes':[{'id':'one','name':'One','start':0,'end':12}]},
            source_inventory=lambda:('fixture',[]),public_path=lambda path:Path(path).resolve())
        records={'sourceFingerprint':'fixture','shots':{'one':{'frames':16}}}
        with patch('sbph.validation.validate_shot_set',return_value=records),contextlib.redirect_stdout(io.StringIO()):
            delivery_report=verify(self.p)
            conform_report=conform(self.p)
        for report in [delivery_report,conform_report]:
            self.assertEqual(report['audio']['sourceSha256'],self.original_hash)
            self.assertEqual(report['audio']['sourceWindow']['frames'],12)
            self.assertEqual(report['audio']['sourceWindow']['startFrame'],0)
            self.assertGreater(report['audio']['monoCorrelationAt16k'],.995)
        self.assert_original_unchanged()


if __name__=='__main__':unittest.main()
