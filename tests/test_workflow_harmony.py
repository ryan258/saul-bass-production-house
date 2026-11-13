"""Read-only orientation, deliberate selection, and hash-bound owner evidence."""
import json,tempfile,unittest,os,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from workflow_fixtures import project,files
from sbph.project import dump,sha,FRAMEWORK
from sbph.evidence import preflight,saved_records,record_screening,screening_status
from sbph.status import delivery,production_action
from sbph.unit9_run import select,resolve


class WorkflowHarmony(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.p=project(self.root);self.p.output.mkdir();self.p.source_inventory=lambda:('current',[])

    def saved_delivery(self):
        movie=self.p.output/'assembly.mp4';movie.write_bytes(b'delivery')
        dump(self.p.output/'media-verification.json',{'status':'passed','sourceFingerprint':'current','delivery':str(self.p.public_path(movie)),'deliverySha256':sha(movie)})
        timeline=self.p.output/'human-edit.otio';timeline.write_bytes(b'timeline')
        dump(self.p.output/'timeline-verification.json',{'sourceFingerprint':'current','timelineSha256':sha(timeline)})
        reference=self.p.output/'proof.mp4';reference.write_bytes(b'reference')
        dump(self.p.output/'assembly-verification.json',{'status':'passed_with_exclusions','sourceFingerprint':'current','sha256':sha(movie),'reference':str(reference),'referenceSha256':sha(reference),'firstFrameReviewRequired':True})
        return movie

    def test_preflight_and_evidence_are_read_only_and_missing_audio_blocks_readiness(self):
        before=files(self.p.root);self.assertEqual(preflight(self.p)['status'],'ready')
        self.assertEqual(saved_records(self.p)['records'],[]);self.assertEqual(files(self.p.root),before)
        self.p.audio.unlink();self.assertEqual(preflight(self.p)['status'],'blocked')
        result=subprocess.run([sys.executable,'-m','sbph','preflight',str(self.p.config)],env={**os.environ,'PYTHONPATH':str(FRAMEWORK/'src')},capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(json.loads(result.stdout)['status'],'blocked')

    def test_failed_resolve_acceptance_has_nonzero_cli_exit(self):
        code="import runpy,sys;from unittest.mock import patch;sys.argv=['sbph','resolve-check','handoff','--json']\nwith patch('sbph.resolve.check',return_value={'status':'failed'}):runpy.run_module('sbph.__main__',run_name='__main__')"
        result=subprocess.run([sys.executable,'-c',code],env={**os.environ,'PYTHONPATH':str(FRAMEWORK/'src')},capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertEqual(json.loads(result.stdout)['status'],'failed')

    def test_current_delivery_suggests_screening_and_stale_timeline_suggests_export(self):
        movie=self.saved_delivery();before=files(self.p.root)
        result=production_action(self.p,{'status':'matches'},delivery(self.p))
        self.assertEqual(result['stage'],'screening');self.assertIn('exclusions',result['text']);self.assertEqual(files(self.p.root),before)
        (self.p.output/'human-edit.otio').write_bytes(b'changed export')
        self.assertEqual(production_action(self.p,{'status':'matches'},delivery(self.p))['stage'],'timeline')

    def test_changed_reference_cannot_reuse_saved_conform(self):
        self.saved_delivery();(self.p.output/'proof.mp4').write_bytes(b'new reference')
        self.assertEqual(production_action(self.p,{'status':'matches'},delivery(self.p))['stage'],'conform')

    def test_screening_needs_explicit_attestation_and_matches_exact_movie(self):
        movie=self.saved_delivery()
        with self.assertRaisesRegex(ValueError,'Watch the complete'):record_screening(self.p)
        with patch('sbph.status.shot_build',return_value={'status':'matches'}):
            report=record_screening(self.p,True,True,'Reviewed the ending and exact cut frames')
        self.assertEqual(report['status'],'attested');self.assertTrue(Path(report['file']).is_file())
        self.assertEqual(screening_status(self.p,movie,'current')['status'],'attested')
        movie.write_bytes(b'changed delivery');self.assertIsNone(screening_status(self.p,movie,'current'))

    def test_delivery_public_path_mapping_is_not_mistaken_for_changed_movie(self):
        self.p.deliver_root=self.root/'relocated';self.saved_delivery()
        self.assertEqual(delivery(self.p)['verification'],'saved report matches movie bytes')

    def test_run_selection_is_explicit_and_refuses_escaping_or_redirected_runs(self):
        base=self.root/'toolkit';run=base/'output/unit-9-motion-handled/complete'
        dump(run/'production.json',{'renderer':'motion-canvas','root':str(base/'examples/unit-9-motion'),'output':str(run)})
        self.assertEqual(resolve(base),base/'examples/unit-9-motion.json')
        self.assertEqual(select(base,'complete'),run/'production.json');before=files(base)
        self.assertEqual(resolve(base),run/'production.json');self.assertEqual(files(base),before)
        select(base,'default');self.assertEqual(resolve(base),base/'examples/unit-9-motion.json')
        with self.assertRaises(ValueError):select(base,'../escape')
        dump(run/'production.json',{'renderer':'motion-canvas','root':str(base/'examples/unit-9-motion'),'output':str(base/'elsewhere')})
        with self.assertRaisesRegex(ValueError,'native Unit 9'):resolve(base,'complete')

    def test_run_selection_canonicalizes_a_symlinked_toolkit_root(self):
        base=self.root/'physical-toolkit';run=base/'output/unit-9-motion-handled/complete'
        dump(run/'production.json',{'renderer':'motion-canvas','root':str(base/'examples/unit-9-motion'),'output':str(run)})
        alias=self.root/'toolkit-alias';alias.symlink_to(base,target_is_directory=True)
        self.assertEqual(resolve(alias),(base/'examples/unit-9-motion.json').resolve())
        self.assertEqual(select(alias,'complete'),(run/'production.json').resolve())
        before=files(base)
        self.assertEqual(resolve(alias),(run/'production.json').resolve());self.assertEqual(files(base),before)


if __name__=='__main__':unittest.main()
