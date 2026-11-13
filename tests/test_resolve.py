"""Resolve acceptance logic with a fake Resolve; the real application is never required."""
from pathlib import Path
import copy,shutil,tempfile,unittest
from unittest.mock import patch
import opentimelineio as otio
import test_production_validation as fixtures
from sbph import resolve
from sbph.handoff import package,check_package


class FakeItem:
    def __init__(self,row,origin,folder):self.row,self.origin,self.folder=row,origin,folder
    def GetName(self):return self.row['name']
    def GetStart(self):return self.origin+self.row['start']
    def GetDuration(self):return self.row['duration']
    def GetLeftOffset(self):return self.row['sourceStart']
    def GetMediaPoolItem(self):return self
    def GetClipProperty(self,key):return str(self.folder/self.row['file'])


class FakeTimeline:
    def __init__(self,exp,folder):self.exp,self.folder,self.change=exp,folder,None
    def GetStartFrame(self):return 86400
    def GetTrackCount(self,kind):return self.exp['trackCounts'][kind]
    def GetItemListInTrack(self,kind,number):return [FakeItem(r,86400,self.folder) for r in self.exp[kind]] if number==1 else []
    def GetSetting(self,key):return str(float(self.exp['fps']))
    def GetMarkers(self):return {frame:{} for frame in self.exp['markers']}
    def Export(self,path,kind):
        tl=otio.adapters.read_from_file(str(self.folder/'edit.otio'))
        for clip in tl.find_clips():clip.media_reference.target_url=(self.folder/clip.media_reference.target_url).as_uri()
        if self.change:self.change(tl)
        otio.adapters.write_to_file(tl,path);return True


class FakeResolve:
    EXPORT_OTIO='otio'
    def __init__(self,exp,folder):self.timeline=FakeTimeline(exp,folder)
    def GetProjectManager(self):return self
    def GetCurrentProject(self):return self
    def GetMediaPool(self):return self
    def ImportTimelineFromFile(self,path,options):
        assert Path(path).name=='edit.otio' and options['importSourceClips'] and options['timelineName'];return self.timeline
    def GetProductName(self):return 'DaVinci Resolve Studio'
    def GetVersionString(self):return '19.0'


class ResolveAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProductionValidation.setUpClass()
        cls.addClassCleanup(fixtures.ProductionValidation.doClassCleanups)

    def setUp(self):
        self.fixture=fixtures.ProductionValidation();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)/'handoff';package(self.fixture.p,self.folder)
        self.exp=resolve.expected(self.folder)

    def facts(self):
        timeline=FakeTimeline(self.exp,self.folder)
        return {'fps':float(self.exp['fps']),'markers':sorted(self.exp['markers']),'trackCounts':self.exp['trackCounts'].copy(),
            'video':[{'name':r['name'],'start':r['start'],'duration':r['duration'],'leftOffset':r['sourceStart'],'path':str(self.folder/r['file'])} for r in self.exp['video']],
            'audio':[{'name':r['name'],'start':r['start'],'duration':r['duration'],'leftOffset':r['sourceStart'],'path':str(self.folder/r['file'])} for r in self.exp['audio']]}

    def test_expected_matches_the_package_and_a_faithful_import_passes(self):
        self.assertEqual(len(self.exp['video']),len(self.fixture.p.edit['scenes']));self.assertEqual(len(self.exp['audio']),1)
        self.assertEqual(self.exp['video'][0]['sourceStart'],self.fixture.p.handles)
        self.assertEqual([c['status'] for c in resolve.evaluate(self.facts(),self.exp) if c['status']!='passed'],[])

    def test_wrong_rate_offset_offline_media_and_clip_count_fail(self):
        for change,name in [(lambda f:f.update(fps=f['fps']+1),'frame rate'),(lambda f:f['video'][0].update(leftOffset=0),'handle in-point'),
                (lambda f:f['video'][0].update(path=None),'media online'),(lambda f:f['video'].pop(),'video clip count'),
                (lambda f:f['audio'][0].update(duration=1),'audio 1')]:
            facts=copy.deepcopy(self.facts());change(facts)
            failed=[c['check'] for c in resolve.evaluate(facts,self.exp) if c['status']=='failed']
            self.assertTrue(any(name in item for item in failed),(name,failed))

    def test_missing_markers_warn_without_failing(self):
        facts=self.facts();facts['markers']=[]
        statuses={c['check']:c['status'] for c in resolve.evaluate(facts,self.exp)}
        if self.exp['markers']:self.assertEqual(statuses['markers'],'warning')
        self.assertNotIn('failed',statuses.values())

    def test_scripted_check_imports_exports_compares_and_leaves_the_package_valid(self):
        with patch('sbph.resolve.connect',return_value=FakeResolve(self.exp,self.folder)):report=resolve.check(self.folder)
        self.assertEqual(report['status'],'passed',report['checks']);self.assertEqual(report['exportedReturn']['status'],'unchanged')
        self.assertTrue(Path(report['file']).is_file());check_package(self.folder)

    def test_manual_record_distinguishes_attested_from_incomplete(self):
        report=resolve.record(self.folder,'19.1 Free',{'imported':True,'linked':True,'markersVisible':True,'audioLocked':False})
        self.assertEqual(report['status'],'incomplete');self.assertEqual(report['mode'],'manual')
        self.assertIn('not confirmed',[c['status'] for c in report['checks']]);check_package(self.folder)

    def test_manual_record_with_full_attestation_and_return_comparison(self):
        shutil.copy2(self.folder/'edit.otio',self.folder/'return.otio')
        report=resolve.record(self.folder,'19.1 Free',dict.fromkeys(resolve.ATTESTATIONS,True),self.folder/'return.otio','looked right')
        self.assertEqual(report['status'],'attested');self.assertEqual(report['exportedReturn']['status'],'unchanged')

    def test_windows_absolute_paths_are_only_presumed_associations(self):
        _,tl=check_package(self.folder)
        for clip in tl.find_clips():clip.media_reference.target_url='file:///C:/Users/me/Resolve%20Media/'+clip.media_reference.target_url.rsplit('/',1)[-1]
        otio.adapters.write_to_file(tl,str(self.folder/'return.otio'))
        from sbph.editor_return import compare
        report=compare(self.folder,self.folder/'return.otio')
        self.assertEqual(report['status'],'needs_review');self.assertFalse(report['comparisonComplete']);self.assertFalse(report['originalAudioPreserved'])
        self.assertTrue(all(not r['mediaVerified'] and r['presumedCollectedMedia'] for r in report['returnedClips']))
        self.assertTrue(all(i['kind']=='unverified_media' for i in report['issues']))

    def test_imported_media_bytes_all_track_counts_and_audio_inpoint_are_checked(self):
        replacement=self.folder/'different.wav';replacement.write_bytes(b'wrong original recording')
        for change,check in [(lambda f:f['audio'][0].update(path=str(replacement)),'media identity'),
                (lambda f:f['audio'][0].update(leftOffset=1),'source in-point'),
                (lambda f:f['trackCounts'].update(video=2),'video track count'),
                (lambda f:f['trackCounts'].update(audio=2),'audio track count')]:
            with self.subTest(check=check):
                facts=self.facts();change(facts)
                self.assertTrue(any(check in r['check'] and r['status']=='failed' for r in resolve.evaluate(facts,self.exp)))

    def test_material_or_unverifiable_exports_fail_scripted_acceptance(self):
        def slip(tl):
            clip=tl.video_tracks()[0][0];clip.source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(1,self.exp['fps']),clip.source_range.duration)
        def missing(tl):tl.audio_tracks()[0][0].media_reference.target_url='file:///unavailable/original.wav'
        def root_disabled(tl):tl.tracks.enabled=False
        def audio_effect(tl):tl.audio_tracks()[0][0].effects.append(otio.schema.Effect(name='gain'))
        def extra_track(tl):tl.tracks.append(otio.schema.Track(kind=otio.schema.TrackKind.Audio))
        for change in [slip,missing,root_disabled,audio_effect,extra_track]:
            with self.subTest(change=change.__name__):
                fake=FakeResolve(self.exp,self.folder);fake.timeline.change=change
                with patch('sbph.resolve.connect',return_value=fake):report=resolve.check(self.folder)
                self.assertEqual(report['status'],'failed',report)
                self.assertTrue(any(r['check']=='exported return' and r['status']=='failed' for r in report['checks']))

    def test_marker_only_export_changes_warn_and_preserve_acceptance(self):
        fake=FakeResolve(self.exp,self.folder)
        def markers(tl):tl.video_tracks()[0].markers.append(otio.schema.Marker(name='editor marker'))
        fake.timeline.change=markers
        with patch('sbph.resolve.connect',return_value=fake):report=resolve.check(self.folder)
        self.assertEqual(report['status'],'passed');self.assertEqual(report['exportedReturn']['materialChanges'],0)
        self.assertTrue(any(r['status']=='warning' for r in report['checks']))

    def test_export_failures_and_malformed_export_never_pass(self):
        for exported in [False,True]:
            fake=FakeResolve(self.exp,self.folder)
            with patch.object(fake.timeline,'Export',return_value=exported),patch('sbph.resolve.connect',return_value=fake):report=resolve.check(self.folder)
            self.assertEqual(report['status'],'failed')
        fake=FakeResolve(self.exp,self.folder)
        with patch.object(fake.timeline,'Export',side_effect=RuntimeError('export refused')),patch('sbph.resolve.connect',return_value=fake):report=resolve.check(self.folder)
        self.assertEqual(report['status'],'failed');self.assertTrue(any(r['detail']=='export refused' for r in report['checks']))

    def test_manual_failed_comparison_overrides_full_attestation(self):
        _,tl=check_package(self.folder);tl.tracks.enabled=False
        file=self.folder/'disabled.otio';otio.adapters.write_to_file(tl,str(file))
        report=resolve.record(self.folder,'19.1 Free',dict.fromkeys(resolve.ATTESTATIONS,True),file)
        self.assertEqual(report['status'],'failed');self.assertFalse(report['exportedReturn']['originalAudioPreserved'])

    def test_manual_editorial_changes_need_explicit_acceptance_and_verified_audio(self):
        _,tl=check_package(self.folder);clip=tl.video_tracks()[0][0]
        clip.source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(1,self.exp['fps']),clip.source_range.duration)
        file=self.folder/'edited.otio';otio.adapters.write_to_file(tl,str(file));confirmed=dict.fromkeys(resolve.ATTESTATIONS,True)
        self.assertEqual(resolve.record(self.folder,'19.1 Free',confirmed,file)['status'],'failed')
        report=resolve.record(self.folder,'19.1 Free',confirmed,file,accept_edits=True)
        self.assertEqual(report['status'],'attested');self.assertTrue(report['acceptedEditorialChanges'])
        tl.audio_tracks()[0][0].effects.append(otio.schema.Effect(name='gain'));otio.adapters.write_to_file(tl,str(file))
        self.assertEqual(resolve.record(self.folder,'19.1 Free',confirmed,file,accept_edits=True)['status'],'failed')

    def test_acceptance_records_and_exports_are_unique_and_bound_to_package(self):
        with patch('sbph.resolve.stamp',return_value='same-second'),patch('sbph.resolve.connect',return_value=FakeResolve(self.exp,self.folder)):
            first=resolve.check(self.folder);second=resolve.check(self.folder)
        self.assertNotEqual(first['file'],second['file']);self.assertNotEqual(first['exportedReturn']['file'],second['exportedReturn']['file'])
        self.assertEqual(first['packageIdentity'],resolve.package_identity(self.folder))
        self.assertEqual(first['exportedReturn']['baselineManifestSha256'],first['packageIdentity']['handoffSha256'])

    def test_exclusive_receipt_creation_never_replaces_an_existing_record(self):
        from types import SimpleNamespace
        with patch('sbph.resolve.stamp',return_value='same-second'),patch('sbph.resolve.uuid.uuid4',return_value=SimpleNamespace(hex='a'*32)):
            first=resolve.write(self.folder,{'status':'original'})
            with self.assertRaises(FileExistsError):resolve.write(self.folder,{'status':'replacement'})
        import json
        self.assertEqual(json.loads(Path(first['file']).read_text())['status'],'original')

    def test_manual_record_requires_a_version(self):
        with self.assertRaisesRegex(ValueError,'edition and version'):resolve.record(self.folder,None,{})

    def test_connect_explains_the_free_edition_limit(self):
        class Dead:
            @staticmethod
            def scriptapp(name):return None
        with patch.dict('sys.modules',{'DaVinciResolveScript':Dead}),self.assertRaisesRegex(ValueError,'free edition'):resolve.connect()


if __name__=='__main__':unittest.main()
