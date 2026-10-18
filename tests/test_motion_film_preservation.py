"""Standalone native-film recovery, using temporary fixtures and tiny media."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import ffmpeg
from PIL import Image

from sbph import motion_film as film
from sbph.project import dump,sha


class MotionFilmPreservation(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();native=self.root/'native';native.mkdir()
        self.project=native/'project.ts';self.project.write_text('fixture source')
        (native/'audio.wav').write_bytes(b'original recording')
        self.audio=self.root/'audio.wav';shutil.copy2(native/'audio.wav',self.audio)
        self.baseline=self.root/'baseline.mp4';self.baseline.write_bytes(b'baseline movie')
        self.spec={'frames':60,'fps':30,'width':16,'height':16,'scene':'film'}
        self.plan={'frames':60,'fps':30,'sourceAudioSha256':sha(self.audio),'scenes':[
            {'id':key,'start':start,'end':start+30,'name':'Fixture','animations':[],'accents':[]}
            for key,start in [('01',0),('02',30)]]}
        dump(native/'proof.json',self.spec);dump(native/'edit.json',self.plan)
        dump(native/'film.meta',{'timeEvents':[{'name':'cut-02','targetTime':1},{'name':'cut-end','targetTime':2}]})
        self.p=SimpleNamespace(root=self.root,output=self.root/'production',audio=self.audio,
            data={'motion_canvas_full':'native/project.ts','motion_full_baseline':'baseline.mp4'},public_path=lambda path:Path(path))
        self.out=self.p.output/'motion-canvas-full';self.out.mkdir(parents=True)
        self.final=self.out/'unit-9-motion-canvas-v01.mp4';self.cache=self.out/'chunks.json'
        for path in [self.final,self.out/'verification.json',self.out/'effective-edit.json',self.out/'decoded-shots-01.jpg',self.out/'decoded-shots-02.jpg']:
            path.write_bytes(b'previous '+path.name.encode())
        (self.out/'source-frames').mkdir();(self.out/'source-frames/old.png').write_bytes(b'previous source frame')
        self.before=self.delivery_snapshot();self.fingerprint='current identity'
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('sbph.motion_film.binary',return_value='node'))
        self.stack.enter_context(patch('sbph.motion_film.subprocess.run',return_value=subprocess.CompletedProcess([],0)))
        self.stack.enter_context(patch('sbph.motion_film.inventory',side_effect=lambda project:(self.fingerprint,[{'file':'project.ts','sha256':'fixture'}])))
        self.stack.enter_context(patch('sbph.motion_film.verify_audio_window',return_value='window hash'))
        self.renderer=self.stack.enter_context(patch('sbph.motion_film.render',side_effect=self.render))
        self.encoder=self.stack.enter_context(patch('sbph.motion_film.encode',side_effect=self.encode))
        self.check=self.stack.enter_context(patch('sbph.motion_film.check_video',return_value={}))
        self.mux=self.stack.enter_context(patch('sbph.motion_film._run_ffmpeg',side_effect=self.mux_movie))
        self.pcm=self.stack.enter_context(patch('sbph.motion_film.pcm',return_value=b'original PCM'))
        self.sheets=self.stack.enter_context(patch('sbph.motion_film.contact_sheets',side_effect=self.contact_sheets))
        self.quality=self.stack.enter_context(patch('sbph.motion_film.quality_checks',return_value=[]))

    def delivery_snapshot(self):
        paths=[self.final,self.out/'verification.json',self.out/'effective-edit.json',*self.out.glob('decoded-shots-*.jpg'),*(self.out/'source-frames').glob('*')]
        return {str(path.relative_to(self.out)):path.read_bytes() for path in paths}

    def render(self,project,work,start,count):
        self.assertNotEqual(project,self.project)
        self.assertEqual(project.read_text(),'fixture source')
        (work/'frames').mkdir()
        for frame in range(start,start+count):Image.new('RGB',(16,16),'red').save(work/'frames'/f'{frame:06}.png')
        return {'result':0,'errors':[],'cutAudit':{s['id']:s['start'] for s in self.plan['scenes'] if s['start']<start+count},'renderSeconds':.1}

    def encode(self,work,output,start,count,*settings):output.write_bytes(f'new chunk {start} {self.fingerprint}'.encode())

    def mux_movie(self,graph):
        output=Path([arg for arg in ffmpeg.compile(graph) if arg.endswith('.mp4')][-1])
        output.write_bytes(b'new movie generation')

    def contact_sheets(self,movie,plan,out):
        (out/'decoded-shots-01.jpg').write_bytes(b'new decoded sheet')
        return [{'shot':s['id'],'frame':(s['start']+s['end']-1)//2} for s in plan['scenes']]

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):return film.build(self.p,chunk_frames=30)

    def assert_previous_delivery(self):
        self.assertEqual(self.delivery_snapshot(),self.before)
        self.assertFalse(list(self.out.glob('.motion-film-*')))

    def test_success_promotes_one_complete_generation_and_removes_obsolete_sheet(self):
        self.assertEqual(self.build(),self.final)
        self.assertEqual(self.final.read_bytes(),b'new movie generation')
        self.assertEqual(set(path.name for path in (self.out/'source-frames').iterdir()),{'000000.png','000059.png'})
        self.assertFalse((self.out/'decoded-shots-02.jpg').exists())
        report=json.loads((self.out/'verification.json').read_text())
        self.assertEqual(report['file'],str(self.final));self.assertEqual(report['sha256'],sha(self.final))
        self.assertEqual(report['humanScreening'],'not recorded for this build')
        for row in report['artifacts']:self.assertEqual(sha(self.out/row['file']),row['sha256'])
        self.assertEqual(json.loads((self.out/'effective-edit.json').read_text()),self.plan)
        self.assertEqual(self.project.read_text(),'fixture source')

    def test_delivery_checks_and_receipt_failure_preserve_previous_generation(self):
        for failure in ['mux','metadata','audio','sheets','quality','source','receipt']:
            with self.subTest(failure=failure):
                with contextlib.ExitStack() as stack:
                    if failure=='mux':stack.enter_context(patch('sbph.motion_film._run_ffmpeg',side_effect=RuntimeError('mux')))
                    elif failure=='metadata':stack.enter_context(patch('sbph.motion_film.check_video',side_effect=RuntimeError('metadata')))
                    elif failure=='audio':self.pcm.side_effect=lambda path:b'baseline' if path==self.baseline else b'changed'
                    elif failure=='sheets':stack.enter_context(patch('sbph.motion_film.contact_sheets',side_effect=RuntimeError('sheets')))
                    elif failure=='quality':stack.enter_context(patch('sbph.motion_film.quality_checks',side_effect=RuntimeError('quality')))
                    elif failure=='source':stack.enter_context(patch('sbph.motion_film.quality_checks',side_effect=lambda *args:setattr(self,'fingerprint','changed during QA') or []))
                    else:
                        def write(path,data):
                            if path.name=='verification.json':raise OSError('receipt')
                            dump(path,data)
                        stack.enter_context(patch('sbph.motion_film.dump',side_effect=write))
                    with self.assertRaises((RuntimeError,OSError)):self.build()
                self.pcm.side_effect=None;self.fingerprint='current identity';self.assert_previous_delivery()

    def test_failed_later_section_keeps_verified_progress_and_resumes(self):
        def interrupted(project,work,start,count):
            if start==30:raise KeyboardInterrupt()
            return self.render(project,work,start,count)
        self.renderer.side_effect=interrupted
        with self.assertRaises(KeyboardInterrupt):self.build()
        self.assert_previous_delivery()
        self.assertEqual(set(json.loads(self.cache.read_text())['chunks']),{'0'})
        self.assertTrue((self.out/'chunks/000.source-frames/000000.png').exists())
        self.renderer.side_effect=self.render;self.renderer.reset_mock();self.build()
        self.assertEqual([call.args[2] for call in self.renderer.call_args_list],[30])

    def test_encoder_and_cache_write_failures_preserve_prior_chunk_and_cache(self):
        self.build();before=(self.out/'chunks/000.mp4').read_bytes(),self.cache.read_bytes()
        for failure in ['encoder','cache-write']:
            with self.subTest(failure=failure):
                self.fingerprint='changed source identity'
                with contextlib.ExitStack() as stack:
                    if failure=='encoder':
                        def fail_encode(work,output,*args):output.write_bytes(b'partial candidate');raise RuntimeError('encoder failed')
                        stack.enter_context(patch('sbph.motion_film.encode',side_effect=fail_encode))
                    else:
                        def fail_cache(path,data):
                            if path.name=='chunks.json':raise OSError('cache write failed')
                            dump(path,data)
                        stack.enter_context(patch('sbph.motion_film.dump',side_effect=fail_cache))
                    with self.assertRaises((RuntimeError,OSError)):self.build()
                self.assertEqual(((self.out/'chunks/000.mp4').read_bytes(),self.cache.read_bytes()),before)

    def test_chunk_cache_promotion_failure_rolls_back_chunk_and_evidence(self):
        self.build();before={str(path.relative_to(self.out)):path.read_bytes() for path in [self.cache,self.out/'chunks/000.mp4',self.out/'chunks/000.source-frames/000000.png']}
        self.fingerprint='changed source identity';replace=Path.replace;failed=False
        def fail_cache(path,destination):
            nonlocal failed
            if Path(destination)==self.cache and path.name=='chunks.json' and not failed:
                failed=True;raise OSError('cache replacement failed')
            return replace(path,destination)
        with patch.object(Path,'replace',fail_cache):
            with self.assertRaisesRegex(OSError,'cache replacement'):self.build()
        self.assertTrue(failed)
        self.assertEqual({name:(self.out/name).read_bytes() for name in before},before)

    def test_final_receipt_promotion_failure_rolls_back_all_delivery_artifacts(self):
        replace=Path.replace
        for error in [OSError('delivery receipt replacement failed'),KeyboardInterrupt()]:
            with self.subTest(error=type(error).__name__):
                failed=False
                def fail_receipt(path,destination):
                    nonlocal failed
                    if Path(destination)==self.out/'verification.json' and path.name=='verification.json' and not failed:
                        failed=True;raise error
                    return replace(path,destination)
                with patch.object(Path,'replace',fail_receipt):
                    with self.assertRaises(type(error)):self.build()
                self.assertTrue(failed);self.assert_previous_delivery()

    def test_late_sheet_promotion_failure_restores_replaced_qa_and_old_sheets(self):
        replace=Path.replace;failed=False
        def fail_sheet(path,destination):
            nonlocal failed
            if Path(destination)==self.out/'decoded-shots-01.jpg' and not failed:
                failed=True;raise OSError('late sheet replacement failed')
            return replace(path,destination)
        with patch.object(Path,'replace',fail_sheet):
            with self.assertRaisesRegex(OSError,'late sheet'):self.build()
        self.assertTrue(failed);self.assert_previous_delivery()

    def test_source_change_before_chunk_promotion_preserves_clip_and_cache(self):
        self.build();before=(self.out/'chunks/000.mp4').read_bytes(),self.cache.read_bytes()
        self.check.side_effect=lambda file,*args,**kwargs:(_ for _ in ()).throw(RuntimeError('rerender requested')) if file==self.out/'chunks/000.mp4' else None
        def changed(project,work,start,count):
            result=self.render(project,work,start,count);self.fingerprint='changed during render';return result
        self.renderer.side_effect=changed
        with self.assertRaisesRegex(RuntimeError,'changed during render'):self.build()
        self.assertEqual(((self.out/'chunks/000.mp4').read_bytes(),self.cache.read_bytes()),before)

    def test_source_change_while_staging_chunk_receipt_preserves_clip_and_cache(self):
        self.build();before=(self.out/'chunks/000.mp4').read_bytes(),self.cache.read_bytes();delivery=self.delivery_snapshot()
        self.fingerprint='updated source identity'
        def changed_during_receipt(path,data):
            dump(path,data)
            if path.name=='chunks.json':self.fingerprint='changed while staging receipt'
        with patch('sbph.motion_film.dump',side_effect=changed_during_receipt):
            with self.assertRaisesRegex(RuntimeError,'changed during render'):self.build()
        self.assertEqual(((self.out/'chunks/000.mp4').read_bytes(),self.cache.read_bytes()),before)
        self.assertEqual(self.delivery_snapshot(),delivery)

    def test_resume_rerenders_clip_changed_during_probe_or_qa_check(self):
        self.build();file=self.out/'chunks/000.mp4';qa_records=film._qa_records
        for phase in ['probe','qa']:
            with self.subTest(phase=phase):
                changed=False
                def mutate():
                    nonlocal changed
                    changed=True;file.write_bytes(b'clip changed while checking cache')
                def probe(path,*args,**kwargs):
                    if path==file:mutate()
                def qa(folder,*args):
                    result=qa_records(folder,*args)
                    if folder==self.out/'chunks/000.source-frames':mutate()
                    return result
                self.renderer.reset_mock()
                with contextlib.ExitStack() as stack:
                    if phase=='probe':stack.enter_context(patch('sbph.motion_film.check_video',side_effect=probe))
                    else:stack.enter_context(patch('sbph.motion_film._qa_records',side_effect=qa))
                    self.build()
                self.assertTrue(changed)
                self.assertEqual([call.args[2] for call in self.renderer.call_args_list],[0])
                self.assertEqual(sha(file),json.loads(self.cache.read_text())['chunks']['0']['sha256'])

    def test_resume_rechecks_metadata_and_source_frame_evidence(self):
        self.build()
        for failure in ['metadata','missing-evidence','changed-evidence']:
            with self.subTest(failure=failure):
                if failure=='metadata':
                    def check(file,*args,**kwargs):
                        if file==self.out/'chunks/001.mp4':raise RuntimeError('old chunk has wrong metadata')
                    self.check.side_effect=check
                elif failure=='missing-evidence':(self.out/'chunks/001.source-frames/000059.png').unlink()
                else:(self.out/'chunks/001.source-frames/000059.png').write_bytes(b'changed source evidence')
                self.renderer.reset_mock();self.build();self.check.side_effect=None
                self.assertEqual([call.args[2] for call in self.renderer.call_args_list],[30])

    def test_tool_and_chunk_size_identity_prevent_silent_reuse(self):
        self.build();self.renderer.reset_mock();self.fingerprint='changed browser or tool identity';self.build()
        self.assertEqual([call.args[2] for call in self.renderer.call_args_list],[0,30])
        self.renderer.reset_mock()
        with contextlib.redirect_stdout(io.StringIO()):film.build(self.p,chunk_frames=60)
        self.assertEqual([call.args[2] for call in self.renderer.call_args_list],[0])
        self.assertEqual(set(json.loads(self.cache.read_text())['chunks']),{'0'})

    def test_source_output_overlap_fails_before_scratch_or_copy(self):
        self.p.output=self.project.parent/'production'
        with patch('sbph.motion_film.shutil.copytree') as copy:
            with self.assertRaisesRegex(ValueError,'must not overlap'):self.build()
        copy.assert_not_called();self.assertFalse(self.p.output.exists())

    def test_baseline_and_audio_aliases_to_managed_outputs_fail_before_changes(self):
        for path in [self.final,self.out/'source-frames/old.png',self.out/'decoded-shots-02.jpg',self.out/'chunks/000.mp4']:
            for role in ['baseline','audio']:
                with self.subTest(path=path.relative_to(self.out),role=role):
                    original_audio=self.p.audio
                    self.p.data['motion_full_baseline']=str(path if role=='baseline' else self.baseline)
                    if role=='audio':self.p.audio=path
                    with patch('sbph.motion_film.shutil.copytree') as copy:
                        with self.assertRaisesRegex(ValueError,'outside managed output'):self.build()
                    copy.assert_not_called();self.renderer.assert_not_called();self.assert_previous_delivery()
                    self.p.audio=original_audio
        self.assertFalse((self.out/'chunks').exists());self.assertFalse(self.cache.exists())

    def test_chunk_directory_symlink_cannot_redirect_writes_into_source(self):
        chunks=self.out/'chunks';chunks.symlink_to(self.project.parent,target_is_directory=True)
        sources={path.name:path.read_bytes() for path in self.project.parent.iterdir() if path.is_file()}
        with patch('sbph.motion_film.shutil.copytree') as copy:
            with self.assertRaisesRegex(ValueError,'chunk directory must not be a symlink'):self.build()
        copy.assert_not_called();self.renderer.assert_not_called();self.assert_previous_delivery()
        self.assertEqual({path.name:path.read_bytes() for path in self.project.parent.iterdir() if path.is_file()},sources)

    def test_outer_scratch_cleanup_error_does_not_invalidate_promoted_delivery(self):
        remove=shutil.rmtree
        for error in [OSError('scratch cleanup denied'),KeyboardInterrupt()]:
            with self.subTest(error=type(error).__name__):
                exercised=False;warnings=io.StringIO()
                def cleanup(path,*args,**kwargs):
                    nonlocal exercised
                    if Path(path).name.startswith('.motion-film-'):
                        exercised=True;raise error
                    return remove(path,*args,**kwargs)
                with patch('sbph.media.shutil.rmtree',side_effect=cleanup),contextlib.redirect_stderr(warnings):result=self.build()
                self.assertTrue(exercised);self.assertEqual(result,self.final)
                self.assertIn('Temporary render work retained:',warnings.getvalue())
                self.assertEqual(self.final.read_bytes(),b'new movie generation')
                report=json.loads((self.out/'verification.json').read_text())
                self.assertEqual(report['sha256'],sha(self.final))


class TinyNativeMedia(unittest.TestCase):
    def test_real_encoded_chunk_resumption_checks_metadata_hash_and_qa(self):
        with tempfile.TemporaryDirectory() as temporary:
            work=Path(temporary);frames=work/'frames';frames.mkdir();qa=work/'qa';qa.mkdir()
            for frame in range(30):Image.new('RGB',(16,16),'red').save(frames/f'{frame:06}.png')
            movie=work/'candidate.mp4';film.encode(work,movie,0,30,30,16,16)
            for frame in [0,29]:shutil.copy2(frames/f'{frame:06}.png',qa/f'{frame:06}.png')
            spec={'frames':30,'fps':30,'width':16,'height':16}
            row={'start':0,'frames':30,'fps':30,'width':16,'height':16,'sha256':sha(movie),'cutAudit':{'one':0},'sourceFrames':film._qa_records(qa,{0,29},(16,16))}
            self.assertTrue(film._reusable_chunk(row,movie,qa,0,30,spec,{0,29},{'one':0}))
            self.assertFalse(film._reusable_chunk(row|{'width':32},movie,qa,0,30,spec|{'width':32},{0,29},{'one':0}))
            movie.write_bytes(movie.read_bytes()+b'changed')
            self.assertFalse(film._reusable_chunk(row,movie,qa,0,30,spec,{0,29},{'one':0}))

    def test_browser_and_tool_identity_are_part_of_actual_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'project.ts';project.write_text('fixture source')
            with patch('sbph.motion_film.runtime_identity',return_value={'tool':'v1'}) as tools,patch('sbph.motion_film.browser_identity',return_value={'browser':'v1'}) as browser:
                first=film.inventory(project)[0];browser.return_value={'browser':'v2'}
                self.assertNotEqual(first,film.inventory(project)[0]);first=film.inventory(project)[0]
                tools.return_value={'tool':'v2'};self.assertNotEqual(first,film.inventory(project)[0])

    def test_scene_metadata_keeps_seed_and_render_inputs_but_ignores_computed_event_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'project.ts';project.write_text('fixture source');meta=project.parent/'film.meta'
            original={'version':1,'seed':91230,'timeEvents':[{'name':'start','targetTime':.1},{'name':'end','targetTime':1}],
                'customRenderSetting':{'contrast':1}}
            dump(meta,original)
            with patch('sbph.motion_film.runtime_identity',return_value={'tool':'v1'}),patch('sbph.motion_film.browser_identity',return_value={'browser':'v1'}):
                first=film.inventory(project)[0]
                cached={**original,'timeEvents':[{**event,'initialTime':0,'offset':event['targetTime'],'stack':'recomputed renderer stack'} for event in reversed(original['timeEvents'])]}
                dump(meta,cached);self.assertEqual(first,film.inventory(project)[0])
                for field,value in [('seed',91231),('version',2),('customRenderSetting',{'contrast':2}),
                    ('timeEvents',[{'name':'start','targetTime':.1000000001},{'name':'end','targetTime':1}])]:
                    with self.subTest(field=field):
                        dump(meta,original|{field:value});self.assertNotEqual(first,film.inventory(project)[0])
                meta.write_text(json.dumps(original,separators=(',',':')))
                self.assertEqual(first,film.inventory(project)[0])


if __name__=='__main__':unittest.main()
