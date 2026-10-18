"""Whole-set output recovery, using tiny files and directories only."""
from pathlib import Path
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sbph.media import _promote_files


def snapshot(folder):
    return {
        path.relative_to(folder).as_posix():None if path.is_dir() else path.read_bytes()
        for path in sorted(folder.rglob('*'))
    }


class OutputPromotion(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def fixture(self,name='case'):
        root=self.root/name;root.mkdir()
        output=root/'production';output.mkdir()
        work=root/'.render-work';work.mkdir()
        for name in ['movie.mp4','proof.json','obsolete.jpg']:
            (output/name).write_bytes(('old '+name).encode())
        for name in ['source-frames','obsolete-work','editor-exports']:
            (output/name/'nested').mkdir(parents=True)
            (output/name/'nested/owner.png').write_bytes(('old '+name).encode())
        for name in ['movie.mp4','proof.json','new.txt']:
            (work/name).write_bytes(('new '+name).encode())
        for name in ['source-frames','new-frames']:
            (work/name).mkdir()
            (work/name/'new.png').write_bytes(('new '+name).encode())
        pairs=[(work/name,output/name) for name in
            ['movie.mp4','source-frames','new.txt','new-frames','proof.json']]
        remove=[output/'obsolete.jpg',output/'obsolete-work',output/'already-absent.jpg']
        return output,work,pairs,remove

    def test_promotes_files_and_directories_and_removes_only_requested_artifacts(self):
        output,work,pairs,remove=self.fixture()
        owner=snapshot(output/'editor-exports')
        old_directory_inode=(output/'source-frames').stat().st_ino
        replace=Path.replace;moved_inodes=[]
        def observe_directory_backup(path,destination):
            result=replace(path,destination)
            if path==output/'source-frames':moved_inodes.append(Path(destination).stat().st_ino)
            return result
        with patch.object(Path,'replace',observe_directory_backup):_promote_files(pairs,work,remove=remove)
        self.assertEqual((output/'movie.mp4').read_bytes(),b'new movie.mp4')
        self.assertEqual((output/'proof.json').read_bytes(),b'new proof.json')
        self.assertEqual((output/'new.txt').read_bytes(),b'new new.txt')
        self.assertEqual(snapshot(output/'source-frames'),{'new.png':b'new source-frames'})
        self.assertEqual(snapshot(output/'new-frames'),{'new.png':b'new new-frames'})
        self.assertTrue(all(not path.exists() for path in remove))
        self.assertEqual(snapshot(output/'editor-exports'),owner)
        # Retained frames were moved for recovery, rather than copied in full.
        self.assertEqual(moved_inodes,[old_directory_inode])
        self.assertFalse(list(output.glob('.promotion-recovery-*')))

    def test_second_and_last_promotion_failures_restore_the_complete_previous_set(self):
        replace=Path.replace
        for position in [1,4]:
            for error in [OSError('promotion failure'),KeyboardInterrupt()]:
                with self.subTest(position=position,error=type(error).__name__):
                    output,work,pairs,remove=self.fixture(f'{position}-{type(error).__name__}')
                    before=snapshot(output);candidate=pairs[position][0]
                    def fail(path,destination):
                        if path==candidate:raise error
                        return replace(path,destination)
                    with patch.object(Path,'replace',fail):
                        with self.assertRaises(type(error)):_promote_files(pairs,work,remove=remove)
                    self.assertEqual(snapshot(output),before)

    def test_cancellation_after_a_completed_rename_restores_original_outputs(self):
        output,work,pairs,remove=self.fixture();before=snapshot(output)
        replace=Path.replace;last_candidate=pairs[-1][0]
        def cancel_after_replace(path,destination):
            result=replace(path,destination)
            if path==last_candidate:raise KeyboardInterrupt()
            return result
        with patch.object(Path,'replace',cancel_after_replace):
            with self.assertRaises(KeyboardInterrupt):_promote_files(pairs,work,remove=remove)
        self.assertEqual(snapshot(output),before)

    def test_failure_while_detaching_a_directory_restores_removed_files_and_directory(self):
        output,work,pairs,remove=self.fixture();before=snapshot(output)
        replace=Path.replace;directory=output/'obsolete-work'
        def fail_after_backup(path,destination):
            result=replace(path,destination)
            if path==directory:raise KeyboardInterrupt()
            return result
        with patch.object(Path,'replace',fail_after_backup):
            with self.assertRaises(KeyboardInterrupt):_promote_files(pairs,work,remove=remove)
        self.assertEqual(snapshot(output),before)

    def test_all_file_backups_are_staged_before_any_output_changes(self):
        output,work,pairs,remove=self.fixture();before=snapshot(output)
        hardlink=Path.hardlink_to;calls=0
        def fail_second_backup(path,target):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('cannot back up previous receipt')
            return hardlink(path,target)
        with patch.object(Path,'hardlink_to',fail_second_backup):
            with self.assertRaisesRegex(OSError,'back up'):_promote_files(pairs,work,remove=remove)
        self.assertEqual(snapshot(output),before)

    def test_file_directory_transitions_succeed_and_roll_back(self):
        replace=Path.replace
        for failure in [False,True]:
            with self.subTest(failure=failure):
                output,work,_,_=self.fixture(str(failure));before=snapshot(output)
                pairs=[(work/'new-frames',output/'movie.mp4'),
                    (work/'new.txt',output/'source-frames'),(work/'proof.json',output/'proof.json')]
                def fail_receipt(path,destination):
                    if failure and path==pairs[-1][0]:raise OSError('receipt failure')
                    return replace(path,destination)
                with patch.object(Path,'replace',fail_receipt):
                    if failure:
                        with self.assertRaises(OSError):_promote_files(pairs,work)
                    else:_promote_files(pairs,work)
                if failure:self.assertEqual(snapshot(output),before)
                else:
                    self.assertEqual(snapshot(output/'movie.mp4'),{'new.png':b'new new-frames'})
                    self.assertEqual((output/'source-frames').read_bytes(),b'new new.txt')
                    self.assertEqual(snapshot(output/'editor-exports'),{'nested':None,'nested/owner.png':b'old editor-exports'})

    def test_removal_only_transaction_and_absent_removals(self):
        output,work,_,remove=self.fixture()
        _promote_files([],work,remove=remove)
        self.assertTrue(all(not path.exists() for path in remove))
        self.assertEqual((output/'movie.mp4').read_bytes(),b'old movie.mp4')
        self.assertTrue((output/'editor-exports/nested/owner.png').is_file())

    def test_rollback_failure_preserves_recovery_bytes_outside_work_cleanup(self):
        output,work,pairs,remove=self.fixture()
        outer=work.parent/'.outer-stage';outer.mkdir();nested=outer/work.name
        work.rename(nested)
        pairs=[(nested/candidate.relative_to(work),destination) for candidate,destination in pairs]
        work=nested
        replace=Path.replace;last_candidate=pairs[-1][0];blocked=output/'movie.mp4'
        def fail_promotion_and_one_restore(path,destination):
            if path==last_candidate:raise OSError('receipt promotion failed')
            if Path(destination)==blocked and path.parent.name=='backups':
                raise OSError('restore destination unavailable')
            return replace(path,destination)
        with patch.object(Path,'replace',fail_promotion_and_one_restore):
            with self.assertRaisesRegex(RuntimeError,'backups are preserved in') as failure:
                _promote_files(pairs,work,remove=remove)
        recoveries=[path.resolve() for path in output.glob('.promotion-recovery-*')]
        self.assertEqual(len(recoveries),1)
        recovery=recoveries[0]
        self.assertIn(str(recovery),str(failure.exception))
        shutil.rmtree(outer)
        record=json.loads((recovery/'recovery.json').read_text())
        previous=record['previousOutputs'][str(blocked)]
        self.assertEqual((recovery/'backups'/previous).read_bytes(),b'old movie.mp4')
        self.assertEqual((output/'proof.json').read_bytes(),b'old proof.json')
        self.assertEqual(snapshot(output/'source-frames'),{'nested':None,'nested/owner.png':b'old source-frames'})
        self.assertFalse((output/'new.txt').exists());self.assertFalse((output/'new-frames').exists())

    def test_recovery_storage_and_mapping_fail_before_any_output_changes(self):
        mkdir=Path.mkdir
        for phase in ['allocation','backup-folder','mapping']:
            for error in [OSError('recovery storage unavailable'),KeyboardInterrupt()]:
                with self.subTest(phase=phase,error=type(error).__name__):
                    output,work,pairs,remove=self.fixture(phase+type(error).__name__)
                    before=snapshot(output);staged=snapshot(work)
                    def fail_backup_folder(path,*args,**kwargs):
                        if path.name=='backups':raise error
                        return mkdir(path,*args,**kwargs)
                    with contextlib.ExitStack() as stack:
                        if phase=='allocation':stack.enter_context(patch('sbph.media.tempfile.mkdtemp',side_effect=error))
                        elif phase=='mapping':stack.enter_context(patch('sbph.media.dump',side_effect=error))
                        else:stack.enter_context(patch.object(Path,'mkdir',fail_backup_folder))
                        with self.assertRaises(type(error)):_promote_files(pairs,work,remove=remove)
                    self.assertEqual(snapshot(output),before)
                    self.assertEqual(snapshot(work),staged)

    def test_incomplete_rollback_requires_no_new_recovery_io(self):
        from sbph import media
        mkdtemp=media.tempfile.mkdtemp;dump=media.dump;replace=Path.replace
        for blocked_io in ['allocation','move','mapping']:
            for error in [OSError('recovery unavailable'),KeyboardInterrupt()]:
                with self.subTest(blocked_io=blocked_io,error=type(error).__name__):
                    output,work,pairs,remove=self.fixture(blocked_io+type(error).__name__)
                    last_candidate=pairs[-1][0];blocked=output/'movie.mp4';promotion_failed=False
                    def fail_promotion_and_restore(path,destination):
                        nonlocal promotion_failed
                        if path==last_candidate:
                            promotion_failed=True;raise OSError('receipt promotion failed')
                        if Path(destination)==blocked and path.parent.name=='backups':
                            raise OSError('restore destination unavailable')
                        return replace(path,destination)
                    def recovery_allocation(*args,**kwargs):
                        if promotion_failed:raise error
                        return mkdtemp(*args,**kwargs)
                    def recovery_mapping(*args,**kwargs):
                        if promotion_failed:raise error
                        return dump(*args,**kwargs)
                    with contextlib.ExitStack() as stack:
                        stack.enter_context(patch.object(Path,'replace',fail_promotion_and_restore))
                        if blocked_io=='allocation':stack.enter_context(patch('sbph.media.tempfile.mkdtemp',side_effect=recovery_allocation))
                        elif blocked_io=='mapping':stack.enter_context(patch('sbph.media.dump',side_effect=recovery_mapping))
                        else:stack.enter_context(patch.object(Path,'rename',side_effect=error))
                        with self.assertRaisesRegex(RuntimeError,'backups are preserved in') as failure:
                            _promote_files(pairs,work,remove=remove)
                    recovery=next(output.glob('.promotion-recovery-*'))
                    self.assertIn(str(recovery.resolve()),str(failure.exception))
                    shutil.rmtree(work)
                    record=json.loads((recovery/'recovery.json').read_text())
                    previous=record['previousOutputs'][str(blocked)]
                    self.assertEqual((recovery/'backups'/previous).read_bytes(),b'old movie.mp4')

    def test_cleanup_failure_or_cancellation_does_not_undo_a_complete_result(self):
        replace=Path.replace;rmtree=shutil.rmtree
        for rollback in [False,True]:
            for error in [OSError('cleanup failed'),KeyboardInterrupt()]:
                with self.subTest(rollback=rollback,error=type(error).__name__):
                    output,work,pairs,remove=self.fixture(str(rollback)+type(error).__name__)
                    before=snapshot(output);last_candidate=pairs[-1][0]
                    def fail_promotion(path,destination):
                        if rollback and path==last_candidate:raise OSError('promotion failure')
                        return replace(path,destination)
                    def fail_cleanup(path,*args,**kwargs):
                        if Path(path).name.startswith('.promotion-recovery-'):
                            # Cleanup can fail after it has already removed old
                            # backups. The new set is committed at this point.
                            if not rollback:rmtree(Path(path)/'backups')
                            raise error
                        return rmtree(path,*args,**kwargs)
                    warnings=io.StringIO()
                    with patch.object(Path,'replace',fail_promotion),patch('sbph.media.shutil.rmtree',side_effect=fail_cleanup),contextlib.redirect_stderr(warnings):
                        if rollback:
                            with self.assertRaisesRegex(OSError,'promotion failure'):_promote_files(pairs,work,remove=remove)
                        else:_promote_files(pairs,work,remove=remove)
                    recovery=next(output.glob('.promotion-recovery-*'))
                    self.assertIn(str(recovery.resolve()),warnings.getvalue())
                    self.assertIn('cleanup incomplete',warnings.getvalue())
                    if rollback:
                        visible={name:value for name,value in snapshot(output).items()
                            if not name.split('/')[0].startswith('.promotion-recovery-')}
                        self.assertEqual(visible,before)
                    else:
                        self.assertEqual((output/'movie.mp4').read_bytes(),b'new movie.mp4')
                        self.assertEqual((output/'proof.json').read_bytes(),b'new proof.json')
                        self.assertEqual(snapshot(output/'source-frames'),{'new.png':b'new source-frames'})
                        self.assertTrue(all(not path.exists() for path in remove))

    def test_overlapping_or_missing_paths_are_rejected_before_changes(self):
        cases=['duplicate','nested-output','staging-output','staging-ancestor',
            'duplicate-removal','nested-removal','outside-candidate','nested-candidate','missing-candidate','missing-parent']
        for case in cases:
            with self.subTest(case=case):
                output,work,pairs,remove=self.fixture(case)
                if case=='duplicate':pairs=[(work/'movie.mp4',output/'movie.mp4'),(work/'proof.json',output/'movie.mp4')]
                elif case=='nested-output':pairs=[(work/'source-frames',output/'source-frames'),(work/'new.txt',output/'source-frames/nested/extra')]
                elif case=='staging-output':pairs=[(work/'movie.mp4',work/'new-output')]
                elif case=='staging-ancestor':pairs=[(work/'movie.mp4',work.parent)]
                elif case=='duplicate-removal':remove.append(pairs[0][1])
                elif case=='nested-removal':remove.append(output/'source-frames/nested')
                elif case=='outside-candidate':pairs=[(output/'movie.mp4',output/'other')]
                elif case=='nested-candidate':pairs=[(work/'source-frames',output/'frames'),(work/'source-frames/new.png',output/'image')]
                elif case=='missing-candidate':pairs=[(work/'missing',output/'movie.mp4')]
                elif case=='missing-parent':pairs=[(work/'movie.mp4',output/'missing/movie.mp4')]
                before=snapshot(output);staged=snapshot(work)
                with self.assertRaises(ValueError):_promote_files(pairs,work,remove=remove)
                self.assertEqual(snapshot(output),before)
                self.assertEqual(snapshot(work),staged)

    def test_symlink_outputs_and_candidates_are_refused_without_following_them(self):
        for candidate_link in [False,True]:
            with self.subTest(candidate_link=candidate_link):
                output,work,_,_=self.fixture(str(candidate_link))
                owner=output/'movie.mp4';before=owner.read_bytes()
                if candidate_link:
                    candidate=work/'linked';candidate.symlink_to(owner)
                    pairs=[(candidate,output/'replacement')]
                else:
                    destination=output/'linked';destination.symlink_to(owner)
                    pairs=[(work/'movie.mp4',destination)]
                with self.assertRaisesRegex(ValueError,'symlink'):_promote_files(pairs,work)
                self.assertEqual(owner.read_bytes(),before)
                self.assertFalse((output/'replacement').exists())


if __name__=='__main__':unittest.main()
