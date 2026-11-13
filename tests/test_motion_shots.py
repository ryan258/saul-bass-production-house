"""Headless-browser-free shot contract tests, with real PNG encoding and OTIO."""
from pathlib import Path
import contextlib,io,json,subprocess,unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import test_production_validation as fixtures
from sbph.project import Project,dump,sha,binary
from sbph.media import render_shots,assemble,probe
from sbph.validation import validate_shot_set
from sbph.timeline import timeline
from sbph.shot_backend import motion_projects
from sbph.motion_shots import export_body


class MotionShots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProductionValidation.setUpClass();cls.addClassCleanup(fixtures.ProductionValidation.doClassCleanups)

    def setUp(self):
        self.fixture=fixtures.ProductionValidation();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root;self.config=self.fixture.config
        mapping={}
        for identifier in ['1','2']:
            file=self.root/'motion'/identifier/'project.ts';file.parent.mkdir(parents=True)
            file.write_text('isolated fixture');(file.parent/'scene.meta').write_text('{}')
            mapping[identifier]=str(file.relative_to(self.root))
        self.config.update(renderer='motion-canvas',motion_shots=mapping);self.fixture.save()
        self.p=Project.load(self.fixture.p.config);self.p.driver.unlink()
        browser=patch('sbph.fingerprint.browser_identity',return_value={'sha256':'browser-v1'});self.browser=browser.start();self.addCleanup(browser.stop)

    def fake_body(self,p,project,work,count,start=0):
        folder=work/'frames';folder.mkdir()
        for i in range(count):Image.new('RGB',(p.width,p.height),['red','green','blue'][i%3]).save(folder/f'{start+i:06}.png')

    def render(self,selected=None):
        with patch('sbph.motion_shots.export_body',side_effect=self.fake_body),contextlib.redirect_stdout(io.StringIO()):
            return render_shots(self.p,selected)

    def test_real_encode_held_edges_shared_validation_timeline_assembly(self):
        self.render();records=validate_shot_set(self.p)
        with contextlib.redirect_stdout(io.StringIO()):
            file=timeline(self.p);movie=assemble(self.p)
        self.assertTrue(file.exists());self.assertEqual(int(probe(movie)['streams'][0]['nb_frames']),6)
        rec=records['shots']['1'];self.assertEqual((rec['frames'],rec['sourceStart'],rec['bodyFrames']),(7,2,3))
        decoded=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(self.p.output/'shots/1-test.mp4'),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        frames=np.frombuffer(decoded,dtype=np.uint8).reshape(7,16,16,3).astype(float)
        self.assertLess(abs(frames[0]-frames[2]).mean(),1);self.assertLess(abs(frames[4]-frames[6]).mean(),1)
        self.assertGreater(abs(frames[2]-frames[3]).mean(),30)

    def test_meta_browser_mapping_and_launcher_are_part_of_identity(self):
        before=self.p.source_inventory()[0]
        meta=self.root/'motion/1/scene.meta';meta.write_text('{"cue":1}')
        self.assertNotEqual(before,self.p.source_inventory()[0]);before=self.p.source_inventory()[0]
        self.browser.return_value={'sha256':'browser-v2'}
        self.assertNotEqual(before,self.p.source_inventory()[0])
        inventory=self.p.source_inventory()[1]
        self.assertTrue(any(r['file']=='framework:motion-canvas/render.mjs' for r in inventory))

    def test_partial_changed_build_rejects_mixed_shots(self):
        self.render();(self.root/'motion/1/scene.meta').write_text('{"new":1}')
        self.render({'1'})
        with self.assertRaisesRegex(ValueError,'incomplete'):validate_shot_set(self.p)

    def test_bad_frame_sequence_preserves_prior_clip_and_manifest(self):
        self.render();file=self.p.output/'shots/1-test.mp4';manifest=self.p.output/'shots.json';before=(sha(file),sha(manifest))
        def missing(p,project,work,count,start=0):
            self.fake_body(p,project,work,count,start);(work/'frames/000001.png').unlink()
        with patch('sbph.motion_shots.export_body',side_effect=missing):
            with self.assertRaisesRegex(RuntimeError,'Incomplete'):render_shots(self.p,{'1'})
        self.assertEqual(before,(sha(file),sha(manifest)))

    def test_explicit_shared_project_windows_and_invalid_maps(self):
        project=self.config['motion_shots']['1']
        self.config['motion_shots']={'1':{'project':project,'startFrame':0},'2':{'project':project,'startFrame':3}}
        self.fixture.save();self.p=Project.load(self.p.config);self.render();self.assertEqual(len(validate_shot_set(self.p)['shots']),2)
        for mapping in [{'1':project},{'1':project,'2':project},{'1':{'project':project,'startFrame':True},'2':project}]:
            self.config['motion_shots']=mapping;self.fixture.save()
            with self.assertRaises(ValueError):motion_projects(Project.load(self.p.config))

    def test_renderer_uses_temporary_source_copy_and_explicit_window(self):
        project=motion_projects(self.p)['1'];meta=project.parent/'scene.meta';before=meta.read_bytes()
        work=self.root/'work';work.mkdir();calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if args[2]=='render':
                copied=Path(args[3]);(copied.parent/'scene.meta').write_text('renderer cache')
                return subprocess.CompletedProcess(args,0,stdout='{"result":0,"errors":[]}\n',stderr='')
            return subprocess.CompletedProcess(args,0)
        with patch('sbph.motion_shots.run_native',side_effect=run):export_body(self.p,project,work,3,9)
        self.assertEqual(meta.read_bytes(),before)
        self.assertEqual(json.loads(calls[-1][-1])['startFrame'],9)
        self.assertNotEqual(Path(calls[-1][3]),project)

    def test_renderer_canonicalizes_symlinked_source_and_work_roots(self):
        alias=self.root/'native-path-alias';alias.symlink_to(self.root.resolve(),target_is_directory=True)
        project=alias/'motion/1/project.ts';meta=project.parent/'scene.meta';before=meta.read_bytes()
        work=alias/'aliased-work';work.mkdir();calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if args[2]=='render':
                copied=Path(args[3]);self.assertEqual(copied.parent,work.resolve()/'source')
                (copied.parent/'scene.meta').write_text('renderer cache')
                return subprocess.CompletedProcess(args,0,stdout='{"result":0,"errors":[]}\n',stderr='')
            return subprocess.CompletedProcess(args,0)
        with patch('sbph.motion_shots.run_native',side_effect=run):export_body(self.p,project,work,3,9)
        self.assertEqual(meta.read_bytes(),before);self.assertEqual(Path(calls[-1][4]),work.resolve())
        self.assertEqual(json.loads(calls[-1][-1])['startFrame'],9)

    def test_source_inventory_symlink_escape_is_rejected_before_copy_or_render(self):
        project=motion_projects(self.p)['1'];outside=self.root/'outside-native.ts';outside.write_text('unmanaged source')
        (project.parent/'escaping.ts').symlink_to(outside.resolve())
        work=self.root/'rejected-work';work.mkdir()
        with patch('sbph.motion_shots.run_native') as runner:
            with self.assertRaises(ValueError):export_body(self.p,project,work,3,9)
        runner.assert_not_called();self.assertFalse((work/'source').exists())
        self.assertEqual(outside.read_text(),'unmanaged source')


if __name__=='__main__':unittest.main()
