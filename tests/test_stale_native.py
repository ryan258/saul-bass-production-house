"""Read-only stale evidence and native launcher routing; no browser or render."""
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from sbph.fingerprint import digest,inventory_changes,format_inventory_changes
from sbph.project import FRAMEWORK,dump
from sbph.status import shot_build,display,delivery


def specification(data):
    return {'file':'build:specification','sha256':digest(data),'specification':data}


class StaleEvidence(unittest.TestCase):
    def test_inventory_names_files_and_nested_browser_tool_and_setting_changes(self):
        before=[{'file':'old.png','sha256':'old'},{'file':'scene.ts','sha256':'v1'},
            specification({'browser':{'path':'/old/browser','sha256':'old-browser'},
                'runtime':{'tools':{'ffmpeg':{'version':'v1'}}},'settings':{'handles':12,'old':True}})]
        after=[{'file':'new.png','sha256':'new'},{'file':'scene.ts','sha256':'v2'},
            specification({'browser':{'path':'/new/browser','sha256':'new-browser'},
                'runtime':{'tools':{'ffmpeg':{'version':'v2'}}},'settings':{'handles':8,'new':True}})]
        changes=inventory_changes(before,after)
        self.assertEqual({row['file']:row['change'] for row in changes},
            {'old.png':'removed','new.png':'added','scene.ts':'changed','build:specification':'changed'})
        fields={row['field']:row for row in changes[0]['details']}
        self.assertEqual(fields['browser.path']['before'],'/old/browser')
        self.assertEqual(fields['browser.path']['after'],'/new/browser')
        self.assertEqual(fields['settings.old']['change'],'removed')
        self.assertEqual(fields['settings.new']['change'],'added')
        text='\n'.join(format_inventory_changes(changes))
        for expected in ['Removed old.png','Added new.png','Changed scene.ts',
                'browser.path: /old/browser -> /new/browser','runtime.tools.ffmpeg.version: v1 -> v2',
                'settings.handles: 12 -> 8']:
            self.assertIn(expected,text)
        limited=format_inventory_changes(changes,limit=2)
        self.assertEqual(len(limited),3);self.assertIn('more changes',limited[-1])

    def test_missing_and_malformed_historical_inventory_is_explicit(self):
        for saved in [None,{},[{}],[{'file':'same','sha256':'a'},{'file':'same','sha256':'b'}]]:
            with self.subTest(saved=saved):
                changes=inventory_changes(saved,[])
                self.assertEqual(changes[0]['change'],'unavailable')
                self.assertIn('cannot be compared',format_inventory_changes(changes)[0])
        self.assertEqual(inventory_changes([],[]),[])

    def test_status_reports_exact_differences_without_mutating_or_probing(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            saved=[specification({'browser':{'path':'old'}})]
            current=[specification({'browser':{'path':'new'}})]
            dump(output/'shots.json',{'schemaVersion':2,'sourceFingerprint':'old','sourceInventory':saved,'shots':{}})
            before=(output/'shots.json').read_bytes()
            p=SimpleNamespace(output=output,source_inventory=lambda:('new',current))
            result=shot_build(p)
            self.assertEqual(result['status'],'stale')
            self.assertEqual(result['productionValidation'],'not run')
            self.assertEqual(result['staleChanges'][0]['details'][0]['field'],'browser.path')
            self.assertEqual((output/'shots.json').read_bytes(),before)
            data={'title':'Fixture','shots':1,'frames':24,'fps':24,
                'nextAction':{'text':'Review','command':None},'build':result,
                'delivery':{'file':'assembly.mp4','exists':False},'checkpoint':None,
                'openNotes':[],'recentDrafts':[],'errors':[]}
            self.assertIn('browser.path: old -> new',display(data))

    def test_malformed_shot_rows_are_unverified_without_changing_saved_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);movie=output/'shots/one-test.mp4'
            movie.parent.mkdir();movie.write_bytes(b'existing movie')
            p=SimpleNamespace(output=output,source_inventory=lambda:('current',[]),
                edit={'scenes':[{'id':'one','kind':'test'}]})
            for row in [None,[],'bad',7]:
                with self.subTest(row=row):
                    dump(output/'shots.json',{'schemaVersion':2,'sourceFingerprint':'current',
                        'sourceInventory':[],'shots':{'one':row}})
                    before=(output/'shots.json').read_bytes()
                    result=shot_build(p)
                    self.assertEqual(result['status'],'unverified')
                    self.assertIn('Malformed shot record: one',result['reason'])
                    self.assertEqual((output/'shots.json').read_bytes(),before)
                    self.assertEqual(movie.read_bytes(),b'existing movie')

    def test_malformed_delivery_reports_are_unreadable_without_rewriting_them(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);movie=output/'assembly.mp4';movie.write_bytes(b'existing delivery')
            p=SimpleNamespace(root=output,output=output,data={})
            for report in [None,[],{'delivery':[]},{'delivery':False},{'delivery':{}},
                    {'delivery':''},{'deliverySha256':[]}]:
                with self.subTest(report=report):
                    dump(output/'media-verification.json',report)
                    before=(output/'media-verification.json').read_bytes()
                    result=delivery(p)
                    self.assertTrue(result['verification'].startswith('unreadable report:'))
                    self.assertEqual((output/'media-verification.json').read_bytes(),before)
                    self.assertEqual(movie.read_bytes(),b'existing delivery')


class NativeLauncher(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.launcher=self.root/'unit9';shutil.copy2(FRAMEWORK/'unit9',self.launcher)
        python=self.root/'.venv/bin/python';python.parent.mkdir(parents=True);python.symlink_to(sys.executable)
        stub=self.root/'sbph'
        script='import json,sys;print(json.dumps(sys.argv[1:]))'
        stub.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -c '+shlex.quote(script)+' "$@"\n')
        stub.chmod(0o755)

    def run_launcher(self,*arguments):
        return subprocess.run([str(self.launcher),*arguments],capture_output=True,text=True)

    def make_run(self,name='complete-run',**overrides):
        folder=self.root/'output/unit-9-motion-handled'/name
        data={'renderer':'motion-canvas','root':str(self.root/'examples/unit-9-motion'),'output':str(folder)}
        data.update(overrides);dump(folder/'production.json',data)
        return folder/'production.json'

    def test_short_native_commands_preserve_arguments_and_default_target(self):
        for command in ['status','resume','note','notes','resolve','reanchor','intent','check','shots','validate','timeline','assemble','package']:
            with self.subTest(command=command):
                result=self.run_launcher('motion-'+command,'--json')
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads(result.stdout),[command,str(self.root/'examples/unit-9-motion.json'),'--json'])
        legacy=self.run_launcher('status','--json')
        self.assertEqual(json.loads(legacy.stdout),['status',str(self.root/'examples/unit-9.json'),'--json'])

    def test_explicit_named_run_is_reused_without_changing_the_default(self):
        config=self.make_run()
        before=config.read_bytes()
        result=self.run_launcher('motion-resume','--run','complete-run','--shot','31','--text','Review contact')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),['resume',str(config.resolve()),'--shot','31','--text','Review contact'])
        self.assertEqual(config.read_bytes(),before)
        result=self.run_launcher('motion-status')
        self.assertEqual(json.loads(result.stdout)[1],str(self.root/'examples/unit-9-motion.json'))

    def test_missing_unsafe_redirected_and_non_native_runs_are_refused(self):
        for arguments in [('--run',),('--run','../escape'),('--run','missing')]:
            with self.subTest(arguments=arguments):
                result=self.run_launcher('motion-status',*arguments)
                self.assertNotEqual(result.returncode,0);self.assertIn('unit9:',result.stderr)
        for overrides in [{'renderer':'svg'},{'root':str(self.root/'elsewhere')},{'output':str(self.root/'elsewhere')}]:
            with self.subTest(overrides=overrides):
                self.make_run(**overrides)
                result=self.run_launcher('motion-status','--run','complete-run')
                self.assertNotEqual(result.returncode,0);self.assertIn('native Unit 9 configuration',result.stderr)
        outside=self.root/'elsewhere';outside.mkdir()
        linked=self.root/'output/unit-9-motion-handled/linked';linked.symlink_to(outside,target_is_directory=True)
        result=self.run_launcher('motion-status','--run','linked')
        self.assertNotEqual(result.returncode,0);self.assertIn('must remain inside',result.stderr)


if __name__=='__main__':unittest.main()
