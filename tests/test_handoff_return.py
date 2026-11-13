"""Real collected-media relocation and synthetic human edits; never touch Unit 9."""
from pathlib import Path
import contextlib,io,json,shutil,tempfile,unittest
from unittest.mock import patch
import opentimelineio as otio
import test_production_validation as fixtures
from sbph.project import dump,sha
from sbph.handoff import package,check_package
from sbph.editor_return import compare
from sbph.workflow import add_note,set_intent

RT=otio.opentime.RationalTime;TR=otio.opentime.TimeRange


class HandoffReturn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProductionValidation.setUpClass()
        cls.addClassCleanup(fixtures.ProductionValidation.doClassCleanups)

    def setUp(self):
        self.fixture=fixtures.ProductionValidation();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.p=self.fixture.p
        # Both fixture media files intentionally have identical bytes; identity
        # must retain shot IDs, and stripped metadata must be called ambiguous.
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)/'handoff with spaces'

    def collect(self):
        return package(self.p,self.folder)

    def returned(self,change=lambda tl:None):
        manifest,tl=check_package(self.folder);change(tl)
        file=self.folder/'return.otio';otio.adapters.write_to_file(tl,str(file));return file

    def test_relocation_collects_external_audio_notes_intent_and_markers(self):
        outside=Path(self.temp.name)/'outside audio.wav';shutil.copy2(self.p.audio,outside)
        config=self.fixture.config;config['audio']=str(outside)
        self.fixture.edit['events']=[{'id':'beat','frame':2,'basis':'action','meaning':'Arrival'}]
        self.fixture.save()
        from sbph.project import Project
        self.fixture.p=self.p=Project.load(self.p.config);self.fixture.make_manifest()
        add_note(self.p,'Hold this beat','1','1f');set_intent(self.p,'1',{'goal':'Receive a signal'})
        source_snapshot={str(f):sha(f) for f in self.p.root.rglob('*') if f.is_file()}
        self.collect()
        relocated=Path(self.temp.name)/'moved package';shutil.move(self.folder,relocated)
        shutil.rmtree(self.p.root);outside.unlink()
        manifest,tl=check_package(relocated)
        self.assertEqual(len(manifest['media']),3)
        self.assertEqual(tl.video_tracks()[0].markers[0].name,'beat')
        self.assertTrue(all(not c.media_reference.target_url.startswith('file:') for c in tl.find_clips()))
        context=json.loads((relocated/'editorial-context.json').read_text())
        self.assertEqual(context['notes'][0]['text'],'Hold this beat')
        self.assertEqual(context['intent'][0]['fields']['goal'],'Receive a signal')
        self.assertTrue(source_snapshot)
        file=relocated/'return.otio';otio.adapters.write_to_file(tl,str(file))
        self.assertEqual(compare(relocated,file)['status'],'unchanged')

    def test_refuses_existing_destination_and_stale_sources_without_writes(self):
        self.folder.mkdir();(self.folder/'owner').write_text('keep')
        with self.assertRaisesRegex(ValueError,'exists'):self.collect()
        self.assertEqual((self.folder/'owner').read_text(),'keep')
        shutil.rmtree(self.folder);self.p.driver.write_text('changed')
        with self.assertRaisesRegex(ValueError,'Stale'):self.collect()
        self.assertFalse(self.folder.exists())

    def test_tampered_and_escaping_packages_fail(self):
        self.collect();manifest,_=check_package(self.folder)
        movie=self.folder/manifest['media'][0]['file'];original=movie.read_bytes();movie.write_bytes(b'tamper')
        with self.assertRaisesRegex(ValueError,'changed'):check_package(self.folder)
        movie.write_bytes(original)
        for bad in ['../outside','file:///tmp/outside','/tmp/outside','%2e%2e/outside']:
            data=json.loads(json.dumps(manifest));data['files'][bad]='0'*64;dump(self.folder/'handoff.json',data)
            with self.assertRaisesRegex(ValueError,'Unsafe'):check_package(self.folder)

    def test_unchanged_is_read_only_and_checks_local_bytes(self):
        canonical=self.p.output/'human-edit.otio';canonical.write_bytes(b'preserved timeline')
        self.collect();self.assertEqual(canonical.read_bytes(),b'preserved timeline')
        file=self.returned();before={str(f):sha(f) for f in self.folder.rglob('*') if f.is_file()}
        result=compare(self.folder,file)
        self.assertEqual(result['status'],'unchanged');self.assertTrue(result['originalAudioPreserved']);self.assertTrue(result['comparisonComplete'])
        self.assertEqual(before,{str(f):sha(f) for f in self.folder.rglob('*') if f.is_file()})

    def test_cli_checks_and_compares_without_a_project_and_refuses_overwrites(self):
        from sbph.__main__ import main
        self.collect();file=self.returned();output=Path(self.temp.name)/'comparison.json'
        with patch('sys.argv',['sbph','package-check',str(self.folder),'--json']),contextlib.redirect_stdout(io.StringIO()) as capture:
            main()
        self.assertEqual(json.loads(capture.getvalue())['status'],'valid')
        argv=['sbph','compare-return',str(self.folder),'--returned',str(file),'--out',str(output),'--json']
        with patch('sys.argv',argv),contextlib.redirect_stdout(io.StringIO()):main()
        self.assertEqual(json.loads(output.read_text())['status'],'unchanged')
        with patch('sys.argv',argv),self.assertRaisesRegex(ValueError,'exists'):main()

    def test_trim_slip_reorder_gap_duplicate_and_deletion(self):
        self.collect()
        def edit(tl):
            track=tl.video_tracks()[0];first=track[0].deepcopy();second=track[1].deepcopy();track.clear()
            second.source_range=TR(RT(1,30),RT(4,30))
            track.extend([second,otio.schema.Gap(source_range=TR(RT(0,30),RT(1,30))),second.deepcopy()])
        report=compare(self.folder,self.returned(edit))
        self.assertEqual(report['status'],'needs_review');self.assertTrue(report['originalAudioPreserved'])
        self.assertTrue(any(c['type']=='gaps' for c in report['changes']))
        self.assertTrue(any(c.get('clip')=='1' and c.get('after')==0 for c in report['changes']))
        self.assertTrue(any(c.get('clip')=='2' and c.get('after')==2 for c in report['changes']))
        fields=[c.get('fields',{}) for c in report['changes']]
        self.assertTrue(any('sourceStart' in f and 'duration' in f and 'timelineStart' in f for f in fields))

    def test_audio_shift_and_handle_overrun_are_visible(self):
        self.collect()
        def edit(tl):
            tl.video_tracks()[0][0].source_range=TR(RT(-1,30),RT(3,30))
            tl.audio_tracks()[0].insert(0,otio.schema.Gap(source_range=TR(RT(0,30),RT(1,30))))
        report=compare(self.folder,self.returned(edit))
        self.assertFalse(report['originalAudioPreserved'])
        self.assertTrue(any(i['kind']=='handle_overrun' for i in report['issues']))

    def test_unknown_changed_missing_and_ambiguous_media_are_not_guessed_from_names(self):
        self.collect()
        def edit(tl):
            first=tl.video_tracks()[0][0];first.metadata.clear()
            second=tl.video_tracks()[0][1];second.media_reference.target_url='missing.mp4'
            audio=tl.audio_tracks()[0][0];audio.effects.append(otio.schema.Effect(name='gain'))
        report=compare(self.folder,self.returned(edit))
        self.assertFalse(report['comparisonComplete']);self.assertFalse(report['originalAudioPreserved'])
        self.assertTrue({'unmatched','unverified_media','unsupported'}<={i['kind'] for i in report['issues']})
        def changed(tl):
            file=self.folder/'replacement.mp4';file.write_bytes(b'different')
            tl.video_tracks()[0][0].media_reference.target_url=file.name
        report=compare(self.folder,self.returned(changed))
        self.assertTrue(any(i['kind']=='media_changed' for i in report['issues']))

    def test_nested_tracks_transitions_and_rate_changes_require_review(self):
        self.collect()
        def edit(tl):
            track=tl.video_tracks()[0];track[0].source_range=TR(RT(1,24),RT(2,24))
            track.insert(1,otio.schema.Transition(in_offset=RT(1,30),out_offset=RT(1,30)))
            tl.tracks.append(otio.schema.Stack())
        report=compare(self.folder,self.returned(edit))
        self.assertFalse(report['comparisonComplete'])
        self.assertTrue(any(i['kind']=='unsupported' for i in report['issues']))

    def test_malformed_package_and_return_identity_fail_explicitly(self):
        self.collect();manifest,_=check_package(self.folder)
        for field,value in [('fps',True),('media',[None]),('timeline',['bad'])]:
            modified=json.loads(json.dumps(manifest));modified[field]=value;dump(self.folder/'handoff.json',modified)
            with self.assertRaises(ValueError):check_package(self.folder)
        dump(self.folder/'handoff.json',manifest)
        def edit(tl):tl.video_tracks()[0][0].metadata['sbph']={'media_sha256':[]}
        report=compare(self.folder,self.returned(edit))
        self.assertFalse(report['comparisonComplete']);self.assertEqual(report['status'],'needs_review')

    def test_disabled_root_stack_is_a_material_change_and_never_preserves_audio(self):
        self.collect()
        def disabled(tl):tl.tracks.enabled=False
        report=compare(self.folder,self.returned(disabled))
        self.assertEqual(report['status'],'needs_review');self.assertFalse(report['originalAudioPreserved'])
        self.assertTrue(any(c['type']=='stack_enabled' for c in report['changes']))
        self.assertTrue(any(i['kind']=='disabled' and i['where']=='timeline' for i in report['issues']))

    def test_basename_association_never_verifies_unavailable_returned_bytes(self):
        self.collect()
        def remote(tl):
            for clip in tl.find_clips():clip.media_reference.target_url='file:///another/computer/'+Path(clip.media_reference.target_url).name
        report=compare(self.folder,self.returned(remote))
        self.assertFalse(report['comparisonComplete']);self.assertFalse(report['originalAudioPreserved'])
        self.assertTrue(all(r['mediaSha256'] is None and r['presumedCollectedMedia'] for r in report['returnedClips']))
        self.assertEqual({i['kind'] for i in report['issues']},{'unverified_media'})

    def test_invalid_baseline_structure_fails_even_when_inventory_hashes_match(self):
        self.collect();manifest,original=check_package(self.folder)
        def disabled(tl):tl.tracks.enabled=False
        def audio_trim(tl):tl.audio_tracks()[0][0].source_range=TR(RT(1,30),RT(5,30))
        def effects(tl):tl.video_tracks()[0].effects.append(otio.schema.Effect(name='effect'))
        def extra(tl):tl.tracks.append(otio.schema.Track(kind='Audio'))
        def gap(tl):tl.video_tracks()[0].insert(0,otio.schema.Gap(source_range=TR(RT(0,30),RT(1,30))))
        def provenance(tl):tl.metadata['sbph']['sourceFingerprint']='0'*64
        for edit in [disabled,audio_trim,effects,extra,gap,provenance]:
            with self.subTest(edit=edit.__name__):
                tl=original.deepcopy();edit(tl);otio.adapters.write_to_file(tl,str(self.folder/'edit.otio'))
                changed=json.loads(json.dumps(manifest));changed['files']['edit.otio']=sha(self.folder/'edit.otio');dump(self.folder/'handoff.json',changed)
                with self.assertRaises(ValueError):check_package(self.folder)

    def test_report_binds_the_baseline_manifest_and_timeline(self):
        self.collect();report=compare(self.folder,self.returned())
        self.assertEqual(report['baselineManifestSha256'],sha(self.folder/'handoff.json'))
        self.assertEqual(report['baselineTimelineSha256'],sha(self.folder/'edit.otio'))

    def test_shot_named_original_audio_does_not_collide_with_the_audio_identity(self):
        self.fixture.edit['scenes'][0]['id']='original_audio';self.fixture.save()
        from sbph.project import Project
        self.fixture.p=self.p=Project.load(self.p.config);self.fixture.make_manifest();self.collect()
        report=compare(self.folder,self.returned())
        self.assertEqual(report['status'],'unchanged');self.assertTrue(report['originalAudioPreserved'])


if __name__=='__main__':unittest.main()
