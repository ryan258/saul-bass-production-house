import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sbph import workflow as flow
from sbph.project import Project,FRAMEWORK,dump,sha
from sbph.status import snapshot
from workflow_fixtures import project,files


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.p=project(self.temp.name)

    def test_status_and_resume_are_read_only_and_work_before_audio_preparation(self):
        self.p.audio.unlink()
        with self.assertRaisesRegex(ValueError,'audio is missing'):Project.load(self.p.config)
        p=Project.load(self.p.config,require_audio=False);before=files(p.root)
        with patch('sbph.media.probe',side_effect=AssertionError('No probing during status')):
            result=snapshot(p)
        self.assertFalse(result['sourceAudioExists']);self.assertEqual(result['build']['status'],'missing')
        self.assertIn('Prepare or restore',result['nextAction']['text'])
        self.assertEqual(files(p.root),before);self.assertFalse((p.root/'.sbph').exists())

    def test_motion_canvas_status_suggests_a_shot_without_an_svg_driver(self):
        data=json.loads(self.p.config.read_text());data['renderer']='motion-canvas';self.p.config.write_text(json.dumps(data))
        self.p.driver.unlink()
        result=snapshot(Project.load(self.p.config))
        self.assertIn(' shots ',result['nextAction']['command']);self.assertNotIn('animatic',result['nextAction']['command'])

    def test_cli_reports_missing_fields_and_failed_subprocesses_without_tracebacks(self):
        env={**os.environ,'PYTHONPATH':str(FRAMEWORK/'src')}
        def run(*args):return subprocess.run([sys.executable,'-m','sbph',*args],capture_output=True,text=True,env=env)
        edit=self.p.root/'data/edit.json';data=json.loads(edit.read_text());del data['frames'];edit.write_text(json.dumps(data))
        result=run('status',str(self.p.config))
        self.assertEqual(result.returncode,1);self.assertIn('missing required field',result.stderr);self.assertNotIn('Traceback',result.stderr)
        script="import runpy,subprocess,sys;from unittest.mock import patch;sys.argv=['sbph','status','x']\n"\
            "with patch('sbph.project.Project.load',side_effect=subprocess.CalledProcessError(2,['node','x'])):runpy.run_module('sbph.__main__',run_name='__main__')"
        result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env)
        self.assertEqual(result.returncode,1);self.assertIn('command failed (2): node x',result.stderr);self.assertNotIn('Traceback',result.stderr)

    def test_timecodes_and_invalid_time_are_unambiguous(self):
        self.assertEqual(flow.parse_time('00:00:01:08',24),32)
        self.assertEqual(flow.parse_time('1:02.5',24),1500)
        self.assertEqual(flow.parse_time('48f',24),48)
        self.assertEqual(flow.timecode(32,24),'00:00:01:08')
        for value in ['-1','00:00:01:24','1:61','nan','one']:
            with self.subTest(value=value),self.assertRaises(ValueError):flow.parse_time(value,24)

    def test_notes_have_short_ids_categories_and_retained_resolution(self):
        first=flow.add_note(self.p,'Hold the bridge','bridge','34f','t')
        self.assertEqual(first['id'],'N1');self.assertEqual(first['kind'],'timing')
        self.assertEqual(first['anchor']['localFrame'],2)
        flow.resolve_note(self.p,'n1','Reviewed')
        second=flow.add_note(self.p,'Listen for the answer',at='3.5',kind='s')
        self.assertEqual(second['id'],'N2');self.assertEqual(len(flow.notes(self.p)),1)
        self.assertEqual(len(flow.notes(self.p,True)),2)
        self.assertEqual(flow.find_note(self.p,'N1')['resolution'],'Reviewed')

    def test_note_anchors_follow_moves_but_flag_rate_trim_or_deleted_shots(self):
        flow.add_note(self.p,'Contact','bridge','34f')
        bridge=flow.shot(self.p,'bridge');bridge['start']=36;bridge['end']=68
        note=flow.find_note(self.p,'N1')
        self.assertEqual(note['location']['status'],'retimed');self.assertEqual(note['location']['frame'],38)
        self.p.fps=30;self.assertEqual(flow.find_note(self.p,'N1')['location']['status'],'rate_changed')
        self.p.fps=24;bridge['end']=37
        self.assertEqual(flow.find_note(self.p,'N1')['location']['status'],'outside_shot')
        self.p.edit['scenes'].remove(bridge)
        self.assertEqual(flow.find_note(self.p,'N1')['location']['status'],'orphaned')

    def test_invalid_anchor_does_not_create_state(self):
        for arguments in [{'identifier':'missing'},{'identifier':'bridge','at':'0'},{'at':'100'}]:
            with self.subTest(arguments=arguments),self.assertRaises(ValueError):flow.add_note(self.p,'Text',**arguments)
        self.assertFalse((self.p.root/'.sbph').exists())

    def test_checkpoint_drives_resume_without_implicitly_running_a_command(self):
        flow.add_note(self.p,'Slow the reveal','bridge')
        flow.save_checkpoint(self.p,note_id='N1')
        before=files(self.p.root);result=snapshot(self.p)
        self.assertIn('--note N1',result['nextAction']['command'])
        self.assertEqual(result['nextAction']['text'],'Slow the reveal')
        self.assertEqual(files(self.p.root),before)
        flow.resolve_note(self.p,'N1')
        self.assertNotIn('--note N1',snapshot(self.p)['nextAction']['command'])

    def test_resume_suggests_a_bounded_window_for_a_long_shot(self):
        self.p.frames=1000;self.p.edit['scenes'][0]['end']=1000
        flow.save_checkpoint(self.p,identifier='approach',text='Review the opening')
        recommendation=snapshot(self.p)['nextAction']['command']
        self.assertIn('--duration 5.0',recommendation)
        self.assertIn('--start 0.0',recommendation)

    def test_reanchor_and_checkpoint_history_preserve_existing_text(self):
        flow.add_note(self.p,'Keep this text','bridge','34f')
        flow.save_checkpoint(self.p,note_id='N1')
        result=flow.reanchor_note(self.p,'N1','arrival','70f')
        self.assertEqual(result['text'],'Keep this text');self.assertEqual(result['location']['frame'],70)
        self.assertEqual(result['anchorHistory'][0]['anchor']['shotId'],'bridge')
        self.assertEqual(flow.checkpoint(self.p)['location']['frame'],70)
        flow.save_checkpoint(self.p,text='Return here tomorrow')
        self.assertEqual(len(flow.read_state(self.p,'resume')['items']),2)
        self.assertEqual(flow.checkpoint(self.p)['text'],'Return here tomorrow')
        self.assertEqual(snapshot(self.p)['nextAction']['text'],'Return here tomorrow')

    def test_intent_is_optional_mergeable_and_does_not_change_edit_or_build(self):
        config=json.loads(self.p.config.read_text());config['source_globs']=['src/**/*','data/**/*','.sbph/**/*']
        dump(self.p.config,config);self.p=Project.load(self.p.config)
        with patch('sbph.fingerprint.runtime_identity',return_value={'test':'local'}):
            fingerprint=self.p.source_inventory()[0];edit_sha=sha(self.p.root/'data/edit.json')
            flow.set_intent(self.p,'bridge',{'goal':'Connect the track'})
            intent=flow.set_intent(self.p,'bridge',{'change':'The crossing becomes possible'})
            flow.add_note(self.p,'Hold','bridge');flow.save_checkpoint(self.p,identifier='bridge')
            self.assertEqual(intent['fields']['goal'],'Connect the track')
            self.assertEqual(sha(self.p.root/'data/edit.json'),edit_sha)
            self.assertEqual(self.p.source_inventory()[0],fingerprint)

    def test_corrupt_records_and_lock_are_preserved(self):
        flow.add_note(self.p,'First','bridge')
        file=flow.state_path(self.p,'notes');file.write_text('{broken')
        before=file.read_bytes()
        self.assertTrue(snapshot(self.p)['errors'])
        with self.assertRaises(ValueError):flow.add_note(self.p,'Second','bridge')
        self.assertEqual(file.read_bytes(),before)
        lock=self.p.root/'.sbph/.write.lock';lock.write_text('owner')
        with self.assertRaisesRegex(ValueError,'holds'):flow.set_intent(self.p,'bridge',{'goal':'Connect'})
        self.assertEqual(lock.read_text(),'owner')

    def test_status_distinguishes_legacy_freshness_from_production_validation(self):
        self.p.output.mkdir();dump(self.p.output/'shots.json',{'shots':{}})
        self.assertEqual(snapshot(self.p)['build']['status'],'legacy')
        with patch('sbph.fingerprint.runtime_identity',return_value={'test':'local'}):
            fingerprint=self.p.source_inventory()[0];records={}
            (self.p.output/'shots').mkdir()
            for scene in self.p.edit['scenes']:
                file=self.p.output/'shots'/f"{scene['id']}-{scene['kind']}.mp4";file.write_bytes(b'fixture, not probed')
                records[scene['id']]={'sha256':sha(file)}
            dump(self.p.output/'shots.json',{'schemaVersion':2,'sourceFingerprint':fingerprint,'shots':records})
            result=snapshot(self.p)['build']
            self.assertEqual(result['status'],'matches');self.assertEqual(result['productionValidation'],'not run')
            file.write_bytes(b'changed');self.assertEqual(snapshot(self.p)['build']['status'],'changed')
            self.p.driver.write_text('// changed');self.assertEqual(snapshot(self.p)['build']['status'],'stale')

    def test_cli_checkpoint_note_resolve_and_json_use_the_example_launcher(self):
        env={**os.environ,'SBPH_HOME':str(FRAMEWORK),'PYTHONDONTWRITEBYTECODE':'1'}
        def run(*arguments):
            return json.loads(subprocess.check_output([str(self.p.root/'make'),*arguments,'--json'],env=env,text=True))
        run('resume','--shot','bridge','--text','Review the pause')
        note=run('note','--text','Try a longer hold','--kind','t')
        self.assertEqual(note['anchor']['shotId'],'bridge')
        self.assertEqual(run('notes')[0]['id'],'N1')
        self.assertEqual(run('resolve','--note','N1')['status'],'resolved')
        before=files(self.p.root);run('resume');run('status');self.assertEqual(files(self.p.root),before)


if __name__=='__main__':unittest.main()
