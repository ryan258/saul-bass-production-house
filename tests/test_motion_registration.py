"""Small native-plan registrations; no Unit 9 files or browser required."""
from pathlib import Path
import contextlib,copy,io,json,shutil,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from sbph.project import Project,dump,sha
from sbph.motion_registration import register,validate_registration,isolate_registered_body,main
from sbph.motion_shots import export_body
from sbph.shot_backend import motion_projects
from sbph.unit9_run import select


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
        with patch('sbph.motion_shots.run_native',side_effect=run):export_body(p,self.source/'project.ts',work,45,45)
        self.assertEqual(options[0]['startFrame'],0)
        self.assertEqual([f.name for f in sorted((work/'frames').glob('*.png'))],[f'{i:06}.png' for i in range(45,90)])

    def test_isolation_rejects_a_window_crossing_a_registered_cut(self):
        self.create();p=Project.load(self.config);copied=self.root/'render-copy';shutil.copytree(self.source,copied)
        with self.assertRaisesRegex(ValueError,'complete native shot'):isolate_registered_body(p,copied,44,45)

    def test_computed_cue_caches_do_not_stale_semantic_registration_but_seed_does(self):
        self.meta['seed']=91230;dump(self.source/'film.meta',self.meta);self.create();before=self.config.read_bytes()
        self.meta['timeEvents']=[{**event,'initialTime':0,'offset':1,'stack':'editor cache'} for event in reversed(self.meta['timeEvents'])]
        dump(self.source/'film.meta',self.meta);validate_registration(Project.load(self.config));self.create()
        self.assertEqual(self.config.read_bytes(),before)
        self.meta['seed']=91231;dump(self.source/'film.meta',self.meta)
        with self.assertRaisesRegex(ValueError,'stale'):validate_registration(Project.load(self.config))

    def test_legacy_registration_keeps_raw_guard_until_explicit_refresh(self):
        self.create();config=json.loads(self.config.read_text());receipt=config['motion_registration']
        receipt.update(schemaVersion=1,cuesSha256=sha(self.source/'film.meta'));receipt.pop('cuesSemanticSha256');dump(self.config,config)
        before=self.config.read_bytes();self.create();self.assertEqual(self.config.read_bytes(),before)
        self.meta['timeEvents'][0]['stack']='computed cache';dump(self.source/'film.meta',self.meta)
        with self.assertRaisesRegex(ValueError,'stale'):validate_registration(Project.load(self.config))
        self.create(True);self.assertEqual(json.loads(self.config.read_text())['motion_registration']['schemaVersion'],2)

    def test_initial_and_refresh_promotion_failure_restore_both_files(self):
        replace=Path.replace
        for initial in [True,False]:
            with self.subTest(initial=initial):
                if not initial:self.create()
                before={file:file.read_bytes() for file in [self.config,self.derived] if file.exists()};failed=False
                if not initial:self.meta['timeEvents'][0]['targetTime']=46/30;dump(self.source/'film.meta',self.meta)
                def fail_config(path,destination):
                    nonlocal failed
                    if Path(destination)==self.config and path.name=='production.json' and not failed:failed=True;raise OSError('configuration replacement failed')
                    return replace(path,destination)
                with patch.object(Path,'replace',fail_config):
                    with self.assertRaisesRegex(OSError,'configuration replacement'):self.create(not initial)
                self.assertTrue(failed);self.assertEqual({file:file.read_bytes() for file in [self.config,self.derived] if file.exists()},before)

    def named_run(self,name='complete'):
        self.create();run=self.output/name;data=json.loads(self.config.read_text())
        data.update(root=str(self.config.parent/'unit-9-motion'),output=str(run),delivery=str(run/'review.mp4'),handles=7,
            timeline_file='my-edit.otio',verification={'profile':'generic','conform_first_frame_offset':0},owner_note='Keep this setting')
        data['motion_registration'].update(schemaVersion=1,cuesSha256=sha(self.source/'film.meta'));data['motion_registration'].pop('cuesSemanticSha256')
        file=run/'production.json';dump(file,data);return file

    def refresh_run(self,file,refresh=True):
        return register(self.legacy/'production.json',self.config,self.output,refresh,file)

    def test_selected_refresh_preserves_custom_settings_and_unchanged_shared_edit(self):
        selected=self.named_run();previous=selected.read_bytes();data=json.loads(previous)
        default=json.loads(self.config.read_text());default.update(handles=5,owner_note='Keep default setting');dump(self.config,default)
        unchanged=(self.derived.read_bytes(),self.derived.stat().st_mtime_ns)
        self.assertEqual(self.refresh_run(selected),selected)
        updated=json.loads(selected.read_text())
        self.assertEqual({k:v for k,v in updated.items() if k not in ['motion_registration','motion_shots']},{k:v for k,v in data.items() if k not in ['motion_registration','motion_shots']})
        self.assertEqual(updated['motion_registration']['schemaVersion'],2)
        self.assertEqual((self.derived.read_bytes(),self.derived.stat().st_mtime_ns),unchanged)
        self.assertEqual(json.loads(self.config.read_text())['owner_note'],'Keep default setting')
        self.assertEqual(json.loads(self.config.read_text())['handles'],5)
        saved=list((selected.parent/'.registration-history').glob('*.json'));self.assertEqual(len(saved),1);self.assertEqual(saved[0].read_bytes(),previous)
        validate_registration(Project.load(selected));validate_registration(Project.load(self.config))
        before={path:(path.read_bytes(),path.stat().st_mtime_ns) for path in [self.config,self.derived,selected,saved[0]]}
        self.refresh_run(selected);self.assertEqual(before,{path:(path.read_bytes(),path.stat().st_mtime_ns) for path in before})

    def test_selected_legacy_guard_requires_refresh_and_saved_cue_change_updates_both_windows(self):
        selected=self.named_run();before=selected.read_bytes();self.refresh_run(selected,False)
        self.assertEqual(selected.read_bytes(),before);self.assertEqual(json.loads(before)['motion_registration']['schemaVersion'],1)
        self.meta['timeEvents'][0]['targetTime']=46/30;dump(self.source/'film.meta',self.meta)
        with self.assertRaisesRegex(ValueError,'refresh'):self.refresh_run(selected,False)
        self.refresh_run(selected)
        for path in [self.config,selected]:
            project=Project.load(path);validate_registration(project)
            self.assertEqual(project.edit['scenes'][0]['end'],46);self.assertEqual(project.data['motion_shots']['02']['startFrame'],46)
            self.assertEqual(project.data['motion_registration']['schemaVersion'],2)

    def test_selected_promotion_failure_rolls_back_default_edit_selected_and_recovery_copy(self):
        selected=self.named_run();before={path:path.read_bytes() for path in [self.config,self.derived,selected]}
        self.meta['timeEvents'][0]['targetTime']=46/30;dump(self.source/'film.meta',self.meta)
        replace=Path.replace;failed=False
        def fail_selected(path,destination):
            nonlocal failed
            if Path(destination)==selected and path.name=='selected-production.json' and not failed:failed=True;raise OSError('selected replacement failed')
            return replace(path,destination)
        with patch.object(Path,'replace',fail_selected):
            with self.assertRaisesRegex(OSError,'selected replacement'):self.refresh_run(selected)
        self.assertTrue(failed);self.assertEqual(before,{path:path.read_bytes() for path in before})
        self.assertFalse(list((selected.parent/'.registration-history').glob('*.json')))

    def test_external_selected_setting_edit_during_planning_is_preserved(self):
        selected=self.named_run();load=Project.load;changed=False;before=(self.config.read_bytes(),self.derived.read_bytes())
        def owner_edit(path,*args,**kwargs):
            nonlocal changed
            if Path(path)==selected and not changed:
                data=json.loads(selected.read_text());data['owner_note']='Owner changed this during refresh';dump(selected,data);changed=True
            return load(path,*args,**kwargs)
        with patch('sbph.motion_registration.Project.load',side_effect=owner_edit):
            with self.assertRaisesRegex(RuntimeError,'inputs changed'):self.refresh_run(selected)
        self.assertTrue(changed);self.assertEqual(json.loads(selected.read_text())['owner_note'],'Owner changed this during refresh')
        self.assertEqual((self.config.read_bytes(),self.derived.read_bytes()),before)

    def test_changed_shared_edit_refuses_busy_sibling_writer(self):
        selected=self.named_run();sibling=self.named_run('other');before={path:path.read_bytes() for path in [self.config,self.derived,selected,sibling]}
        self.meta['timeEvents'][0]['targetTime']=46/30;dump(self.source/'film.meta',self.meta)
        # A disk lock represents a different process. This thread's own nested
        # lock is intentionally reentrant and cannot model a competing writer.
        lock=sibling.parent.parent/('.'+sibling.parent.name+'.sbph-build-lock');lock.mkdir();dump(lock/'owner.json',{'pid':99999,'command':'native render'})
        with self.assertRaisesRegex(ValueError,'locked'):self.refresh_run(selected)
        self.assertEqual(before,{path:path.read_bytes() for path in before});self.assertTrue(lock.exists())

    def test_selected_alias_is_canonical_and_redirected_sibling_or_history_is_refused(self):
        selected=self.named_run();alias=self.root/'toolkit-alias';alias.symlink_to(self.root,target_is_directory=True)
        self.assertEqual(self.refresh_run(alias/selected.relative_to(self.root)),selected)
        outside=self.root/'outside-run';outside.mkdir();sentinel=outside/'keep';sentinel.write_text('keep')
        linked=self.output/'linked';linked.symlink_to(outside,target_is_directory=True);dump(outside/'production.json',{'owner':'keep'})
        self.meta['timeEvents'][0]['targetTime']=46/30;dump(self.source/'film.meta',self.meta)
        with self.assertRaisesRegex(ValueError,'Sibling native run'):self.refresh_run(selected)
        self.assertFalse((outside.parent/('.'+outside.name+'.sbph-build-lock')).exists());linked.unlink()
        history=selected.parent/'.registration-history';shutil.rmtree(history);history.symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'recovery directory'):self.refresh_run(selected)
        self.assertEqual(sentinel.read_text(),'keep');self.assertEqual(set(path.name for path in outside.iterdir()),{'production.json','keep'})

    def test_cli_honors_saved_active_run_and_explicit_default_and_initial_default(self):
        base=self.root/'toolkit';named=base/'output/unit-9-motion-handled/complete/production.json'
        dump(named,{'renderer':'motion-canvas','root':str(base/'examples/unit-9-motion'),'output':str(named.parent)})
        with patch('sbph.motion_registration.FRAMEWORK',base),patch('sbph.motion_registration.register') as registration:
            with patch.object(sys,'argv',['motion-register','--refresh']),contextlib.redirect_stdout(io.StringIO()):main()
            self.assertEqual(registration.call_args.args[-1],base/'examples/unit-9-motion.json')
            select(base,'complete')
            for flags,expected in [([],named),(['--run','default'],base/'examples/unit-9-motion.json'),(['--run','complete'],named)]:
                with self.subTest(flags=flags),patch.object(sys,'argv',['motion-register','--refresh',*flags]),contextlib.redirect_stdout(io.StringIO()):main()
                self.assertEqual(registration.call_args.args[-1],expected)

    def test_registration_refuses_edit_parent_symlink_into_original_before_writes(self):
        folder=self.config.parent/'unit-9-motion';folder.mkdir(parents=True)
        (folder/'data').symlink_to(self.legacy/'data',target_is_directory=True);before=self.legacy_hashes()
        with self.assertRaisesRegex(ValueError,'separate'):self.create(True)
        self.assertFalse(self.config.exists());self.assertEqual(self.legacy_hashes(),before)


if __name__=='__main__':unittest.main()
