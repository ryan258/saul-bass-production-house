import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import numpy as np
from PIL import Image
from sbph.assembly_check import check as conform
from sbph.delivery import delivery_path,reference_path
from sbph.media import BSF,probe
from sbph.project import binary,dump,sha
from sbph.review import contact_sheets
from sbph.verify import project_audio_comparison,verify
from sbph import unit9_checks


class GenericVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.media.cleanup)
        cls.source=Path(cls.media.name)/'source.wav';cls.movie=Path(cls.media.name)/'movie.mp4'
        time=np.arange(24000)/48000
        samples=(np.sin(2*np.pi*(100*time+30*time*time))*12000).astype('<i2')
        with wave.open(str(cls.source),'wb') as stream:
            stream.setparams((2,2,48000,0,'NONE','not compressed'));stream.writeframes(np.column_stack((samples,samples)).tobytes())
        subprocess.run([binary('ffmpeg'),'-v','error','-f','lavfi','-i','color=red:s=64x48:r=24','-i',str(cls.source),'-frames:v','12','-t','0.5','-vf','scale=out_color_matrix=bt709:out_range=tv','-c:v','libx264','-pix_fmt','yuv420p','-bsf:v',BSF,'-c:a','aac','-b:a','320k','-color_primaries','bt709','-color_trc','iec61966-2-1','-colorspace','bt709','-color_range','tv',str(cls.movie)],check=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name).resolve();output=root/'production';output.mkdir()
        shutil.copy2(self.source,root/'audio.wav');shutil.copy2(self.movie,output/'assembly.mp4')
        self.p=SimpleNamespace(root=root,output=output,audio=root/'audio.wav',data={},fps=24,frames=12,width=64,height=48,handles=2,
            edit={'title':'UNIT 9','scenes':[{'id':'one','name':'First','start':0,'end':6},{'id':'two','name':'Second','start':6,'end':12}]},
            source_inventory=lambda:('fixture',[]),public_path=lambda path:Path(path).resolve())
        self.records={'sourceFingerprint':'fixture','shots':{'one':{'frames':10},'two':{'frames':10}}}
        gate=patch('sbph.validation.validate_shot_set',return_value=self.records);gate.start();self.addCleanup(gate.stop)

    def check(self,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):return verify(self.p,**kwargs)

    def test_generic_check_needs_no_unit9_files_even_with_unit9_title(self):
        report=self.check()
        self.assertEqual(report['profile'],'generic');self.assertIsNone(report['profileChecks'])
        self.assertEqual(report['pixelComparisons'],[])
        self.assertEqual(len(report['decodedShotFrames']),2)
        self.assertEqual(report['delivery'],str(self.p.output/'assembly.mp4'))
        self.assertTrue(Path(report['contactSheets'][0]).is_file())
        self.assertFalse((self.p.root/'review').exists())
        self.assertFalse((self.p.root/'assets').exists())

    def test_missing_reference_picture_does_not_replace_report(self):
        report=self.p.output/'media-verification.json';report.write_bytes(b'previous report')
        self.p.data={'verification':{'reference_frames':[{'frame':0,'file':'missing.png'}]}}
        with self.assertRaisesRegex(ValueError,'missing'):self.check()
        self.assertEqual(report.read_bytes(),b'previous report')

    def test_configured_picture_reference_is_actually_compared(self):
        from sbph.review import decode_frames
        frames=self.p.root/'frames';frames.mkdir()
        file=decode_frames(self.p.output/'assembly.mp4',[0],frames)[0]
        reference=self.p.root/'reference.png';shutil.copy2(file,reference)
        self.p.data={'verification':{'reference_frames':[{'frame':0,'file':'reference.png'}]}}
        report=self.check();self.assertEqual(len(report['pixelComparisons']),1)
        self.assertEqual(report['referenceHashes']['reference.png'],sha(reference))
        Image.new('RGB',(64,48),'blue').save(reference)
        before=(self.p.output/'media-verification.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'comparison failed'):self.check()
        self.assertEqual((self.p.output/'media-verification.json').read_bytes(),before)

    def test_bad_delivery_metadata_fails_before_audio_decode(self):
        original=probe(self.p.output/'assembly.mp4')
        for kind,key,value in [('video','width',128),('video','nb_frames','11'),('video','avg_frame_rate','30/1'),('video','color_transfer','bt709'),('audio','channels',1),('audio','duration','1.0')]:
            with self.subTest(key=key):
                metadata=copy.deepcopy(original);next(s for s in metadata['streams'] if s['codec_type']==kind)[key]=value
                with patch('sbph.verify.probe',return_value=metadata),patch('sbph.verify.audio_comparison') as audio:
                    with self.assertRaises(ValueError):self.check()
                    audio.assert_not_called()

    def test_invalid_profile_and_reference_frame_fail_clearly(self):
        with self.assertRaisesRegex(ValueError,'Unknown verification profile'):self.check(profile='unknown')
        self.p.data={'verification':{'reference_frames':[{'frame':12,'file':'not-needed.png'}]}}
        with self.assertRaisesRegex(ValueError,'inside the edit'):self.check()

    def test_unit9_profile_requires_explicit_selection_and_can_be_overridden(self):
        self.p.data={'verification':{'profile':'unit9'}}
        with patch('sbph.unit9_checks.reference_frames',return_value=[]),patch('sbph.unit9_checks.inspect',return_value={'profile':'unit9'}) as inspect:
            report=self.check();self.assertEqual(report['profileChecks'],{'profile':'unit9'});inspect.assert_called_once()
            inspect.reset_mock();self.check(profile='generic');inspect.assert_not_called()

    def test_delivery_and_reference_roles_are_explicit(self):
        self.assertEqual(delivery_path(self.p),self.p.output/'assembly.mp4')
        with self.assertRaisesRegex(ValueError,'explicit reference'):reference_path(self.p)
        self.p.data={'reference':'production/assembly.mp4'}
        with self.assertRaisesRegex(ValueError,'separate movie'):reference_path(self.p)
        alias=self.p.root/'alias.mp4';os.link(self.p.output/'assembly.mp4',alias)
        with self.assertRaisesRegex(ValueError,'separate movie'):reference_path(self.p,'alias.mp4')
        legacy=self.p.root/'legacy.mp4';shutil.copy2(self.movie,legacy)
        self.p.data={'master':'legacy.mp4'}
        self.assertEqual(delivery_path(self.p),legacy);self.assertEqual(reference_path(self.p),legacy)

    def test_conform_supports_non_unit9_rate_dimensions_and_reference(self):
        reference=self.p.root/'independent.mp4';shutil.copy2(self.movie,reference)
        self.p.data={'reference':'independent.mp4'}
        with contextlib.redirect_stdout(io.StringIO()):report=conform(self.p)
        self.assertEqual(report['sampleSize'],[512,384]);self.assertEqual(len(report['comparedFrames']),6)
        self.assertEqual(report['referenceSha256'],sha(reference))

    def test_conform_source_changes_do_not_replace_prior_report(self):
        reference=self.p.root/'independent.mp4';shutil.copy2(self.movie,reference)
        self.p.data={'reference':'independent.mp4'}
        receipt=self.p.output/'assembly-verification.json';receipt.write_bytes(b'previous conform report')
        source=self.p.audio.read_bytes()
        initial_hash=sha(self.p.audio)
        for change in ['before-audio','after-audio','framework']:
            with self.subTest(change=change):
                self.p.audio.write_bytes(source)
                self.records['sourceFingerprint']=initial_hash
                self.p.source_inventory=lambda:(sha(self.p.audio),[])
                def comparison(p,movie):
                    if change=='before-audio':p.audio.write_bytes(source+b'changed unused tail')
                    result=project_audio_comparison(p,movie)
                    if change=='after-audio':p.audio.write_bytes(source+b'changed unused tail')
                    if change=='framework':p.source_inventory=lambda:('changed framework',[])
                    return result
                with patch('sbph.assembly_check.project_audio_comparison',side_effect=comparison):
                    with self.assertRaisesRegex(RuntimeError,'Build sources changed during conform'):
                        conform(self.p)
                self.assertEqual(receipt.read_bytes(),b'previous conform report')


class ReviewPagination(unittest.TestCase):
    def test_every_shot_is_paginated_beyond_sixty(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);frame=folder/'frame.png';Image.new('RGB',(32,24),'red').save(frame)
            p=SimpleNamespace(width=32,height=24,fps=24)
            shots=[{'id':str(i),'name':'Shot','frame':i} for i in range(61)]
            sheets=contact_sheets(p,shots,{i:frame for i in range(61)},folder)
            self.assertEqual(len(sheets),4)
            with Image.open(sheets[-1]) as image:self.assertEqual(image.height,412)


class Unit9Profile(unittest.TestCase):
    def test_explicit_profile_preserves_geometry_and_asset_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'assets/webp').mkdir(parents=True);(root/'review').mkdir()
            Image.new('RGBA',(8,8),(255,0,0,128)).save(root/'assets/webp/prop.webp',lossless=True)
            p=SimpleNamespace(root=root,fps=30)
            rows=[{'frame':1164,'lever':{'grip':[0,300]}},{'frame':1233,'lever':{'grip':[0,0]}},{'frame':7000,'seam':{'gap':28}}]
            dump(root/'review/geometry-samples.json',rows)
            self.assertEqual(unit9_checks.inspect(p)['modelGeometry']['finalGapMinimumAt1280Stage'],28)
            rows[-1]['seam']['gap']=0;dump(root/'review/geometry-samples.json',rows)
            with self.assertRaisesRegex(ValueError,'gap failed'):unit9_checks.inspect(p)


if __name__=='__main__':unittest.main()
