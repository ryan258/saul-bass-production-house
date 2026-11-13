import copy,unittest
from sbph.motion_film import effective_plan,validate_plan


class MotionFilmContract(unittest.TestCase):
    def setUp(self):
        self.plan={'fps':30,'frames':90,'scenes':[
            {'id':'01','start':0,'end':45,'animations':[{'signal':'lever','startFrame':3,'endFrame':30,'startEvent':'pull','endEvent':'stop'}],'accents':[{'frame':30}]},
            {'id':'02','start':45,'end':90,'animations':[],'accents':[]}]}
        self.meta={'timeEvents':[{'name':name,'targetTime':frame/30} for name,frame in [('pull',3),('stop',30),('cut-02',45),('cut-end',90)]]}

    def test_complete_edit_and_signal_range(self):
        validate_plan(self.plan,self.meta)

    def test_narration_cut_desync_rejected(self):
        self.meta['timeEvents'][2]['targetTime']=44/30
        with self.assertRaisesRegex(ValueError,'narration edit'):validate_plan(self.plan,self.meta)

    def test_competing_tweens_rejected(self):
        action=copy.deepcopy(self.plan['scenes'][0]['animations'][0]);action.update(startFrame=15,endFrame=35,startEvent='other-start',endEvent='other-end')
        self.plan['scenes'][0]['animations'].append(action)
        self.meta['timeEvents'].extend([{'name':'other-start','targetTime':.5},{'name':'other-end','targetTime':35/30}])
        with self.assertRaisesRegex(ValueError,'compete'):validate_plan(self.plan,self.meta)

    def test_action_across_cut_rejected(self):
        self.plan['scenes'][0]['animations'][0]['endFrame']=46
        with self.assertRaisesRegex(ValueError,'boundary'):validate_plan(self.plan,self.meta)

    def test_saved_editor_timing_drives_effective_edit(self):
        original=copy.deepcopy(self.plan)
        self.meta['timeEvents'][1]['targetTime']=32/30
        self.meta['timeEvents'][2]['targetTime']=46/30
        resolved=effective_plan(self.plan,self.meta)
        validate_plan(resolved,self.meta)
        self.assertEqual(resolved['scenes'][0]['animations'][0]['endFrame'],32)
        self.assertEqual(resolved['scenes'][0]['end'],46)
        self.assertEqual(resolved['scenes'][1]['start'],46)
        self.assertEqual(self.plan,original)

    def test_editor_cannot_shorten_original_audio(self):
        self.meta['timeEvents'][-1]['targetTime']=89/30
        with self.assertRaisesRegex(ValueError,'original audio duration'):effective_plan(self.plan,self.meta)

    def add_pulse(self,frame=33,end=40):
        self.plan['scenes'][0]['pulses']=[{'frame':frame,'endFrame':end,'startEvent':'hit'}]
        self.meta['timeEvents'].append({'name':'hit','targetTime':frame/30})

    def test_saved_pulse_cue_keeps_duration_and_obeys_shot_boundary(self):
        self.add_pulse();self.meta['timeEvents'][-1]['targetTime']=40/30
        updated=effective_plan(self.plan,self.meta)
        self.assertEqual((updated['scenes'][0]['pulses'][0]['frame'],updated['scenes'][0]['pulses'][0]['endFrame']),(40,47))
        with self.assertRaisesRegex(ValueError,'Pulse crosses'):validate_plan(updated,self.meta)

    def test_pulse_invalid_ranges_types_events_and_competing_signal_are_rejected(self):
        self.add_pulse();validate_plan(self.plan,self.meta)
        original=copy.deepcopy(self.plan)
        for patch in [{'endFrame':33},{'endFrame':46},{'frame':True},{'startEvent':'missing'},{'signal':'head'}]:
            with self.subTest(patch=patch):
                self.plan=copy.deepcopy(original);self.plan['scenes'][0]['pulses'][0].update(patch)
                with self.assertRaises(ValueError):validate_plan(self.plan,self.meta)
        self.plan=copy.deepcopy(original);self.plan['scenes'][0]['animations'][0]['signal']='pulse'
        self.plan['scenes'][0]['pulses'][0].update(frame=20,endFrame=25);self.meta['timeEvents'][-1]['targetTime']=20/30
        with self.assertRaisesRegex(ValueError,'compete'):validate_plan(self.plan,self.meta)

    def test_malformed_or_duplicate_saved_cues_fail_as_operator_errors(self):
        for event in [None,{'name':'bad','targetTime':float('nan')},{'name':'bad','targetTime':True},self.meta['timeEvents'][0]]:
            with self.subTest(event=event):
                meta=copy.deepcopy(self.meta);meta['timeEvents'].append(event)
                with self.assertRaises(ValueError):effective_plan(self.plan,meta)


if __name__=='__main__':unittest.main()
