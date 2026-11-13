"""Native audio/TypeScript preflight failures without browser or renders."""
from pathlib import Path
import json,signal,subprocess,tempfile,unittest,wave
from unittest.mock import Mock,patch
from sbph import motion_film as film
from sbph.project import FRAMEWORK,binary
from sbph.motion_runtime import run_native


class NativeAudioPreflight(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.project=self.root/'project.ts';self.project.write_text('// fixture')
        with wave.open(str(self.root/'audio.wav'),'wb') as reader:
            reader.setparams((2,2,48000,0,'NONE','not compressed'));reader.writeframes(b'\0'*48000*4)
        self.spec={'frames':30,'fps':30,'width':16,'height':16}
        self.video={'codec_type':'video','nb_frames':'30','avg_frame_rate':'30/1','width':16,'height':16,
            'color_primaries':'bt709','color_transfer':'iec61966-2-1','color_space':'bt709','color_range':'tv'}
        self.audio={'codec_type':'audio','codec_name':'aac','sample_rate':'48000','channels':2,'duration':'1.0'}
        self.baseline=self.root/'baseline.mp4'

    def baseline_check(self,video=None,audio=None):
        with patch('sbph.motion_film.probe',return_value={'streams':[video or self.video,audio or self.audio]}):
            return film.validate_baseline(self.project,self.spec,self.baseline)

    def test_same_length_baseline_is_bound_to_the_verified_wav_samples(self):
        with patch('sbph.verify.audio_comparison',return_value={'sourceSha256':'verified'}) as compare:
            result=self.baseline_check()
            compare.assert_called_once_with(self.root/'audio.wav',self.baseline)
            self.assertEqual((result['sampleRate'],result['channels']),(48000,2))
        with patch('sbph.verify.audio_comparison',side_effect=ValueError('Audio correlation failed')):
            with self.assertRaisesRegex(ValueError,'correlation'):self.baseline_check()

    def test_wrong_range_format_or_duration_fails_before_audio_comparison(self):
        for changes in [{'sample_rate':'44100'},{'channels':1},{'duration':'1.1'}]:
            with self.subTest(changes=changes),patch('sbph.verify.audio_comparison') as compare:
                with self.assertRaises(ValueError):self.baseline_check(audio=self.audio|changes)
                compare.assert_not_called()
        for changes in [{'nb_frames':'29'},{'avg_frame_rate':'24/1'},{'width':32}]:
            with self.subTest(changes=changes),patch('sbph.verify.audio_comparison') as compare:
                with self.assertRaises(ValueError):self.baseline_check(video=self.video|changes)
                compare.assert_not_called()

    def test_final_delivery_checks_audio_duration_rate_channels_and_stream_count(self):
        expected={'sampleRate':48000,'channels':2}
        for streams in [[self.video,self.audio|{'sample_rate':'44100'}],[self.video,self.audio|{'channels':1}],
            [self.video,self.audio|{'duration':'1.1'}],[self.video,self.audio,self.audio]]:
            with self.subTest(streams=streams),patch('sbph.motion_film.probe',return_value={'streams':streams}):
                with self.assertRaises(RuntimeError):film.check_video(self.baseline,30,30,(16,16),with_audio=True,audio_format=expected)


class NativeTypecheckPreflight(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.project=self.root/'project.ts';self.project.write_text('export const value:number=1;\n')
        self.config=self.root/'tsconfig.json'

    def check(self):
        return subprocess.run([binary('node'),str(FRAMEWORK/'motion-canvas/typecheck.mjs'),str(self.project)],capture_output=True,text=True)

    def test_requested_project_must_be_in_config_roots(self):
        (self.root/'other.ts').write_text('export const ignored=1;\n')
        self.config.write_text(json.dumps({'compilerOptions':{'types':[]},'files':['other.ts']}))
        result=self.check();self.assertNotEqual(result.returncode,0)
        self.assertIn('requested Motion Canvas project is not included',result.stderr)

    def test_recoverable_config_syntax_error_is_not_reported_as_success(self):
        self.config.write_text('{"compilerOptions":{"types":[]},"files":["project.ts"] "unexpected":true}')
        result=self.check();self.assertNotEqual(result.returncode,0)
        self.assertNotIn('type check passed',result.stdout)
        self.assertIn('tsconfig.json',result.stderr)


class NativeProcessLifecycle(unittest.TestCase):
    def process(self):
        process=Mock(pid=314159,returncode=0,stdin=None)
        process.communicate.return_value=('output','errors')
        return process

    def test_success_preserves_output_without_signalling_completed_process_group(self):
        process=self.process()
        with patch('sbph.motion_runtime.subprocess.Popen',return_value=process) as launch,patch('sbph.motion_runtime.os.killpg') as kill:
            result=run_native(['node','fixture'],capture_output=True,text=True,check=True)
        self.assertTrue(launch.call_args.kwargs['start_new_session']);self.assertEqual((result.stdout,result.stderr),('output','errors'))
        kill.assert_not_called();process.stdout.close.assert_called_once();process.stderr.close.assert_called_once()

    def test_interruption_terminates_isolated_group_and_preserves_original_exception(self):
        process=self.process();process.communicate.side_effect=KeyboardInterrupt()
        with patch('sbph.motion_runtime.subprocess.Popen',return_value=process),patch('sbph.motion_runtime.os.killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):run_native(['node','fixture'],capture_output=True)
        kill.assert_called_once_with(process.pid,signal.SIGTERM);process.wait.assert_called_once_with(timeout=5)
        process.stdout.close.assert_called_once();process.stderr.close.assert_called_once()

    def test_hung_native_process_escalates_after_graceful_browser_cleanup_window(self):
        process=self.process();process.communicate.side_effect=KeyboardInterrupt()
        process.wait.side_effect=[subprocess.TimeoutExpired('node',5),subprocess.TimeoutExpired('node',2),-9]
        with patch('sbph.motion_runtime.subprocess.Popen',return_value=process),patch('sbph.motion_runtime.os.killpg') as kill:
            with self.assertRaises(KeyboardInterrupt):run_native(['node','fixture'])
        self.assertEqual([call.args for call in kill.call_args_list],[(process.pid,signal.SIGTERM),(process.pid,signal.SIGINT),(process.pid,signal.SIGKILL)])

    def test_checked_failure_retains_captured_diagnostics(self):
        process=self.process();process.returncode=2
        with patch('sbph.motion_runtime.subprocess.Popen',return_value=process),patch('sbph.motion_runtime.os.killpg') as kill:
            with self.assertRaises(subprocess.CalledProcessError) as failure:run_native(['node','fixture'],capture_output=True,text=True,check=True)
        self.assertEqual((failure.exception.stdout,failure.exception.stderr),('output','errors'));kill.assert_not_called()
