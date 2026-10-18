"""Bounded recovery checks using tiny media and temporary film trees."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_production_validation as fixtures
from sbph.media import render_shots
from sbph.project import FRAMEWORK,binary,dump,sha
from sbph.validation import validate_shot_set


class ShotResumption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProductionValidation.setUpClass()
        cls.addClassCleanup(fixtures.ProductionValidation.doClassCleanups)
        cls.blue=Path(fixtures.ProductionValidation.media.name)/'blue.mp4'
        subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=c=blue:s=16x16:r=30',
            '-frames:v','7','-c:v','libx264','-pix_fmt','yuv420p',str(cls.blue)],check=True)

    def setUp(self):
        self.fixture=fixtures.ProductionValidation()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.p=self.fixture.p
        self.manifest=self.p.output/'shots.json'

    def fake_render(self,p,destination,start,count,shot):
        shutil.copy2(self.blue,destination)
        return {'file':str(destination),'frames':count,'fps':p.fps,'sha256':sha(destination)}

    def render(self,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):return render_shots(self.p,**kwargs)

    def test_current_clips_are_verified_and_reused_without_rewriting_manifest(self):
        before=(self.manifest.read_bytes(),self.manifest.stat().st_mtime_ns)
        with patch('sbph.media.render_picture') as renderer:
            self.render(resume=True)
            renderer.assert_not_called()
        self.assertEqual(before,(self.manifest.read_bytes(),self.manifest.stat().st_mtime_ns))
        validate_shot_set(self.p)

    def test_missing_corrupt_or_bad_range_clip_is_rendered_without_repeating_good_shot(self):
        for problem in ['missing','corrupt','range','hash-matching-undecodable']:
            with self.subTest(problem=problem):
                manifest=self.fixture.make_manifest()
                movie=self.p.output/'shots/2-test.mp4'
                if problem=='missing':movie.unlink()
                elif problem in {'corrupt','hash-matching-undecodable'}:movie.write_bytes(b'corrupt clip')
                else:manifest['shots']['2']['sourceStart']=0
                if problem=='hash-matching-undecodable':manifest['shots']['2']['sha256']=sha(movie)
                dump(self.manifest,manifest)
                first=sha(self.p.output/'shots/1-test.mp4')
                with patch('sbph.media.render_picture',side_effect=self.fake_render) as renderer:
                    self.render(resume=True)
                self.assertEqual([call.args[-1] for call in renderer.call_args_list],['2'])
                self.assertEqual(first,sha(self.p.output/'shots/1-test.mp4'))
                validate_shot_set(self.p)

    def test_interrupted_run_can_resume_only_its_missing_record(self):
        manifest=json.loads(self.manifest.read_text());del manifest['shots']['2']
        dump(self.manifest,manifest)
        old=self.manifest.read_bytes()
        with patch('sbph.media.render_picture',side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError,'interrupted'):self.render(resume=True)
        self.assertEqual(old,self.manifest.read_bytes())
        with patch('sbph.media.render_picture',side_effect=self.fake_render) as renderer:self.render(resume=True)
        self.assertEqual([call.args[-1] for call in renderer.call_args_list],['2'])
        validate_shot_set(self.p)

    def test_stale_fingerprint_prevents_reuse_and_normal_render_stays_fresh(self):
        self.fixture.driver.write_text(self.fixture.driver.read_text()+'\n// new source')
        with patch('sbph.media.render_picture',side_effect=self.fake_render) as renderer:self.render(resume=True)
        self.assertEqual(renderer.call_count,2)
        validate_shot_set(self.p)
        with patch('sbph.media.render_picture',side_effect=self.fake_render) as renderer:self.render(selected={'1'})
        self.assertEqual(renderer.call_count,1)

    def test_source_change_before_promotion_preserves_previous_clip_and_manifest(self):
        movie=self.p.output/'shots/1-test.mp4';before=(sha(movie),self.manifest.read_bytes())
        def changed(*args):
            record=self.fake_render(*args)
            self.fixture.runtime.return_value={'testTools':'changed during render'}
            return record
        with patch('sbph.media.render_picture',side_effect=changed):
            with self.assertRaisesRegex(RuntimeError,'Sources changed'):self.render(selected={'1'})
        self.assertEqual(before,(sha(movie),self.manifest.read_bytes()))

    def test_failed_manifest_staging_preserves_previous_clip_and_manifest(self):
        movie=self.p.output/'shots/1-test.mp4';before=(sha(movie),self.manifest.read_bytes())
        with patch('sbph.media.render_picture',side_effect=self.fake_render),patch('sbph.media.dump',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError,'disk full'):self.render(selected={'1'})
        self.assertEqual(before,(sha(movie),self.manifest.read_bytes()))

    def test_late_source_change_during_validation_or_receipt_staging_preserves_shot(self):
        from sbph.validation import validate_shot_record
        for phase in ['validation','manifest']:
            with self.subTest(phase=phase):
                self.fixture.runtime.return_value={'testTools':'fixture'}
                self.fixture.make_manifest()
                movie=self.p.output/'shots/1-test.mp4';before=(sha(movie),self.manifest.read_bytes())
                def validate(*args,**kwargs):
                    result=validate_shot_record(*args,**kwargs)
                    self.fixture.runtime.return_value={'testTools':'changed during validation'}
                    return result
                def stage(path,record):
                    dump(path,record)
                    self.fixture.runtime.return_value={'testTools':'changed during manifest staging'}
                with patch('sbph.media.render_picture',side_effect=self.fake_render),patch(
                        'sbph.validation.validate_shot_record' if phase=='validation' else 'sbph.media.dump',
                        side_effect=validate if phase=='validation' else stage):
                    with self.assertRaisesRegex(RuntimeError,'Sources changed'):self.render(selected={'1'})
                self.assertEqual(before,(sha(movie),self.manifest.read_bytes()))

    def test_clip_replaced_during_probe_is_rejected_and_rendered_on_resume(self):
        from sbph.media import probe
        movie=self.p.output/'shots/1-test.mp4';replaced=False
        def changing_probe(file):
            nonlocal replaced
            info=probe(file)
            if Path(file)==movie and not replaced:
                replaced=True;shutil.copy2(self.blue,movie)
            return info
        with patch('sbph.media.probe',side_effect=changing_probe),patch('sbph.media.render_picture',side_effect=self.fake_render) as renderer:
            self.render(resume=True)
        self.assertTrue(replaced)
        self.assertEqual([call.args[-1] for call in renderer.call_args_list],['1'])
        validate_shot_set(self.p)

    def test_cleanup_error_after_shot_save_keeps_manifest_and_clip_valid(self):
        remove=shutil.rmtree;warnings=io.StringIO()
        def fail_cleanup(path,*args,**kwargs):
            if Path(path).name.startswith('.shot-build-'):raise OSError('cleanup permission denied')
            return remove(path,*args,**kwargs)
        with patch('sbph.media.render_picture',side_effect=self.fake_render),patch('sbph.media.shutil.rmtree',side_effect=fail_cleanup),contextlib.redirect_stderr(warnings):
            self.render(selected={'1'})
        validate_shot_set(self.p)
        retained=next(self.p.output.glob('.shot-build-*'))
        self.assertIn(str(retained.resolve()),warnings.getvalue())

    def test_failed_manifest_promotion_rolls_back_the_already_promoted_clip(self):
        movie=self.p.output/'shots/1-test.mp4';before=(sha(movie),self.manifest.read_bytes())
        replace=Path.replace
        def fail_manifest(path,destination):
            if path.name=='shots.json' and path.parent.name.startswith('.shot-build-'):
                raise OSError('manifest replacement failed')
            return replace(path,destination)
        with patch('sbph.media.render_picture',side_effect=self.fake_render),patch.object(Path,'replace',fail_manifest):
            with self.assertRaisesRegex(OSError,'manifest replacement failed'):self.render(selected={'1'})
        self.assertEqual(before,(sha(movie),self.manifest.read_bytes()))
        validate_shot_set(self.p)

    def test_cli_resume_reuses_a_real_tiny_build_and_rejects_flag_for_other_commands(self):
        environment={**os.environ,'PYTHONPATH':str(FRAMEWORK/'src')}
        def run(command,*options):
            return subprocess.run([sys.executable,'-m','sbph',command,str(self.p.config),*options],
                env=environment,capture_output=True,text=True)
        built=run('shots')
        self.assertEqual(built.returncode,0,built.stderr)
        files=[self.manifest,*sorted((self.p.output/'shots').glob('*.mp4'))]
        before={file:(sha(file),file.stat().st_mtime_ns) for file in files}
        resumed=run('shots','--resume')
        self.assertEqual(resumed.returncode,0,resumed.stderr)
        self.assertIn('0 rendered, 2 reused',resumed.stdout)
        self.assertEqual(before,{file:(sha(file),file.stat().st_mtime_ns) for file in files})
        rejected=run('status','--resume')
        self.assertEqual(rejected.returncode,2)
        self.assertIn('--resume is only valid with shots',rejected.stderr)


if __name__=='__main__':unittest.main()
