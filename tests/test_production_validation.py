"""Small application fixtures; never read or write the Unit 9 production tree."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np
import opentimelineio as otio

from sbph.project import Project, binary, dump, sha
from sbph.fingerprint import BUILD_SCHEMA, runtime_identity
from sbph.media import assemble, probe, render_shots
from sbph.timeline import timeline
from sbph.validation import audio_cues, validate_shot_set


class ProductionValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.media.cleanup)
        cls.clip=Path(cls.media.name)/'clip.mp4'
        subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=red:s=16x16:r=30','-frames:v','7','-c:v','libx264','-pix_fmt','yuv420p',str(cls.clip)],check=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'src').mkdir()
        self.driver=self.root/'custom.cjs'
        self.driver.write_text("exports.init=async()=>{};exports.frame=exports.shotFrame=()=>'<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"16\" height=\"16\"><rect width=\"16\" height=\"16\" fill=\"red\"/></svg>';")
        with wave.open(str(self.root/'audio.wav'),'wb') as w:
            w.setparams((1,2,48000,0,'NONE','not compressed'))
            values=(np.sin(np.arange(9600)*2*np.pi*220/48000)*12000).astype('<i2')
            w.writeframes(values.tobytes())
        self.edit={'title':'Fixture','fps':30,'frames':6,'width':16,'height':16,'scenes':[
            {'id':str(i+1),'start':i*3,'end':(i+1)*3,'kind':'test','name':'Shot','action':'Act'} for i in range(2)]}
        self.config={'edit':'custom-edit.json','driver':'custom.cjs','audio':'audio.wav','handles':2,'source_globs':['src/**/*']}
        self.save()
        runtime_patch=patch('sbph.fingerprint.runtime_identity',return_value={'testTools':'v1'})
        self.runtime=runtime_patch.start();self.addCleanup(runtime_patch.stop)
        self.p=Project.load(self.root/'production.json')
        self.manifest=self.make_manifest()

    def save(self):
        dump(self.root/'custom-edit.json',self.edit);dump(self.root/'production.json',self.config)

    def make_manifest(self):
        fingerprint,inventory=self.p.source_inventory();records={}
        for s in self.edit['scenes']:
            file=self.p.output/'shots'/f"{s['id']}-test.mp4";file.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(self.clip,file)
            records[s['id']]={'file':str(file),'id':s['id'],'frames':7,'bodyFrames':3,'handleIn':2,'handleOut':2,'sourceStart':2,'timelineStart':s['start'],'fps':30,'sha256':sha(file),'sourceFingerprint':fingerprint,'handlePolicy':'Fixture handles'}
        manifest={'schemaVersion':BUILD_SCHEMA,'fps':30,'sourceFingerprint':fingerprint,'sourceInventory':inventory,'sourceEditSha256':sha(self.root/'custom-edit.json'),'sourceDriverSha256':sha(self.driver),'shots':records}
        dump(self.p.output/'shots.json',manifest)
        return manifest

    def test_valid_set_checks_actual_media(self):
        self.assertEqual(len(validate_shot_set(self.p)['shots']),2)

    def test_legacy_manifest_rejected_without_rewriting(self):
        del self.manifest['schemaVersion'];dump(self.p.output/'shots.json',self.manifest)
        before=(self.p.output/'shots.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'Legacy'):validate_shot_set(self.p)
        self.assertEqual((self.p.output/'shots.json').read_bytes(),before)

    def test_stale_assembly_and_timeline_fail_before_writing(self):
        output=self.p.output/'assembly.mp4';output.write_bytes(b'previous delivery')
        interchange=self.p.output/'human-edit.otio';interchange.write_bytes(b'previous timeline')
        self.driver.write_text('changed')
        with patch('sbph.media.ffmpeg.run') as encoder:
            for operation in [assemble,timeline]:
                with self.assertRaisesRegex(ValueError,'Stale'):operation(self.p)
            encoder.assert_not_called()
        self.assertEqual(output.read_bytes(),b'previous delivery')
        self.assertEqual(interchange.read_bytes(),b'previous timeline')

    def test_missing_changed_and_incomplete_clips_rejected(self):
        for mode in ['changed','missing','incomplete']:
            with self.subTest(mode=mode):
                self.manifest=self.make_manifest()
                file=self.p.output/'shots/1-test.mp4'
                if mode=='changed':file.write_bytes(b'bad media')
                elif mode=='missing':file.unlink()
                else:
                    del self.manifest['shots']['1'];dump(self.p.output/'shots.json',self.manifest)
                with self.assertRaises(ValueError):validate_shot_set(self.p)

    def test_ranges_fps_and_mixed_builds_rejected(self):
        for field,value in [('sourceStart',0),('handleOut',1),('frames',6),('fps',24),('timelineStart',1),('sourceFingerprint','old')]:
            with self.subTest(field=field):
                manifest=json.loads(json.dumps(self.manifest));manifest['shots']['1'][field]=value
                dump(self.p.output/'shots.json',manifest)
                with self.assertRaises(ValueError):validate_shot_set(self.p)

    def test_record_hash_cannot_hide_wrong_media_metadata(self):
        self.manifest['shots']['1']['frames']=8
        dump(self.p.output/'shots.json',self.manifest)
        with self.assertRaises(ValueError):validate_shot_set(self.p)
        # A valid range record with bytes from a different-sized movie also fails.
        with patch('sbph.media.probe',return_value={'streams':[{'codec_type':'video','nb_frames':'7','avg_frame_rate':'30/1','width':32,'height':16}]}):
            dump(self.p.output/'shots.json',self.manifest|{'shots':json.loads(json.dumps(self.make_manifest()['shots']))})
            with self.assertRaisesRegex(ValueError,'metadata'):validate_shot_set(self.p)

    def test_handles_custom_driver_edit_and_audio_are_fingerprinted(self):
        original=self.p.source_inventory()[0]
        for target in [self.driver,self.root/'custom-edit.json',self.root/'audio.wav']:
            before=target.read_bytes();target.write_bytes(before+b' ')
            if target.suffix=='.json':
                # Whitespace is part of source identity, despite equal parsed data.
                pass
            self.assertNotEqual(original,self.p.source_inventory()[0]);target.write_bytes(before)
        self.config['handles']=3;self.save()
        self.assertNotEqual(original,Project.load(self.root/'production.json').source_inventory()[0])

    def test_declared_external_source_and_added_nested_source_invalidate(self):
        external=self.root.parent/(self.root.name+'-font.bin');external.write_bytes(b'font')
        self.addCleanup(external.unlink)
        self.config['source_files']=[str(external)];self.save();p=Project.load(self.root/'production.json')
        first=p.source_inventory()[0];external.write_bytes(b'revised font')
        self.assertNotEqual(first,p.source_inventory()[0])
        first=p.source_inventory()[0];nested=self.root/'src/nested';nested.mkdir();(nested/'helper.cjs').write_text('helper')
        self.assertNotEqual(first,p.source_inventory()[0])
        external.unlink()
        with self.assertRaisesRegex(ValueError,'Declared source'):p.source_inventory()
        external.write_bytes(b'restored')

    def test_tool_identity_and_live_config_changes_invalidate(self):
        original=self.p.source_inventory()[0];self.runtime.return_value={'testTools':'v2'}
        self.assertNotEqual(original,self.p.source_inventory()[0])
        self.config['handles']=3;self.save()
        with self.assertRaisesRegex(ValueError,'reload'):self.p.source_inventory()

    def test_review_and_artifact_settings_do_not_require_rerendering(self):
        original=self.p.source_inventory()[0]
        self.config.update(delivery='production/review.mp4',reference='production/proof.mp4',timeline_file='edit.otio',proof_start=0,proof_duration=.2,verification={'profile':'generic','reference_frames':[]})
        self.save();current=Project.load(self.root/'production.json')
        self.assertEqual(original,current.source_inventory()[0])
        self.assertEqual(len(validate_shot_set(current)['shots']),2)

    def test_cues_use_seconds_at_current_rate(self):
        dump(self.p.output/'audio-cues.json',{'sourceSha256':sha(self.p.audio),'markerCandidates':[{'seconds':.1,'frame':99,'strength':1}]})
        self.assertEqual(audio_cues(self.p)[0]['frame'],3)

    def test_unknown_shot_fails_without_rendering(self):
        with patch('sbph.media.render_picture') as renderer:
            with self.assertRaisesRegex(ValueError,'Unknown shot'):render_shots(self.p,{'absent'})
            renderer.assert_not_called()

    def test_invalid_render_dimensions_handles_and_kind_rejected(self):
        for key,value in [('width',-2),('height',True),('width',15),('fps',True),('frames',False)]:
            with self.subTest(key=key,value=value):
                original=self.edit[key];self.edit[key]=value;self.save()
                with self.assertRaises(ValueError):Project.load(self.root/'production.json')
                self.edit[key]=original
        self.config['handles']=True;self.save()
        with self.assertRaises(ValueError):Project.load(self.root/'production.json')
        self.config['handles']=2;self.edit['scenes'][0]['kind']='nested/../../outside';self.save()
        with self.assertRaisesRegex(ValueError,'Unsafe shot kind'):Project.load(self.root/'production.json')

    def test_short_source_audio_cannot_enter_assembly(self):
        with wave.open(str(self.p.audio),'wb') as w:
            w.setparams((1,2,48000,0,'NONE','not compressed'));w.writeframes(b'\0'*100)
        self.make_manifest()
        with patch('sbph.media.ffmpeg.run') as encoder:
            with self.assertRaisesRegex(ValueError,'shorter'):assemble(self.p)
            encoder.assert_not_called()

    def test_failed_json_write_preserves_previous_record(self):
        file=self.root/'record.json';dump(file,{'previous':'good'})
        with self.assertRaises(TypeError):dump(file,{'bad':object()})
        self.assertEqual(json.loads(file.read_text()),{'previous':'good'})

    def test_actual_tiny_render_timeline_assembly(self):
        with contextlib.redirect_stdout(io.StringIO()):
            render_shots(self.p)
            file=timeline(self.p)
            movie=assemble(self.p)
        tl=otio.adapters.read_from_file(str(file))
        self.assertEqual(tl.duration().value,6)
        self.assertEqual([c.source_range.start_time.value for c in tl.video_tracks()[0]],[2,2])
        self.assertEqual(int(probe(movie)['streams'][0]['nb_frames']),6)
        self.assertEqual(len(validate_shot_set(self.p)['shots']),2)


class RuntimeFingerprint(unittest.TestCase):
    def test_local_tools_and_installed_libraries_are_identified(self):
        identity=runtime_identity()
        self.assertIn('libvips' if 'libvips' in identity['sharp'] else 'vips',identity['sharp'])
        for name in ['node','ffmpeg','ffprobe']:
            self.assertEqual(len(identity['tools'][name]['sha256']),64)
        self.assertTrue(identity['nodePackages'])


if __name__=='__main__':unittest.main()
