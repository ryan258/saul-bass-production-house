import unittest,json,tempfile
from pathlib import Path
import opentimelineio as otio
from sbph.project import Project

class TimelineContract(unittest.TestCase):
    def project(self,scenes):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);r=Path(tmp.name)
        (r/'audio.wav').write_bytes(b'fixture, not decoded by the model validator')
        edit={'title':'Fixture','fps':30,'frames':60,'width':1920,'height':1080,'scenes':scenes}
        (r/'edit.json').write_text(json.dumps(edit));(r/'production.json').write_text(json.dumps({'edit':'edit.json','audio':'audio.wav','handles':12}))
        return r/'production.json'
    def test_gap_rejected(self):
        with self.assertRaisesRegex(ValueError,'gap'):
            Project.load(self.project([{'id':'01','start':0,'end':29},{'id':'02','start':30,'end':60}]))
    def test_duplicate_id_rejected(self):
        with self.assertRaisesRegex(ValueError,'unique'):
            Project.load(self.project([{'id':'01','start':0,'end':30},{'id':'01','start':30,'end':60}]))
    def test_handles_are_available_media_not_added_timeline_duration(self):
        RT=otio.opentime.RationalTime;TR=otio.opentime.TimeRange
        track=otio.schema.Track(kind=otio.schema.TrackKind.Video)
        for duration in [29,31]:
            track.append(otio.schema.Clip(media_reference=otio.schema.ExternalReference(target_url='file:///fixture.mp4',available_range=TR(RT(0,30),RT(duration+24,30))),source_range=TR(RT(12,30),RT(duration,30))))
        self.assertEqual(track.duration().value,60)
        self.assertEqual(track[1].range_in_parent().start_time.value,29)
        self.assertEqual(track[0].media_reference.available_range.duration.value,53)


class StoryEvents(unittest.TestCase):
    edit={'frames':100,'scenes':[
        {'id':'01','name':'Start','accents':[{'frame':20,'meaning':'Grip stops'}],'pulses':[{'frame':20},{'frame':30}]},
        {'id':'02','name':'Next','accents':[{'frame':70}]}]}

    def test_authored_events_win_even_when_empty(self):
        from sbph.validation import story_events
        self.assertEqual(story_events({**self.edit,'events':[]}),[])
        self.assertEqual(story_events({**self.edit,'events':[{'id':'x'}]}),[{'id':'x'}])

    def test_native_accents_and_impacts_become_ordered_markers_without_duplicates(self):
        from sbph.validation import story_events
        rows=story_events(self.edit)
        self.assertEqual([(r['frame'],r['basis']) for r in rows],[(20,'accent'),(30,'action'),(70,'accent')])
        self.assertEqual(rows[0]['id'],'01 / Grip stops');self.assertEqual(rows[2]['meaning'],'Selected accent')

    def test_plain_edits_get_no_markers_and_bad_frames_are_refused(self):
        from sbph.validation import story_events
        self.assertEqual(story_events({'frames':10,'scenes':[{'id':'a','name':'A'}]}),[])
        with self.assertRaisesRegex(ValueError,'inside the edit'):story_events({'frames':10,'scenes':[{'id':'a','name':'A','accents':[{'frame':10}]}]})


if __name__=='__main__':unittest.main()
