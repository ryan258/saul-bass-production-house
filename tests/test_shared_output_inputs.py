"""Shared output/input collision checks before any encoder or output writes."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import ffmpeg

from sbph.media import assemble,mux_master,render_picture,render_shots
from sbph.preview import preview


def snapshot(root):
    return {path.relative_to(root).as_posix():None if path.is_dir() else path.read_bytes()
        for path in root.rglob('*')}


class SharedOutputInputs(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.output=self.root/'production'
        self.output.mkdir()
        for name in ['audio.wav','film.cjs','production.json','data/edit.json']:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(('original '+name).encode())
        self.p=SimpleNamespace(root=self.root,output=self.output,audio=self.root/'audio.wav',
            driver=self.root/'film.cjs',config=self.root/'production.json',data={},
            edit={'scenes':[{'id':'one','kind':'test','start':0,'end':6}]},
            frames=6,fps=30,width=16,height=16,
            source_inventory=Mock(side_effect=AssertionError('No extra source inventory for collision checks')))
        self.picture=self.root/'picture.mp4';self.picture.write_bytes(b'original picture')

    def assert_refused_without_writes(self,operation):
        before=snapshot(self.root)
        with patch('sbph.media._run_ffmpeg') as encoder,patch('sbph.media.subprocess.Popen') as producer:
            with self.assertRaisesRegex(ValueError,'protected input'):operation()
        encoder.assert_not_called();producer.assert_not_called()
        self.p.source_inventory.assert_not_called()
        self.assertEqual(snapshot(self.root),before)

    def test_picture_and_mux_cannot_replace_original_audio(self):
        for mode in ['picture','mux']:
            with self.subTest(mode=mode):
                operation=(lambda:render_picture(self.p,self.p.audio,0,6)) if mode=='picture' else \
                    (lambda:mux_master(self.p,self.picture,self.p.audio))
                self.assert_refused_without_writes(operation)

    def test_mux_cannot_replace_its_picture_input_including_a_symlink_alias(self):
        alias=self.root/'picture-alias.mp4';alias.symlink_to(self.picture)
        for destination in [self.picture,alias]:
            with self.subTest(destination=destination):
                self.assert_refused_without_writes(lambda:mux_master(self.p,self.picture,destination))

    def test_proof_and_receipt_cannot_replace_original_audio(self):
        for name in ['proof.mp4','proof.json']:
            with self.subTest(name=name):
                self.p.audio=self.output/name;self.p.audio.write_bytes(b'original source recording')
                self.assert_refused_without_writes(lambda:preview(self.p,0,.2))

    def test_proof_resolves_source_audio_alias_before_rendering(self):
        original=self.output/'proof.mp4';original.write_bytes(b'original source recording')
        self.p.audio=self.root/'audio-link.wav';self.p.audio.symlink_to(original)
        self.assert_refused_without_writes(lambda:preview(self.p,0,.2))

    def test_assembly_cannot_replace_original_audio(self):
        self.p.audio=self.output/'assembly.mp4';self.p.audio.write_bytes(b'original source recording')
        with patch('sbph.validation.validate_shot_set') as validate:
            self.assert_refused_without_writes(lambda:assemble(self.p))
        validate.assert_not_called()

    def test_shot_and_manifest_cannot_replace_original_audio(self):
        for name in ['shots.json','shots/one-test.mp4']:
            with self.subTest(name=name):
                self.p.audio=self.output/name;self.p.audio.parent.mkdir(parents=True,exist_ok=True)
                self.p.audio.write_bytes(b'original source recording')
                self.assert_refused_without_writes(lambda:render_shots(self.p))

    def test_shot_directory_alias_cannot_redirect_rendering_over_original_audio(self):
        originals=self.root/'originals';originals.mkdir()
        self.p.audio=originals/'one-test.mp4';self.p.audio.write_bytes(b'original source recording')
        (self.output/'shots').symlink_to(originals,target_is_directory=True)
        self.assert_refused_without_writes(lambda:render_shots(self.p))

    def test_known_driver_configuration_and_edit_cannot_be_proof_destinations(self):
        for source in ['driver','config','edit']:
            with self.subTest(source=source):
                destination=self.output/('proof.mp4' if source=='driver' else 'proof.json')
                destination.write_bytes(('original '+source).encode())
                if source=='edit':self.p.data['edit']='production/proof.json'
                else:setattr(self.p,source,destination)
                self.assert_refused_without_writes(lambda:preview(self.p,0,.2))
                self.p.driver=self.root/'film.cjs';self.p.config=self.root/'production.json';self.p.data={}

    def test_declared_sources_cannot_be_replaced_by_generated_destinations(self):
        for declaration in ['source_files','source_globs']:
            with self.subTest(declaration=declaration):
                source=self.root/'originals/reference.mp4';source.parent.mkdir(exist_ok=True);source.write_bytes(b'original asset')
                self.p.data={declaration:['originals/reference.mp4' if declaration=='source_files' else 'originals/**/*']}
                self.assert_refused_without_writes(lambda:render_picture(self.p,source,0,6))

    def test_explicit_original_inside_output_is_still_protected(self):
        source=self.output/'proof.mp4';source.write_bytes(b'original supplied asset')
        self.p.data={'source_files':['production/proof.mp4'],'source_globs':['**/*']}
        self.assert_refused_without_writes(lambda:preview(self.p,0,.2))

    def test_mux_allows_distinct_files_with_the_same_basename(self):
        output=self.output/self.picture.name
        original=(self.picture.read_bytes(),self.p.audio.read_bytes())
        def encode(graph):
            candidate=Path([arg for arg in ffmpeg.compile(graph) if arg.endswith('.mp4')][-1])
            candidate.write_bytes(b'verified encoded delivery')
        with patch('sbph.media._run_ffmpeg',side_effect=encode),patch('sbph.media._validate_video'),patch('sbph.verify.project_audio_comparison'):
            mux_master(self.p,self.picture,output)
        self.assertEqual(output.read_bytes(),b'verified encoded delivery')
        self.assertEqual((self.picture.read_bytes(),self.p.audio.read_bytes()),original)


if __name__=='__main__':unittest.main()
