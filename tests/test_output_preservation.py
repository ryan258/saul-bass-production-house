"""Failure injection for candidate promotion; no browser or production media."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import ffmpeg

from sbph.media import assemble,mux_master,render_picture,_run_ffmpeg,_validate_video,_candidate_directory
from sbph.preview import preview


def encoded_output(graph):
    return Path([arg for arg in ffmpeg.compile(graph) if arg.endswith('.mp4')][-1])


def write_candidate(graph):
    encoded_output(graph).write_bytes(b'new encoded candidate')


class Process:
    def __init__(self,code=0,stdout=None,communicate=None):
        self.code=code;self.stdout=stdout;self.returncode=None
        self.on_communicate=communicate;self.terminated=False;self.killed=False

    def communicate(self):
        if self.on_communicate:self.on_communicate()
        self.returncode=self.code
        return None,b'fixture failure' if self.code else b''

    def poll(self):return self.returncode

    def wait(self,timeout=None):
        if self.returncode is None:self.returncode=self.code
        return self.returncode

    def terminate(self):self.terminated=True;self.returncode=-15

    def kill(self):self.killed=True;self.returncode=-9


class OutputPreservation(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.output=self.root/'production';self.output.mkdir()
        audio=self.root/'audio.wav';audio.write_bytes(b'original source audio')
        self.p=SimpleNamespace(output=self.output,audio=audio,driver=self.root/'film.cjs',
            width=16,height=16,fps=30,frames=6,data={},
            edit={'scenes':[{'id':'one','kind':'test','start':0,'end':6}]},
            public_path=lambda path:Path(path),source_inventory=Mock(return_value=('current',[])))

    def previous(self,name):
        path=self.output/name;path.write_bytes(b'previous valid output');return path

    def assert_preserved(self,path):
        self.assertEqual(path.read_bytes(),b'previous valid output')
        self.assertFalse([p for p in self.output.iterdir() if p.name.startswith('.')])

    def pipeline(self,producer_code=0,interrupted=False):
        producer=Process(producer_code,stdout=io.BytesIO(b'frames'))
        consumer=None
        def popen(command,**kwargs):
            nonlocal consumer
            if kwargs.get('stdout') is not None and kwargs.get('stdin') is None:return producer
            def complete():
                Path([a for a in command if a.endswith('.mp4')][-1]).write_bytes(b'partial encoder output')
                if interrupted:raise KeyboardInterrupt()
            consumer=Process(communicate=complete);return consumer
        return producer,lambda:consumer,patch('sbph.media.subprocess.Popen',side_effect=popen)

    def test_producer_failure_preserves_prior_clip(self):
        output=self.previous('shot.mp4');producer,consumer,pipeline=self.pipeline(producer_code=1)
        with pipeline,patch('sbph.media.binary',side_effect=lambda name:name):
            with self.assertRaisesRegex(RuntimeError,'producer/encoder'):render_picture(self.p,output,0,6)
        self.assert_preserved(output)
        self.assertIsNotNone(producer.poll());self.assertIsNotNone(consumer().poll())

    def test_cancellation_reaps_both_children_and_preserves_clip(self):
        output=self.previous('shot.mp4');producer,consumer,pipeline=self.pipeline(interrupted=True)
        with pipeline,patch('sbph.media.binary',side_effect=lambda name:name):
            with self.assertRaises(KeyboardInterrupt):render_picture(self.p,output,0,6)
        self.assertTrue(producer.terminated);self.assertTrue(consumer().terminated)
        self.assertTrue(producer.stdout.closed);self.assert_preserved(output)

    def test_tagging_and_metadata_failures_preserve_clip(self):
        for failure in ['tagging','metadata']:
            with self.subTest(failure=failure):
                output=self.previous('shot.mp4');_,_,pipeline=self.pipeline()
                encoder=Mock(side_effect=RuntimeError('tagging failed') if failure=='tagging' else write_candidate)
                validator=Mock(side_effect=RuntimeError('metadata mismatch') if failure=='metadata' else None)
                with pipeline,patch('sbph.media.binary',side_effect=lambda name:name),patch('sbph.media._run_ffmpeg',encoder),patch('sbph.media._validate_video',validator):
                    with self.assertRaises(RuntimeError):render_picture(self.p,output,0,6)
                self.assert_preserved(output)

    def test_success_promotes_only_verified_clip_and_records_final_filename(self):
        output=self.previous('shot.mp4');_,_,pipeline=self.pipeline()
        with pipeline,patch('sbph.media.binary',side_effect=lambda name:name),patch('sbph.media._run_ffmpeg',side_effect=write_candidate),patch('sbph.media._validate_video') as validate:
            record=render_picture(self.p,output,0,6)
        validate.assert_called_once()
        self.assertEqual(output.read_bytes(),b'new encoded candidate')
        self.assertEqual(record['file'],str(output))
        self.assertEqual(sorted(p.name for p in self.output.iterdir()),['shot.mp4'])

    def test_ffmpeg_helper_reaps_cancelled_process(self):
        process=Process(communicate=lambda:(_ for _ in ()).throw(KeyboardInterrupt()))
        with patch('sbph.media.subprocess.Popen',return_value=process),patch('sbph.media.binary',return_value='ffmpeg'):
            with self.assertRaises(KeyboardInterrupt):_run_ffmpeg(ffmpeg.output(ffmpeg.input('source.mp4'),'candidate.mp4'))
        self.assertTrue(process.terminated)

    def test_metadata_validator_rejects_wrong_dimensions_rate_and_audio_window(self):
        video={'codec_type':'video','nb_frames':'6','avg_frame_rate':'30/1','width':16,'height':16,
            'color_primaries':'bt709','color_transfer':'iec61966-2-1','color_space':'bt709','color_range':'tv'}
        audio={'codec_type':'audio','sample_rate':'48000','channels':2,'duration':'.2'}
        for field,value in [('width',32),('avg_frame_rate','24/1'),('color_transfer','bt709')]:
            with self.subTest(field=field),patch('sbph.media.probe',return_value={'streams':[video|{field:value}]}):
                with self.assertRaises(RuntimeError):_validate_video('fixture',self.p,6)
        with patch('sbph.media.probe',return_value={'streams':[video,audio|{'duration':'.1'}]}):
            with self.assertRaisesRegex(RuntimeError,'audio duration'):_validate_video('fixture',self.p,6,with_audio=True)

    def test_mux_metadata_and_audio_failures_preserve_previous_master(self):
        picture=self.root/'picture.mp4';picture.write_bytes(b'input picture')
        for failure in ['encoder','metadata','audio']:
            with self.subTest(failure=failure):
                output=self.previous('assembly.mp4')
                encoder=Mock(side_effect=RuntimeError('encoder') if failure=='encoder' else write_candidate)
                validator=Mock(side_effect=RuntimeError('metadata') if failure=='metadata' else None)
                audio=Mock(side_effect=ValueError('audio verification') if failure=='audio' else None)
                with patch('sbph.media._run_ffmpeg',encoder),patch('sbph.media._validate_video',validator),patch('sbph.verify.project_audio_comparison',audio):
                    with self.assertRaises((RuntimeError,ValueError)):mux_master(self.p,picture,output)
                self.assert_preserved(output)

    def test_mux_input_change_preserves_master(self):
        picture=self.root/'picture.mp4';picture.write_bytes(b'input picture');output=self.previous('assembly.mp4')
        def changed(*args,**kwargs):self.p.audio.write_bytes(b'changed source')
        with patch('sbph.media._run_ffmpeg',side_effect=write_candidate),patch('sbph.media._validate_video'),patch('sbph.verify.project_audio_comparison',side_effect=changed):
            with self.assertRaisesRegex(RuntimeError,'changed during muxing'):mux_master(self.p,picture,output)
        self.assert_preserved(output)

    def assembly_fixture(self):
        shot=self.output/'shots/one-test.mp4';shot.parent.mkdir();shot.write_bytes(b'shot media')
        from sbph.project import sha
        manifest={'sourceFingerprint':'current','shots':{'one':{'file':str(shot),'sha256':sha(shot),'sourceStart':2,'bodyFrames':6}}}
        (self.output/'shots.json').write_text('current manifest')
        return shot,manifest

    def test_assembly_source_and_media_changes_preserve_previous_master(self):
        shot,manifest=self.assembly_fixture()
        for failure in ['source','media']:
            with self.subTest(failure=failure):
                output=self.previous('assembly.mp4')
                self.p.source_inventory.return_value=('changed' if failure=='source' else 'current',[])
                def mux(p,picture,candidate):
                    candidate.write_bytes(b'new assembly')
                    if failure=='media':shot.write_bytes(b'changed shot')
                with patch('sbph.validation.validate_shot_set',return_value=manifest),patch('sbph.media._run_ffmpeg',side_effect=write_candidate),patch('sbph.media.mux_master',side_effect=mux):
                    with self.assertRaisesRegex(RuntimeError,'changed during assembly'):assemble(self.p)
                self.assert_preserved(output)

    def test_proof_failure_preserves_movie_and_receipt(self):
        for failure in ['audio','source','receipt']:
            with self.subTest(failure=failure):
                output=self.previous('proof.mp4');receipt=self.previous('proof.json')
                self.p.source_inventory.side_effect=[('current',[]),('changed' if failure=='source' else 'current',[])]
                def picture(p,path,*args):path.write_bytes(b'picture')
                audio=Mock(return_value={},side_effect=ValueError('audio') if failure=='audio' else None)
                dump=Mock(side_effect=OSError('receipt write failure'))
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch('sbph.validation.validate_edit'))
                    stack.enter_context(patch('sbph.validation.validate_source_audio'))
                    stack.enter_context(patch('sbph.preview.render_picture',side_effect=picture))
                    stack.enter_context(patch('sbph.preview._run_ffmpeg',side_effect=write_candidate))
                    stack.enter_context(patch('sbph.preview._validate_video'))
                    stack.enter_context(patch('sbph.verify.project_audio_comparison',audio))
                    if failure=='receipt':stack.enter_context(patch('sbph.preview.dump',dump))
                    with self.assertRaises((ValueError,RuntimeError,OSError)):preview(self.p,0,.2)
                self.assert_preserved(output);self.assert_preserved(receipt)

    def test_proof_receipt_promotion_failure_rolls_back_movie(self):
        output=self.previous('proof.mp4');receipt=self.previous('proof.json')
        replace=Path.replace
        for error in [OSError('receipt promotion failed'),KeyboardInterrupt()]:
            with self.subTest(error=type(error).__name__):
                failed=False
                def picture(p,path,*args):path.write_bytes(b'picture')
                def fail_receipt(path,destination):
                    nonlocal failed
                    if path.name=='proof.json' and Path(destination)==receipt and not failed:
                        failed=True;raise error
                    return replace(path,destination)
                with patch('sbph.validation.validate_edit'),patch('sbph.validation.validate_source_audio'),patch('sbph.preview.render_picture',side_effect=picture),patch('sbph.preview._run_ffmpeg',side_effect=write_candidate),patch('sbph.preview._validate_video'),patch('sbph.verify.project_audio_comparison',return_value={}),patch.object(Path,'replace',fail_receipt):
                    with self.assertRaises(type(error)):preview(self.p,0,.2)
                self.assertTrue(failed);self.assert_preserved(output);self.assert_preserved(receipt)

    def test_proof_verifies_requested_audio_window_and_records_final_path(self):
        def picture(p,path,*args):path.write_bytes(b'picture')
        with patch('sbph.validation.validate_edit'),patch('sbph.validation.validate_source_audio'),patch('sbph.preview.render_picture',side_effect=picture),patch('sbph.preview._run_ffmpeg',side_effect=write_candidate),patch('sbph.preview._validate_video'),patch('sbph.verify.project_audio_comparison',return_value={}) as audio,contextlib.redirect_stdout(io.StringIO()):
            output=preview(self.p,.1,.1)
        self.assertEqual(audio.call_args.kwargs,{'start':3,'frames':3})
        import json
        report=json.loads((self.output/'proof.json').read_text())
        self.assertEqual(report['file'],str(output))
        self.assertEqual(report['sourceStartFrame'],3);self.assertEqual(report['frames'],3)

    def test_source_change_during_proof_receipt_staging_preserves_previous_pair(self):
        from sbph.project import dump
        output=self.previous('proof.mp4');receipt=self.previous('proof.json')
        def picture(p,path,*args):path.write_bytes(b'picture')
        def stage(path,record):
            dump(path,record);self.p.source_inventory.return_value=('changed',[])
        with patch('sbph.validation.validate_edit'),patch('sbph.validation.validate_source_audio'),patch('sbph.preview.render_picture',side_effect=picture),patch('sbph.preview._run_ffmpeg',side_effect=write_candidate),patch('sbph.preview._validate_video'),patch('sbph.verify.project_audio_comparison',return_value={}),patch('sbph.preview.dump',side_effect=stage):
            with self.assertRaisesRegex(RuntimeError,'Sources changed'):preview(self.p,0,.2)
        self.assert_preserved(output);self.assert_preserved(receipt)

    def test_cleanup_failure_after_save_does_not_fail_shared_builders(self):
        _,manifest=self.assembly_fixture()
        picture=self.root/'picture.mp4';picture.write_bytes(b'input picture')
        remove=shutil.rmtree
        for mode in ['picture','mux','assembly','proof']:
            for error in [OSError('cleanup permission denied'),KeyboardInterrupt()]:
                with self.subTest(mode=mode,error=type(error).__name__):
                    output=self.previous('proof.mp4' if mode=='proof' else 'assembly.mp4')
                    warnings=io.StringIO()
                    def fail_cleanup(path,*args,**kwargs):
                        if Path(path).name.startswith('.'+mode+'-'):raise error
                        return remove(path,*args,**kwargs)
                    def render(p,path,*args):path.write_bytes(b'picture')
                    def mux(p,picture,candidate):candidate.write_bytes(b'new assembly')
                    with contextlib.ExitStack() as stack:
                        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                        stack.enter_context(contextlib.redirect_stderr(warnings))
                        stack.enter_context(patch('sbph.media.shutil.rmtree',side_effect=fail_cleanup))
                        stack.enter_context(patch('sbph.media._run_ffmpeg',side_effect=write_candidate))
                        stack.enter_context(patch('sbph.media._validate_video'))
                        stack.enter_context(patch('sbph.verify.project_audio_comparison',return_value={}))
                        if mode=='picture':
                            _,_,pipeline=self.pipeline();stack.enter_context(pipeline)
                            stack.enter_context(patch('sbph.media.binary',side_effect=lambda name:name))
                            render_picture(self.p,output,0,6)
                        elif mode=='mux':mux_master(self.p,picture,output)
                        elif mode=='assembly':
                            stack.enter_context(patch('sbph.validation.validate_shot_set',return_value=manifest))
                            stack.enter_context(patch('sbph.media.mux_master',side_effect=mux))
                            assemble(self.p)
                        else:
                            stack.enter_context(patch('sbph.validation.validate_edit'))
                            stack.enter_context(patch('sbph.validation.validate_source_audio'))
                            stack.enter_context(patch('sbph.preview.render_picture',side_effect=render))
                            stack.enter_context(patch('sbph.preview._run_ffmpeg',side_effect=write_candidate))
                            stack.enter_context(patch('sbph.preview._validate_video'))
                            preview(self.p,0,.2)
                    self.assertEqual(output.read_bytes(),b'new assembly' if mode=='assembly' else b'new encoded candidate')
                    retained=next(self.output.glob('.'+mode+'-*'))
                    self.assertIn(str(retained.resolve()),warnings.getvalue())
                    remove(retained)

    def test_cleanup_failure_does_not_mask_the_original_build_error(self):
        warnings=io.StringIO()
        with patch('sbph.media.shutil.rmtree',side_effect=OSError('cleanup failed')),contextlib.redirect_stderr(warnings):
            with self.assertRaisesRegex(RuntimeError,'render failed'):
                with _candidate_directory(prefix='.fixture-',dir=self.output):raise RuntimeError('render failed')
        self.assertIn('Temporary render work retained:',warnings.getvalue())


if __name__=='__main__':unittest.main()
