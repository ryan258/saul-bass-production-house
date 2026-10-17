"""Run the shipped example outside the checkout, using its documented launcher."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

import opentimelineio as otio
from sbph.project import FRAMEWORK,binary,sha


class SecondFilm(unittest.TestCase):
    def test_copied_example_completes_without_unit9_or_external_assets(self):
        with tempfile.TemporaryDirectory(prefix='sbph-second-film-') as folder:
            film=Path(folder)/'A second film'
            shutil.copytree(FRAMEWORK/'examples/signal',film,ignore=shutil.ignore_patterns('production','audio','__pycache__'))
            environment={**os.environ,'SBPH_HOME':str(FRAMEWORK),'PYTHONDONTWRITEBYTECODE':'1'}
            for key in ['UNIT9_NODE_MODULES','SBPH_NODE_MODULES','NODE_PATH']:environment.pop(key,None)
            output=subprocess.check_output([str(film/'make'),'build'],cwd=folder,env=environment,text=True,stderr=subprocess.STDOUT)
            self.assertIn('Media checks passed',output)
            self.assertIn('Assembly conforms',output)
            with wave.open(str(film/'audio/source.wav'),'rb') as stream:
                self.assertEqual((stream.getframerate(),stream.getnchannels(),stream.getnframes()),(48000,2,192000))
            project=film/'production'
            report=json.loads((project/'media-verification.json').read_text())
            self.assertEqual(report['profile'],'generic')
            self.assertEqual(report['video']['nb_frames'],'96')
            self.assertEqual(report['video']['avg_frame_rate'],'24/1')
            self.assertEqual(len(report['decodedShotFrames']),3)
            self.assertEqual(len(report['contactSheets']),1)
            self.assertEqual(report['pixelComparisons'],[])
            self.assertTrue(all(Path(name).is_file() for name in report['contactSheets']))
            conform=json.loads((project/'assembly-verification.json').read_text())
            self.assertEqual(len(conform['comparedFrames']),9)
            self.assertLess(conform['maximumRgbMae'],2)
            timeline=otio.adapters.read_from_file(str(project/'human-edit.otio'))
            self.assertEqual(timeline.duration().value,96)
            self.assertEqual(len(timeline.video_tracks()[0]),3)
            self.assertEqual([clip.source_range.start_time.value for clip in timeline.video_tracks()[0]],[4,4,4])
            for track in timeline.tracks:
                for clip in track:
                    self.assertNotIn('unit-9',clip.media_reference.target_url)
            # Adding a review reference must not require another picture render.
            manifest_hash=sha(project/'shots.json')
            frame=project/'opening.png'
            subprocess.run([binary('ffmpeg'),'-v','error','-i',str(project/'proof.mp4'),'-vf','scale=in_color_matrix=bt709:in_range=tv:out_range=pc:flags=accurate_rnd+full_chroma_int','-frames:v','1','-update','1',str(frame)],check=True)
            config=json.loads((film/'production.json').read_text())
            config['verification']={'reference_frames':[{'frame':0,'file':'production/opening.png'}]}
            (film/'production.json').write_text(json.dumps(config))
            subprocess.check_output([str(film/'make'),'check'],cwd=folder,env=environment,stderr=subprocess.STDOUT)
            self.assertEqual(sha(project/'shots.json'),manifest_hash)
            checked=json.loads((project/'media-verification.json').read_text())
            self.assertEqual(len(checked['pixelComparisons']),1)
            # Preparation is repeatable and protects an existing changed source.
            before=sha(film/'audio/source.wav')
            subprocess.check_output([str(film/'make'),'prepare'],cwd=folder,env=environment)
            self.assertEqual(sha(film/'audio/source.wav'),before)
            (film/'audio/source.wav').write_bytes(b'owner replacement')
            failed=subprocess.run([str(film/'make'),'prepare'],cwd=folder,env=environment,capture_output=True)
            self.assertNotEqual(failed.returncode,0)
            self.assertEqual((film/'audio/source.wav').read_bytes(),b'owner replacement')


if __name__=='__main__':unittest.main()
