"""Small native-plan registrations; no Unit 9 files or browser required."""
from pathlib import Path
import copy,json,shutil,subprocess,tempfile,unittest
from unittest.mock import patch
from sbph.project import Project,dump,sha
from sbph.motion_registration import register,validate_registration,isolate_registered_body
from sbph.motion_shots import export_body
from sbph.shot_backend import motion_projects


class MotionRegistration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.legacy=self.root/'Original film';self.legacy.mkdir();self.source=self.legacy/'motion-canvas/full-film-v01';self.source.mkdir(parents=True)
        (self.legacy/'audio.wav').write_bytes(b'original audio fixture');(self.source/'audio.wav').write_bytes(b'original audio fixture');(self.source/'project.ts').write_text('native fixture')
        self.edit={'title':'Fixture','fps':30,'frames':90,'width':16,'height':16,'sourceAudioSha256':sha(self.legacy/'audio.wav'),'scenes':[
            {'id':identifier,'start':start,'end':end,'kind':'fixture','name':'Shot '+identifier,'action':'Act','animations':[],'accents':[]} for identifier,start,end in [('01',0,45),('02',45,90)]]}
        self.meta={'timeEvents':[{'name':'cut-02','targetTime':1.5},{'name':'cut-end','targetTime':3}]}
        dump(self.source/'edit.json',self.edit);dump(self.source/'film.meta',self.meta);dump(self.source/'proof.json',{'fps':30,'frames':90,'width':16,'height':16,'scene':'film'})
        dump(self.legacy/'data/edit.json',self.edit);dump(self.legacy/'production.json',{'root':'.','audio':'audio.wav','handles':2})
        self.config=self.root/'registration/unit-9-motion.json';self.output=self.root/'New output';self.derived=self.config.parent/'unit-9-motion/data/edit.json'

    def create(self,refresh=False):
        return register(self.legacy/'production.json',self.config,self.output,refresh)

    def legacy_hashes(self):return {str(f):sha(f) for f in self.legacy.rglob('*') if f.is_file()}

    def test_registers_all_effective_windows_with_separate_outputs_and_preserves_sources(self):
        before=self.legacy_hashes();self.create();p=Project.load(self.config);validate_registration(p)
        self.assertEqual(p.output,self.output);self.assertEqual(p.audio,self.legacy/'audio.wav')
        self.assertEqual({key:value['startFrame'] for key,value in p.data['motion_shots'].items()},{'01':0,'02':45})
        self.assertEqual(set(motion_projects(p)),{'01','02'});self.assertEqual(self.legacy_hashes(),before)
        self.assertFalse(self.output.exists())

    def test_repeated_registration_is_read_only(self):
        self.create();before={f:(f.read_bytes(),f.stat().st_mtime_ns) for f in [self.config,self.derived]}
        self.create();self.assertEqual(before,{f:(f.read_bytes(),f.stat().st_mtime_ns) for f in before})

    def test_cue_change_blocks_old_windows_until_explicit_refresh(self):
        self.create();p=Project.load(self.config);old=self.config.read_bytes()
        self.meta['timeEvents'][0]['targetTime']=46/30;dump(self.source/'film.meta',self.meta)
        with self.assertRaisesRegex(ValueError,'stale'):motion_projects(p)
        with self.assertRaisesRegex(ValueError,'refresh'):self.create()
        self.assertEqual(self.config.read_bytes(),old)
        native_before=self.legacy_hashes();self.create(True);current=Project.load(self.config)
        self.assertEqual(current.edit['scenes'][0]['end'],46);self.assertEqual(current.data['motion_shots']['02']['startFrame'],46)
        validate_registration(current);self.assertEqual(self.legacy_hashes(),native_before)

    def test_tampered_mapping_or_derived_edit_is_rejected(self):
        self.create();config=json.loads(self.config.read_text());config['motion_shots']['02']['startFrame']=44;dump(self.config,config)
        with self.assertRaisesRegex(ValueError,'window'):motion_projects(Project.load(self.config))
        self.create(True);edit=json.loads(self.derived.read_text());edit['scenes'][0]['name']='Unregistered change';dump(self.derived,edit)
        with self.assertRaisesRegex(ValueError,'stale'):motion_projects(Project.load(self.config))

    def test_changed_native_audio_is_rejected_before_writing(self):
        (self.source/'audio.wav').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'original audio'):self.create()
        self.assertFalse(self.config.exists());self.assertFalse(self.derived.exists())

    def test_output_in_original_film_is_rejected_before_writing(self):
        self.output=self.legacy/'new-production'
        with self.assertRaisesRegex(ValueError,'separate'):self.create()
        self.assertFalse(self.config.exists());self.assertFalse(self.derived.exists())

    def test_refresh_refuses_unrecognized_registration(self):
        dump(self.config,{'owner':'keep'});dump(self.derived,{'owner':'keep'})
        before=(self.config.read_bytes(),self.derived.read_bytes())
        with self.assertRaisesRegex(ValueError,'unrecognized'):self.create(True)
        self.assertEqual(before,(self.config.read_bytes(),self.derived.read_bytes()))

    def test_isolation_removes_neighbor_scenes_and_rebases_only_selected_events(self):
        scene=self.edit['scenes'][1]
        scene['animations']=[{'signal':'head','startFrame':50,'endFrame':70,'startEvent':'move','endEvent':'stop'}]
        scene['pulses']=[{'frame':52,'endFrame':55,'startEvent':'hit'}];scene['accents']=[{'frame':52}]
        self.meta['timeEvents'].extend([{'name':name,'targetTime':frame/30} for name,frame in [('move',50),('stop',70),('hit',52),('unrelated',10)]])
        dump(self.source/'edit.json',self.edit);dump(self.source/'film.meta',self.meta)
        self.create();p=Project.load(self.config);before=self.legacy_hashes();original_edit=copy.deepcopy(p.edit)
        copied=self.root/'render-copy';shutil.copytree(self.source,copied)
        self.assertEqual(isolate_registered_body(p,copied,45,45),'02')
        local=json.loads((copied/'edit.json').read_text());self.assertEqual(local['frames'],45);self.assertEqual(len(local['scenes']),1)
        shot=local['scenes'][0];self.assertEqual((shot['start'],shot['end']),(0,45))
        self.assertEqual((shot['animations'][0]['startFrame'],shot['animations'][0]['endFrame']),(5,25))
        self.assertEqual((shot['pulses'][0]['frame'],shot['pulses'][0]['endFrame']),(7,10));self.assertEqual(shot['accents'][0]['frame'],7)
        events={e['name']:e['targetTime'] for e in json.loads((copied/'film.meta').read_text())['timeEvents']}
        self.assertEqual(events,{'move':5/30,'stop':25/30,'hit':7/30,'cut-end':1.5})
        self.assertEqual(before,self.legacy_hashes());self.assertEqual(p.edit,original_edit)

    def test_export_audits_isolated_shot_and_restores_global_frame_numbering(self):
        from PIL import Image
        self.create();p=Project.load(self.config);work=self.root/'work';work.mkdir();options=[]
        def run(args,**kwargs):
            if args[2]=='render':
                options.append(json.loads(args[-1]));folder=work/'frames';folder.mkdir()
                for i in range(45):Image.new('RGB',(16,16),'red').save(folder/f'{i:06}.png')
                return subprocess.CompletedProcess(args,0,stdout='{"result":0,"errors":[],"cutAudit":{"02":0}}\n',stderr='')
            return subprocess.CompletedProcess(args,0)
        with patch('sbph.motion_shots.subprocess.run',side_effect=run):export_body(p,self.source/'project.ts',work,45,45)
        self.assertEqual(options[0]['startFrame'],0)
        self.assertEqual([f.name for f in sorted((work/'frames').glob('*.png'))],[f'{i:06}.png' for i in range(45,90)])

    def test_isolation_rejects_a_window_crossing_a_registered_cut(self):
        self.create();p=Project.load(self.config);copied=self.root/'render-copy';shutil.copytree(self.source,copied)
        with self.assertRaisesRegex(ValueError,'complete native shot'):isolate_registered_body(p,copied,44,45)


if __name__=='__main__':unittest.main()
