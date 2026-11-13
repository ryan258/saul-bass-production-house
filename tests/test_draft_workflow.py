import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from sbph import workflow as flow
from sbph.drafts import animatic_parameters,revision_parameters,render,artifact_status
from sbph.media import probe
from sbph.project import FRAMEWORK,binary,sha
from workflow_fixtures import project


class DraftWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.p=project(self.temp.name)
        self.p.output.mkdir()
        self.proof=self.p.output/'proof.mp4';self.proof.write_bytes(b'preserved proof')
        self.delivery=self.p.output/'assembly.mp4';self.delivery.write_bytes(b'preserved delivery')
        self.manifest=self.p.output/'shots.json';self.manifest.write_bytes(b'preserved manifest')
        self.original={str(f):sha(f) for f in [self.proof,self.delivery,self.manifest,self.p.audio]}

    def unchanged(self):
        self.assertEqual({file:sha(file) for file in self.original},self.original)

    def test_placeholder_and_storyboard_animatic_works_without_renderer(self):
        self.p.driver.unlink()
        image=self.p.root/'board.png';Image.new('RGB',(80,45),'red').save(image)
        self.p.edit['scenes'][1]['storyboard']='board.png'
        (self.p.root/'data/edit.json').write_text(json.dumps(self.p.edit))
        flow.set_intent(self.p,'approach',{'goal':'Reach the other side','change':'The gap blocks progress'})
        record=render(self.p,animatic_parameters(self.p,width=320))
        self.assertTrue(record['draft']);self.assertEqual(record['frames'],96)
        self.assertEqual([s['mode'] for s in record['sections']],['placeholder','storyboard','placeholder'])
        file=self.p.root/record['file'];self.assertEqual(probe(file)['streams'][0]['nb_frames'],'96')
        raw=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(file),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'])
        with Image.open(io.BytesIO(raw)) as decoded:
            # The visible draft banner changes an otherwise plain placeholder.
            colors=decoded.convert('RGB').crop((0,0,320,52)).getcolors(320*52)
            self.assertGreater(len(colors),2)
        self.assertEqual(artifact_status(self.p,flow.read_state(self.p,'artifacts')['items'][0])['status'],'current')
        flow.set_intent(self.p,'approach',{'goal':'A revised goal'})
        self.assertEqual(artifact_status(self.p,flow.read_state(self.p,'artifacts')['items'][0])['status'],'stale')
        self.unchanged()

    def test_renderer_animatic_samples_only_one_frame_per_shot(self):
        with self.p.driver.open('a') as stream:
            stream.write("\nconst originalFrame=module.exports.frame;module.exports.frame=n=>{fs.appendFileSync(path.join(__dirname,'../samples.txt'),String(n)+'\\n');return originalFrame(n)};\n")
        record=render(self.p,animatic_parameters(self.p,width=320,render_stills=True))
        self.assertEqual((self.p.root/'samples.txt').read_text().splitlines(),['15','47','79'])
        self.assertTrue(all(s['mode']=='renderer-still' for s in record['sections']))
        self.unchanged()

    def test_note_selected_revision_has_context_matching_audio_and_unique_outputs(self):
        flow.add_note(self.p,'Hold the turn','bridge','40f')
        params=revision_parameters(self.p,note_id='N1',before=.25,after=.25,width=320)
        self.assertEqual((params['start'],params['frames']),(26,44))
        first=render(self.p,params);second=render(self.p,params)
        self.assertNotEqual(first['file'],second['file'])
        self.assertEqual(first['parameters']['noteId'],'N1')
        self.assertEqual(probe(self.p.root/first['file'])['streams'][0]['nb_frames'],'44')
        self.assertGreater(first['audio']['monoCorrelationAt16k'],.995)
        self.assertTrue(all(abs(w['estimatedOffsetSamplesAt16k'])<=1 for w in first['audio']['offsetWindows']))
        flow.reanchor_note(self.p,'N1','arrival')
        self.assertEqual(artifact_status(self.p,flow.read_state(self.p,'artifacts')['items'][0])['status'],'stale')
        with self.assertRaisesRegex(ValueError,'anchor changed'):render(self.p,params)
        self.unchanged()

    def test_bad_context_long_window_and_stale_note_do_not_render(self):
        for arguments in [{'identifier':'missing'},{'identifier':'bridge','before':float('nan')},{'identifier':'bridge','start':0,'duration':.1}]:
            with self.subTest(arguments=arguments),self.assertRaises(ValueError):revision_parameters(self.p,**arguments)
        flow.add_note(self.p,'Hold','bridge','40f');self.p.fps=30
        with self.assertRaisesRegex(ValueError,'rate_changed'):revision_parameters(self.p,note_id='N1')
        self.p.fps=24;self.p.frames=1000;self.p.edit['scenes'][0]['end']=1000
        with self.assertRaisesRegex(ValueError,'30 seconds'):revision_parameters(self.p,identifier='approach')
        params=revision_parameters(self.p,identifier='approach',start=0,duration=1)
        self.assertEqual(params['frames'],24);self.unchanged()

    def test_changed_inputs_fail_before_promoting_a_draft(self):
        def changed(p,params,candidate,work,cards):
            candidate.write_bytes(b'not encoded')
            flow.set_intent(p,'bridge',{'goal':'Changed during rendering'})
        video={'codec_type':'video','nb_frames':'96','avg_frame_rate':'24/1','width':320,'height':232}
        with patch('sbph.drafts.encode',side_effect=changed),patch('sbph.drafts.probe',return_value={'streams':[video]}),patch('sbph.verify.audio_comparison',return_value={}),patch('sbph.drafts._run_ffmpeg'):
            with self.assertRaisesRegex(RuntimeError,'inputs changed'):render(self.p,animatic_parameters(self.p,width=320))
        self.assertFalse(list((self.p.output/'drafts').glob('*.mp4')))
        self.assertFalse(flow.state_path(self.p,'artifacts').exists());self.unchanged()

    def test_cli_draft_and_note_preview_resume_as_current_artifacts(self):
        env={**os.environ,'SBPH_HOME':str(FRAMEWORK),'PYTHONDONTWRITEBYTECODE':'1'}
        def run(*arguments):
            return json.loads(subprocess.check_output([str(self.p.root/'make'),*arguments,'--json'],env=env,text=True,stderr=subprocess.STDOUT))
        run('intent','--shot','bridge','--goal','Connect the track')
        note=run('note','--shot','bridge','--text','Review this turn')
        run('resume','--note',note['id'])
        animatic=run('animatic','--width','320')
        revision=run('revision','--note',note['id'],'--before','0.25','--after','0.25','--width','320')
        self.assertNotEqual(animatic['file'],revision['file'])
        state=run('resume')
        self.assertEqual([r['status'] for r in state['recentDrafts']],['current','current'])
        self.assertIn('--note N1',state['nextAction']['command']);self.unchanged()


if __name__=='__main__':unittest.main()
