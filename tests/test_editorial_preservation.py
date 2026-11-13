"""Editorial artifact generations and explicit cut-frame evidence; no Unit 9 media."""
from pathlib import Path
import contextlib,io,json,tempfile,unittest
from unittest.mock import patch
import numpy as np
import opentimelineio as otio
import test_production_validation as fixtures
from sbph import __version__
from sbph.project import Project,dump,sha
from sbph.timeline import timeline
from sbph.assembly_check import check as conform


class EditorialPreservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ProductionValidation.setUpClass();cls.addClassCleanup(fixtures.ProductionValidation.doClassCleanups)

    def setUp(self):
        self.fixture=fixtures.ProductionValidation();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.p=self.fixture.p
        self.files=[self.p.output/'human-edit.otio',self.p.output/'human-edit.xml',self.p.output/'timeline-verification.json']
        for file in self.files:file.write_bytes(('previous '+file.name).encode())
        self.before={f:f.read_bytes() for f in self.files}

    def unchanged(self):
        for file,content in self.before.items():self.assertEqual(file.read_bytes(),content)

    def test_xml_serialization_failure_preserves_all_previous_exports(self):
        real=otio.adapters.write_to_file
        def write(tl,path,**kwargs):
            if kwargs.get('adapter_name')=='fcp_xml':raise RuntimeError('XML adapter failed')
            return real(tl,path,**kwargs)
        with patch('sbph.timeline.otio.adapters.available_adapter_names',return_value=['fcp_xml']),patch('sbph.timeline.otio.adapters.write_to_file',side_effect=write):
            with self.assertRaisesRegex(RuntimeError,'XML adapter failed'):timeline(self.p)
        self.unchanged()

    def test_receipt_staging_failure_and_late_source_changes_preserve_previous_set(self):
        source=self.p.driver.read_bytes();real=dump
        for mode in ['receipt','source','shot']:
            with self.subTest(mode=mode):
                self.p.driver.write_bytes(source);self.fixture.make_manifest()
                def staged(path,data):
                    if Path(path).name=='timeline-verification.json':
                        if mode=='receipt':raise OSError('receipt failed')
                        real(path,data)
                        if mode=='source':self.p.driver.write_bytes(source+b'changed')
                        else:(self.p.output/'shots/1-test.mp4').write_bytes(b'changed clip')
                    else:real(path,data)
                with patch('sbph.timeline.otio.adapters.available_adapter_names',return_value=[]),patch('sbph.timeline.dump',side_effect=staged):
                    with self.assertRaises((OSError,ValueError)):timeline(self.p)
                self.unchanged()

    def test_receipt_promotion_failure_rolls_back_timeline_and_xml(self):
        real=Path.replace
        def replace(path,target):
            if Path(path).parent.name.startswith('.timeline-') and Path(target)==self.files[2]:raise OSError('receipt promotion failed')
            return real(path,target)
        with patch('sbph.timeline.otio.adapters.available_adapter_names',return_value=[]),patch.object(Path,'replace',replace):
            with self.assertRaisesRegex(OSError,'receipt promotion failed'):timeline(self.p)
        self.unchanged()

    def test_success_receipt_binds_timeline_and_uses_current_version(self):
        with patch('sbph.timeline.otio.adapters.available_adapter_names',return_value=[]),contextlib.redirect_stdout(io.StringIO()):output=timeline(self.p)
        report=json.loads(self.files[2].read_text());tl=otio.adapters.read_from_file(str(output))
        self.assertEqual(report['timelineSha256'],sha(output));self.assertEqual(tl.metadata['sbph']['version'],__version__)
        self.assertIn('not measured',report['resolveImport']);self.assertFalse(self.files[1].exists())

    def test_declared_source_at_a_timeline_destination_is_preserved(self):
        self.fixture.config['source_files']=['production/human-edit.otio'];self.fixture.save()
        self.fixture.p=self.p=Project.load(self.p.config);self.fixture.make_manifest()
        with self.assertRaisesRegex(ValueError,'protected input'):timeline(self.p)
        self.unchanged()

    def test_offset_conform_records_exact_cut_differences_as_pending_review(self):
        assembled=self.p.output/'assembly.mp4';reference=self.p.root/'reference.mp4';assembled.write_bytes(b'assembly');reference.write_bytes(b'reference')
        self.p.data['verification']={'conform_first_frame_offset':1}
        # Project settings are render-irrelevant, but the live config still must
        # match the loaded object when the final source gate is checked.
        self.fixture.config['verification']=self.p.data['verification'];self.fixture.save()
        info={'streams':[{'codec_type':'video','nb_frames':'6','avg_frame_rate':'30/1','width':16,'height':16}]}
        def sample(path,frames,size):
            return np.full((len(frames),1,1,3),255 if Path(path)==assembled and frames==[0,3] else 0,dtype=np.uint8)
        audio={'sourceSha256':sha(self.p.audio)}
        with patch('sbph.assembly_check.probe',return_value=info),patch('sbph.assembly_check.sample',side_effect=sample),patch('sbph.assembly_check.project_audio_comparison',return_value=audio),contextlib.redirect_stdout(io.StringIO()):report=conform(self.p,reference)
        self.assertEqual(report['status'],'passed_with_exclusions');self.assertFalse(report['comparisonComplete']);self.assertTrue(report['firstFrameReviewRequired'])
        self.assertEqual(report['excludedFirstFrames'],[0,3]);self.assertEqual(report['firstFrameEvidence']['differingFrames'],[0,3])
        self.assertIn('start + 1',report['method']);self.assertEqual(report['maximumRgbMae'],0)

    def test_conform_rejects_missing_multiple_or_malformed_video_metadata(self):
        assembled=self.p.output/'assembly.mp4';reference=self.p.root/'reference.mp4';assembled.write_bytes(b'assembly');reference.write_bytes(b'reference')
        video={'codec_type':'video','nb_frames':'6','avg_frame_rate':'30/1','width':16,'height':16}
        for streams in [[],[{'codec_type':'audio'}],[video,video],[{**video,'avg_frame_rate':'unknown'}],None]:
            with self.subTest(streams=streams),patch('sbph.assembly_check.probe',return_value={'streams':streams}),patch('sbph.assembly_check.sample') as sample:
                with self.assertRaises(ValueError):conform(self.p,reference)
                sample.assert_not_called()

    def test_conform_source_change_while_staging_receipt_preserves_previous_evidence(self):
        assembled=self.p.output/'assembly.mp4';reference=self.p.root/'reference.mp4';assembled.write_bytes(b'assembly');reference.write_bytes(b'reference')
        receipt=self.p.output/'assembly-verification.json';receipt.write_bytes(b'previous evidence');audio={'sourceSha256':sha(self.p.audio)}
        info={'streams':[{'codec_type':'video','nb_frames':'6','avg_frame_rate':'30/1','width':16,'height':16}]}
        def changed(path,data):dump(path,data);self.p.audio.write_bytes(self.p.audio.read_bytes()+b'changed')
        with patch('sbph.assembly_check.probe',return_value=info),patch('sbph.assembly_check.sample',side_effect=lambda path,frames,size:np.zeros((len(frames),1,1,3),dtype=np.uint8)),patch('sbph.assembly_check.project_audio_comparison',return_value=audio),patch('sbph.assembly_check.dump',side_effect=changed):
            with self.assertRaisesRegex(RuntimeError,'Build sources changed'):conform(self.p,reference)
        self.assertEqual(receipt.read_bytes(),b'previous evidence')

    def test_override_reference_retains_local_identity_when_public_paths_are_remapped(self):
        assembled=self.p.output/'assembly.mp4';reference=self.p.root/'reference.mp4';assembled.write_bytes(b'assembly');reference.write_bytes(b'reference')
        mapped=self.p.root/'mapped-delivery';self.p.public_path=lambda path:mapped/Path(path).resolve().relative_to(self.p.root)
        info={'streams':[{'codec_type':'video','nb_frames':'6','avg_frame_rate':'30/1','width':16,'height':16}]};audio={'sourceSha256':sha(self.p.audio)}
        with patch('sbph.assembly_check.probe',return_value=info),patch('sbph.assembly_check.sample',side_effect=lambda path,frames,size:np.zeros((len(frames),1,1,3),dtype=np.uint8)),patch('sbph.assembly_check.project_audio_comparison',return_value=audio),contextlib.redirect_stdout(io.StringIO()):report=conform(self.p,reference)
        self.assertEqual(report['reference'],str(mapped/'reference.mp4'));self.assertFalse(Path(report['reference']).exists())
        self.assertEqual(report['referenceLocal'],str(reference.resolve()));self.assertEqual(report['referenceSha256'],sha(reference))


if __name__=='__main__':unittest.main()
