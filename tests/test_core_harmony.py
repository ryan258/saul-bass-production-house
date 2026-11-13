"""Pure preflight and local writer exclusion; no production trees or encoders."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from sbph.fingerprint import source_paths
from sbph.media import output_lock,_protect_output_inputs
from sbph.project import Project,dump,shot_filename


class CoreHarmony(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name).resolve()
        self.config=self.root/'production.json'
        self.edit={'title':'Fixture','fps':30,'frames':60,'width':16,'height':16,'scenes':[
            {'id':key,'kind':'test','name':'Shot','action':'Act','start':start,'end':start+30} for key,start in [('one',0),('two',30)]]}
        self.settings={'edit':'edit.json','audio':'audio.wav','driver':'film.cjs'}
        (self.root/'audio.wav').write_bytes(b'original');(self.root/'film.cjs').write_bytes(b'driver')
        self.save()

    def save(self):dump(self.config,self.settings);dump(self.root/'edit.json',self.edit)

    def project(self):return Project.load(self.config)

    def test_rejects_ambiguous_and_case_colliding_shot_filenames(self):
        for first,second in [(('a-b','c'),('a','b-c')),(('One','test'),('one','test'))]:
            for scene,values in zip(self.edit['scenes'],[first,second]):scene.update(id=values[0],kind=values[1])
            self.save()
            with self.assertRaisesRegex(ValueError,'colliding media filenames'):self.project()
        self.assertEqual(shot_filename({'id':'one','kind':'test'}),'one-test.mp4')

    def test_invalid_configuration_edit_and_shot_shapes_have_actionable_errors(self):
        cases=[('config',[], 'configuration must be an object'),('config',{'root':[]},'root must be'),
            ('config',{'source_files':'asset.png'},'source_files must be'),('config',{'source_globs':['../*']},'relative'),
            ('edit',[],'Edit must be an object'),('edit',{'scenes':[]},'Edit requires'),
            ('edit',{**self.edit,'scenes':[None]},'shot objects'),('edit',{**self.edit,'scenes':[{}]},'requires id')]
        for target,value,message in cases:
            with self.subTest(target=target,value=value):
                self.save();dump(self.config if target=='config' else self.root/'edit.json',value)
                with self.assertRaisesRegex(ValueError,message):Project.load(self.config,require_audio=False)

    def test_deliver_root_is_relative_to_film_root(self):
        film=self.root/'film';film.mkdir()
        (film/'audio.wav').write_bytes(b'original');dump(film/'edit.json',self.edit)
        self.settings.update(root='film',deliver_root='delivered');dump(self.config,self.settings)
        self.assertEqual(self.project().deliver_root,film/'delivered')

    def test_globs_omit_generated_work_but_explicit_originals_remain_protected(self):
        self.settings['source_globs']=['**/*'];self.save();p=self.project()
        p.output.mkdir();(p.output/'assembly.mp4').write_bytes(b'generated')
        staging=self.root/'.picture-work';staging.mkdir();(staging/'candidate.mp4').write_bytes(b'temporary')
        self.assertNotIn(p.output/'assembly.mp4',source_paths(p));self.assertNotIn(staging/'candidate.mp4',source_paths(p))
        self.settings['source_files']=['production/assembly.mp4'];self.save();p=self.project()
        self.assertIn(p.output/'assembly.mp4',source_paths(p))
        with self.assertRaisesRegex(ValueError,'protected input'):_protect_output_inputs(p,[p.output/'assembly.mp4'])

    def test_native_originals_are_protected_without_hashing_or_runtime_launch(self):
        native=self.root/'native';native.mkdir();(native/'project.ts').write_text('project');(native/'asset.png').write_bytes(b'original')
        self.settings.update(renderer='motion-canvas',motion_shots={key:{'project':'native/project.ts','startFrame':start} for key,start in [('one',0),('two',30)]})
        self.save();p=self.project()
        with self.assertRaisesRegex(ValueError,'protected input'):_protect_output_inputs(p,[native/'asset.png'])

    def test_glob_aimed_directly_at_output_requires_an_explicit_original_declaration(self):
        self.settings['source_globs']=['production/**/*'];self.save()
        with self.assertRaisesRegex(ValueError,'declare intentional originals with source_files'):source_paths(self.project())

    def test_existing_filesystem_aliases_cannot_bypass_original_protection(self):
        p=self.project();hardlink=self.root/'linked-recording.wav';hardlink.hardlink_to(p.audio)
        with self.assertRaisesRegex(ValueError,'protected input'):_protect_output_inputs(p,[hardlink])
        alias=self.root/'AUDIO.WAV'
        if alias.exists() and alias.samefile(p.audio):
            with self.assertRaisesRegex(ValueError,'protected input'):_protect_output_inputs(p,[alias])

    def test_output_lock_is_nested_and_blocks_other_threads_and_manual_stale_owners(self):
        p=self.project();lock=p.output.parent/('.'+p.output.name+'.sbph-build-lock')
        with output_lock(p,'test build'):
            metadata=json.loads((lock/'owner.json').read_text());self.assertEqual(metadata['command'],'test build')
            with output_lock(p.output):self.assertTrue(lock.is_dir())
            def competing():
                with output_lock(p,'competing'):pass
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaisesRegex(ValueError,'Output is locked'):pool.submit(competing).result()
        self.assertFalse(lock.exists())
        lock.mkdir();dump(lock/'owner.json',{'pid':999999,'command':'interrupted run'})
        before=(lock/'owner.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'interrupted run'):
            with output_lock(p):pass
        self.assertEqual((lock/'owner.json').read_bytes(),before)

    def test_lock_releases_on_failure_and_symlink_aliases_share_it(self):
        p=self.project();p.output.mkdir();alias=self.root/'output-alias';alias.symlink_to(p.output,target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,'interrupted'):
            with output_lock(p):
                with output_lock(alias):raise RuntimeError('interrupted')
        with output_lock(alias):pass


if __name__=='__main__':unittest.main()
