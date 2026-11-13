import unittest
from unittest.mock import AsyncMock
from pydantic import ValidationError
from subject_solver import SubjectSolver,SubjectAnswer,SubjectCheck,subject_route
from subject_browser import can_act,boom_activity


def candidate(**changes):
    return dict(subject='Spanish',question='Yo ___ estudiante.',answer='soy',
        translation='I am a student.',reason='Identity uses ser; yo takes soy.',
        target_id='',value='',uncertainty='',needs_source=False,**changes)


class RoutingTests(unittest.TestCase):
    def test_acronym_tile_positions_distinguish_both_os(self):
        from spanish_rules import category_control
        def tiles(n):return [dict(id=str(i),answer_choice=True,disabled=False,rect=dict(x=i*100,y=100,height=80)) for i in reversed(range(n))]
        self.assertEqual(category_control(tiles(6),'DOCTOR','Origin'),'1')
        self.assertEqual(category_control(tiles(6),'DOCTOR','Occupation'),'4')
        self.assertEqual(category_control(tiles(5),'PLACE','Position'),'0')
        self.assertEqual(category_control(tiles(5),'PLACE','Location'),'1')
        with self.assertRaises(ValueError):category_control(tiles(6),'DOCTOR','O')

    def test_delta_url_always_uses_math(self):
        for subject in ('Auto','Spanish / Translation','English','General'):
            self.assertEqual(subject_route('https://www.deltamath.com/app/student/123',subject,True),'math')

    def test_default_math_unchanged(self):
        self.assertEqual(subject_route('Solve the visible question'),'math')
        self.assertEqual(subject_route('Solve this','Math / DeltaMath',True),'math')

    def test_subject_modes_and_link(self):
        for request in ('Translate: Estoy cansado.','Help with science','English grammar',
            'https://wow.boomlearning.com/hyperplay/test/card/'):
            self.assertEqual(subject_route(request),'subject')
        self.assertEqual(subject_route('Answer the visible card',active_subject=True),'subject')

    def test_only_actual_boom_activity_can_be_automated(self):
        self.assertTrue(boom_activity('https://wow.boomlearning.com/hyperplay/test/card/'))
        for url in ('https://wow.boomlearning.com.evil.test/hyperplay/a','https://wow.boomlearning.com/signin/student','http://wow.boomlearning.com/hyperplay/a'):
            self.assertFalse(boom_activity(url))

    def test_translation_and_no_submit_are_read_only(self):
        for request in ('Translate this card','Solve but do not submit','Explain only','Solve but don’t click'):
            self.assertFalse(can_act(request))
        self.assertTrue(can_act('Solve the visible Spanish card'))


class SolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_translation_and_independent_check(self):
        generate=AsyncMock(side_effect=[candidate(),dict(correct=True,target_matches=True,reason='Verified conjugation')])
        solver=SubjectSolver('test',generate)
        answer,check=await solver.solve('Yo ___ estudiante. soy/es/estoy')
        self.assertEqual(generate.await_count,2)
        self.assertIn('soy',solver.report(answer,check))
        self.assertIn('I am a student.',solver.report(answer,check))
        self.assertIn('Independently solve',generate.call_args_list[1].args[0])

    async def test_ambiguous_answer_is_withheld(self):
        raw=candidate();raw['uncertainty']='Both adjectives fit without context.'
        generate=AsyncMock(return_value=raw)
        solver=SubjectSolver('test',generate)
        answer,check=await solver.solve('Él ___ listo.')
        self.assertIsNone(check)
        self.assertIn('Needs review',solver.report(answer,check))
        self.assertEqual(generate.await_count,1)

    async def test_missing_source_is_withheld(self):
        raw=candidate();raw['needs_source']=True
        solver=SubjectSolver('test',AsyncMock(return_value=raw))
        answer,check=await solver.solve('What does the missing passage say?')
        self.assertIn('Needs review',solver.report(answer,check))

    async def test_disagreement_blocks_answer(self):
        solver=SubjectSolver('test',AsyncMock(side_effect=[candidate(),dict(correct=False,target_matches=True,reason='Wrong verb')]))
        answer,check=await solver.solve('test')
        self.assertIn('verification failed',solver.report(answer,check))

    def test_model_must_supply_real_boolean_checks(self):
        with self.assertRaises(ValidationError):SubjectCheck(correct='true',target_matches=True,reason='')
        with self.assertRaises(ValidationError):SubjectAnswer.model_validate({'answer':'soy'})


if __name__=='__main__':unittest.main()
