import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import numpy as np
from sbph.motion import build, motion_inventory, validate_baseline, verify_audio_window
from sbph.project import binary, dump, sha


class MotionBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        root=Path(cls.temp.name);cls.source=root/'source.wav';cls.baseline=root/'proof.mp4'
        t=np.arange(96000)/48000
        cls.samples=(np.sin(2*np.pi*(80*t+22*t*t))*12000).astype('<i2')
        with wave.open(str(cls.source),'wb') as w:
            w.setparams((1,2,48000,0,'NONE','not compressed'));w.writeframes(cls.samples.tobytes())
        subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=red:s=16x16:r=30','-ss','0.1','-i',str(cls.source),'-frames:v','15','-t','0.5','-c:v','libx264','-c:a','aac','-b:a','128k',str(cls.baseline)],check=True)

    def setUp(self):
        self.work=tempfile.TemporaryDirectory();self.addCleanup(self.work.cleanup)
        self.root=Path(self.work.name);scene=self.root/'scene';scene.mkdir()
        self.project=scene/'project.ts';self.project.write_text('// fixture')
        self.meta=scene/'shutdown.meta';self.meta.write_text('{"timeEvents":[]}')
        self.output=self.root/'production';self.output.mkdir()
        self.movie=self.output/'proof.mp4';shutil.copy2(self.baseline,self.movie)
        self.spec={'sourceStartFrame':3,'sourceStartSample':4800,'frames':15,'sourceSamples':24000,'fps':30,'width':16,'height':16,'cuts':[0,15],'notes':'Fixture'}
        dump(scene/'proof.json',self.spec)
        with wave.open(str(scene/'audio.wav'),'wb') as w:
            w.setparams((1,2,48000,0,'NONE','not compressed'));w.writeframes(self.samples[4800:28800].tobytes())
        self.p=SimpleNamespace(audio=self.source,root=self.root,output=self.output,driver=self.root/'driver.cjs',data={'motion_canvas':'scene/project.ts'},source_inventory=lambda:('fixture',[]))
        self.metadata={'sha256':sha(self.movie),'sourceStartFrame':3,'frames':15,'fps':30}
        dump(self.movie.with_suffix('.json'),self.metadata)

    def test_legacy_baseline_requires_actual_audio_and_matching_media(self):
        self.assertTrue(verify_audio_window(self.p,self.project,self.spec))
        self.assertGreater(validate_baseline(self.p,self.project,self.spec,self.movie)['monoCorrelationAt16k'],.995)

    def test_wrong_window_duration_rate_hash_or_source_rejected(self):
        for key,value in [('sourceStartFrame',6),('frames',30),('fps',24),('sha256','bad'),('sourceAudioSha256','different')]:
            with self.subTest(key=key):
                dump(self.movie.with_suffix('.json'),{**self.metadata,key:value})
                with self.assertRaises(ValueError):validate_baseline(self.p,self.project,self.spec,self.movie)

    def test_matching_sidecar_cannot_hide_wrong_audio_window(self):
        # A crop from another interval defeats provenance inferred only from a
        # sidecar: the comparison must inspect the actual baseline audio.
        crop=self.project.parent/'audio.wav'
        with wave.open(str(crop),'wb') as w:
            w.setparams((1,2,48000,0,'NONE','not compressed'));w.writeframes(self.samples[9600:33600].tobytes())
        with self.assertRaisesRegex(ValueError,'correlation'):
            validate_baseline(self.p,self.project,self.spec,self.movie)

    def test_media_metadata_cannot_be_hidden_by_sidecar(self):
        with patch('sbph.motion.probe',return_value={'streams':[{'codec_type':'video','nb_frames':'15','avg_frame_rate':'30/1','width':32,'height':16}]}):
            with self.assertRaisesRegex(ValueError,'media'):validate_baseline(self.p,self.project,self.spec,self.movie)

    def test_build_rejects_wrong_baseline_before_typecheck_or_outputs(self):
        dump(self.movie.with_suffix('.json'),{**self.metadata,'sourceStartFrame':9})
        before={str(f.relative_to(self.root)):sha(f) for f in self.root.rglob('*') if f.is_file()}
        with patch('sbph.motion.run_native') as runner:
            with self.assertRaisesRegex(ValueError,'window'):build(self.p)
            runner.assert_not_called()
        self.assertEqual(before,{str(f.relative_to(self.root)):sha(f) for f in self.root.rglob('*') if f.is_file()})

    def test_cue_changes_during_render_fail_before_encoding(self):
        final=self.output/'motion-canvas/unit-9-shutdown-motion-canvas.mp4';final.parent.mkdir();final.write_bytes(b'previous output')
        def run(command,**kwargs):
            if command[2]=='render':self.meta.write_text('{"timeEvents":[{"name":"changed"}]}')
        with patch('sbph.motion.browser_identity',return_value={'fixture':'browser'}),patch('sbph.motion.validate_baseline',return_value={'fixture':'verified elsewhere'}),patch('sbph.motion.run_native',side_effect=run),patch('sbph.motion.ffmpeg.run') as encoder:
            with self.assertRaisesRegex(RuntimeError,'cue metadata changed'):build(self.p)
            encoder.assert_not_called()
        self.assertEqual(final.read_bytes(),b'previous output')

    def test_inventory_detects_meta_additions_deletions_and_edits(self):
        before=motion_inventory(self.project)
        self.meta.write_text('changed');self.assertNotEqual(before,motion_inventory(self.project))
        self.meta.write_text('{"timeEvents":[]}');self.assertEqual(before,motion_inventory(self.project))
        added=self.project.parent/'extra.meta';added.write_text('{}');self.assertNotEqual(before,motion_inventory(self.project))
        added.unlink();self.meta.unlink();self.assertNotEqual(before,motion_inventory(self.project))


if __name__=='__main__':unittest.main()
