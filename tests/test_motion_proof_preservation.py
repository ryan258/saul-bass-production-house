"""Standalone proof failures preserve the whole previous delivery generation."""
import contextlib
import io
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import wave

import ffmpeg
from PIL import Image
from sbph import motion
from sbph.project import binary,dump,sha


class MotionProofPreservation(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.scene=self.root/'scene';self.scene.mkdir()
        self.project=self.scene/'project.ts';self.project.write_text('// fixture')
        dump(self.scene/'shutdown.meta',{'timeEvents':[]})
        self.audio=self.root/'original.wav';self.audio.write_bytes(b'original recording')
        (self.scene/'audio.wav').write_bytes(b'editor crop')
        self.output=self.root/'production';self.output.mkdir()
        self.baseline=self.output/'proof.mp4';self.baseline.write_bytes(b'original proof')
        dump(self.baseline.with_suffix('.json'),{'baseline':'original'})
        self.spec={'sourceStartFrame':3,'sourceStartSample':4800,'frames':6,'sourceSamples':9600,
            'fps':30,'width':16,'height':16,'cuts':[0,6],'notes':'Fixture'}
        dump(self.scene/'proof.json',self.spec)
        self.p=SimpleNamespace(root=self.root,output=self.output,audio=self.audio,
            data={'motion_canvas':'scene/project.ts'},source_inventory=Mock(return_value=('current',[])),
            public_path=lambda path:Path('/published')/Path(path).relative_to(self.output))
        self.out=self.output/'motion-canvas';self.out.mkdir()
        for name in ['unit-9-shutdown-motion-canvas.mp4','unit-9-shutdown-comparison.mp4','proof.json',
                'source-frames/old.png','render-work/frames/old.png','editor-exports/keep.txt']:
            file=self.out/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(('previous '+name).encode())
        self.old=self.visible_files();self.sources=self.source_files();self.commands=[]

    def visible_files(self):
        return {f.relative_to(self.out).as_posix():f.read_bytes() for f in self.out.rglob('*')
            if f.is_file() and not any(part.startswith('.') for part in f.relative_to(self.out).parts)}

    def source_files(self):
        return {str(f):f.read_bytes() for f in [*self.scene.rglob('*'),self.audio,self.baseline,self.baseline.with_suffix('.json')] if f.is_file()}

    def fake_run(self,command,**kwargs):
        self.commands.append(command)
        project=Path(command[3] if command[2]=='render' else command[2])
        self.assertNotEqual(project,self.project)
        if command[2]=='render':
            # Renderer-owned metadata changes must stay in the source copy.
            dump(project.parent/'shutdown.meta',{'timeEvents':[],'rendererCache':'new'})
            frames=Path(command[4])/'frames';frames.mkdir()
            for i in range(self.spec['frames']):Image.new('RGB',(16,16),'red').save(frames/f'{i:06}.png')
        return subprocess.CompletedProcess(command,0)

    def fake_encode(self,graph):
        command=ffmpeg.compile(graph)
        Path(next(arg for arg in reversed(command) if arg.endswith('.mp4'))).write_bytes(b'new encoded candidate')

    def fake_comparison(self,baseline,new,output,work,spec):output.write_bytes(b'new comparison')

    def fake_probe(self,file):
        size=(1920,600) if Path(file).name=='unit-9-shutdown-comparison.mp4' else (16,16)
        return {'streams':[{'codec_type':'video','nb_frames':'6','avg_frame_rate':'30/1',
            'width':size[0],'height':size[1],'color_primaries':'bt709','color_transfer':'iec61966-2-1',
            'color_space':'bt709','color_range':'tv'}]}

    @contextlib.contextmanager
    def patched(self,**overrides):
        values={'verify_audio_window':lambda *args:'crop','validate_baseline':lambda *args:{'verified':True},
            'browser_identity':lambda:{'fixture':'browser'},'subprocess.run':self.fake_run,
            '_run_ffmpeg':self.fake_encode,'comparison':self.fake_comparison,
            'probe':self.fake_probe,'pcm':lambda file:b'identical decoded audio'}
        values.update(overrides)
        with contextlib.ExitStack() as stack:
            for name,value in values.items():stack.enter_context(patch('sbph.motion.'+name,side_effect=value))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            yield

    def assert_previous(self):
        self.assertEqual(self.visible_files(),self.old)
        self.assertEqual(self.source_files(),self.sources)

    def test_typecheck_render_encoder_mux_and_comparison_failures_preserve_generation(self):
        for phase in ['typecheck','render','picture','mux','comparison']:
            with self.subTest(phase=phase):
                calls=0
                def run(command,**kwargs):
                    if (phase=='typecheck' and command[2]!='render') or (phase=='render' and command[2]=='render'):
                        raise subprocess.CalledProcessError(1,command)
                    return self.fake_run(command,**kwargs)
                def encode(graph):
                    nonlocal calls
                    calls+=1;self.fake_encode(graph)
                    if (phase=='picture' and calls==1) or (phase=='mux' and calls==2):raise RuntimeError('encoder failure')
                def compare(*args):
                    self.fake_comparison(*args)
                    if phase=='comparison':raise RuntimeError('comparison failure')
                with self.patched(**{'subprocess.run':run,'_run_ffmpeg':encode,'comparison':compare}):
                    with self.assertRaises((RuntimeError,subprocess.CalledProcessError)):motion.build(self.p)
                self.assert_previous()

    def test_incomplete_frames_wrong_metadata_and_changed_audio_preserve_generation(self):
        for phase in ['sequence','metadata','audio']:
            with self.subTest(phase=phase):
                def run(command,**kwargs):
                    result=self.fake_run(command,**kwargs)
                    if phase=='sequence' and command[2]=='render':(Path(command[4])/'frames/000001.png').unlink()
                    return result
                def probe(file):
                    info=self.fake_probe(file)
                    if phase=='metadata':info['streams'][0]['width']=32
                    return info
                def pcm(file):return b'different' if phase=='audio' and Path(file)!=self.baseline else b'identical decoded audio'
                with self.patched(**{'subprocess.run':run,'probe':probe,'pcm':pcm}):
                    with self.assertRaises(RuntimeError):motion.build(self.p)
                self.assert_previous()

    def test_late_framework_or_browser_changes_preserve_generation(self):
        for phase in ['framework','browser']:
            with self.subTest(phase=phase):
                def compare(*args):
                    self.fake_comparison(*args)
                    if phase=='framework':self.p.source_inventory.return_value=('changed',[])
                    else:browser.return_value={'fixture':'changed browser'}
                browser=Mock(return_value={'fixture':'browser'})
                with self.patched(comparison=compare,browser_identity=browser):
                    with self.assertRaisesRegex(RuntimeError,'configuration, framework, or tools changed'):motion.build(self.p)
                self.p.source_inventory.return_value=('current',[])
                self.assert_previous()

    def test_sampling_and_receipt_write_failures_do_not_publish_partial_artifacts(self):
        for phase in ['sampling','receipt']:
            with self.subTest(phase=phase),self.patched():
                with patch('sbph.motion.shutil.copy2' if phase=='sampling' else 'sbph.motion.dump',side_effect=OSError('disk full')):
                    with self.assertRaises(OSError):motion.build(self.p)
                self.assert_previous()

    def test_late_file_and_directory_promotion_failure_or_cancellation_restores_generation(self):
        real_replace=Path.replace
        for name in ['proof.json','source-frames','render-work']:
            for error in [OSError('promotion failed'),KeyboardInterrupt()]:
                with self.subTest(name=name,error=type(error).__name__):
                    failed=False
                    def replace(path,destination):
                        nonlocal failed
                        if Path(destination)==self.out/name and path.parent.name.startswith('.proof-build-') and not failed:
                            failed=True;raise error
                        return real_replace(path,destination)
                    with self.patched(),patch.object(Path,'replace',replace):
                        with self.assertRaises(type(error)):motion.build(self.p,keep_frames=True)
                    self.assertTrue(failed);self.assert_previous()

    def test_success_publishes_matching_receipt_samples_and_both_retention_modes(self):
        for keep_frames in [True,False]:
            with self.subTest(keep_frames=keep_frames),self.patched():output=motion.build(self.p,keep_frames=keep_frames)
            record=json.loads((self.out/'proof.json').read_text())
            self.assertEqual(record['file'],str(self.p.public_path(output)))
            self.assertEqual(record['sha256'],sha(output))
            self.assertEqual(record['comparisonSha256'],sha(self.out/'unit-9-shutdown-comparison.mp4'))
            self.assertEqual(record['retainedRenderWork'],keep_frames)
            self.assertEqual((self.out/'render-work').is_dir(),keep_frames)
            self.assertFalse((self.out/'source-frames/old.png').exists())
            self.assertEqual([r['file'] for r in record['sourceFrames']],['source-frames/000000.png','source-frames/000005.png'])
            self.assertEqual((self.out/'editor-exports/keep.txt').read_bytes(),self.old['editor-exports/keep.txt'])
            self.assertEqual(self.source_files(),self.sources)

    def test_failed_attempt_can_retry_without_replacing_older_diagnostic_work(self):
        with self.patched(comparison=Mock(side_effect=RuntimeError('comparison failed'))):
            with self.assertRaises(RuntimeError):motion.build(self.p)
        failed=list(self.out.glob('.proof-build-*'));self.assertEqual(len(failed),1)
        diagnostic={f.relative_to(failed[0]):sha(f) for f in failed[0].rglob('*') if f.is_file()}
        with self.patched():motion.build(self.p)
        self.assertEqual({f.relative_to(failed[0]):sha(f) for f in failed[0].rglob('*') if f.is_file()},diagnostic)
        self.assertEqual(self.source_files(),self.sources)

    def test_source_output_overlap_fails_before_creating_scratch(self):
        self.p.output=self.scene/'production'
        with self.patched():
            with self.assertRaisesRegex(ValueError,'separate folders'):motion.build(self.p)
        self.assertFalse(self.p.output.exists());self.assert_previous()

    def test_original_inputs_in_managed_output_paths_are_refused_before_work(self):
        for role in ['baseline','audio']:
            for relative in ['unit-9-shutdown-motion-canvas.mp4','unit-9-shutdown-comparison.mp4',
                    'proof.json','source-frames/old.png','render-work/frames/old.png']:
                with self.subTest(role=role,path=relative):
                    self.p.data.pop('motion_baseline',None);self.p.audio=self.audio
                    if role=='baseline':self.p.data['motion_baseline']=str(self.out/relative)
                    else:self.p.audio=self.out/relative
                    with self.patched(),patch('sbph.motion.shutil.copytree') as copy:
                        with self.assertRaisesRegex(ValueError,'outside managed output paths'):motion.build(self.p)
                    copy.assert_not_called();self.assertFalse(self.commands)
                    self.assertFalse(list(self.out.glob('.proof-build-*')));self.assert_previous()

    def test_cleanup_error_after_promotion_keeps_the_completed_delivery_successful(self):
        remove=shutil.rmtree
        def fail_cleanup(path,*args,**kwargs):
            if Path(path).name.startswith('.proof-build-'):raise OSError('cleanup permission denied')
            return remove(path,*args,**kwargs)
        with self.patched(),patch('sbph.motion.shutil.rmtree',side_effect=fail_cleanup):
            output=motion.build(self.p)
        record=json.loads((self.out/'proof.json').read_text())
        self.assertEqual(record['sha256'],sha(output))
        self.assertEqual(len(list(self.out.glob('.proof-build-*'))),1)
        self.assertEqual(self.source_files(),self.sources)

    def test_real_tiny_encoding_audio_and_receipt_with_substituted_native_renderer(self):
        # Source, copy, PNG encoding, stream-copy mux, PCM checks, and promotion
        # are real. Only browser export/typecheck and the visual A/B layout are substituted.
        samples=[int(9000*math.sin(2*math.pi*220*i/48000)) for i in range(19200)]
        def wav(file,values):
            with wave.open(str(file),'wb') as stream:
                stream.setparams((1,2,48000,0,'NONE','not compressed'))
                stream.writeframes(b''.join(struct.pack('<h',value) for value in values))
        wav(self.audio,samples);wav(self.scene/'audio.wav',samples[4800:14400])
        subprocess.run([binary('ffmpeg'),'-v','error','-y','-f','lavfi','-i','color=red:s=16x16:r=30',
            '-ss','0.1','-i',str(self.audio),'-frames:v','6','-t','0.2','-c:v','libx264','-c:a','aac',str(self.baseline)],check=True)
        dump(self.baseline.with_suffix('.json'),{'sha256':sha(self.baseline),'sourceStartFrame':3,'frames':6,'fps':30})
        self.sources=self.source_files()
        real_run=subprocess.run
        def run(command,**kwargs):
            if command[0]==binary('node'):return self.fake_run(command,**kwargs)
            return real_run(command,**kwargs)
        def comparison(baseline,new,output,work,spec):
            graph=ffmpeg.output(ffmpeg.input(str(new)).video.filter('scale',1920,600),
                ffmpeg.input(str(baseline)).audio,str(output),vcodec='libx264',pix_fmt='yuv420p',
                acodec='copy',t=.2,**{'bsf:v':motion.BSF},**motion.COLOR)
            motion._run_ffmpeg(graph.global_args('-hide_banner','-loglevel','error'))
        with patch('sbph.motion.subprocess.run',side_effect=run),patch('sbph.motion.browser_identity',return_value={'fixture':'browser'}),patch('sbph.motion.comparison',side_effect=comparison),contextlib.redirect_stdout(io.StringIO()):
            output=motion.build(self.p)
        record=json.loads((self.out/'proof.json').read_text())
        self.assertEqual(record['sha256'],sha(output));self.assertEqual(record['frames'],6)
        self.assertEqual(record['decodedDeliveryPcmSha256'],sha256_pcm(self.baseline))
        self.assertEqual(self.source_files(),self.sources)


def sha256_pcm(file):
    import hashlib
    return hashlib.sha256(motion.pcm(file)).hexdigest()


if __name__=='__main__':unittest.main()
