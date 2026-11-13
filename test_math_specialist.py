import json
import unittest
from math_solver import calculate
from math_specialist import MathPlan, Calculation, consult
from math_keyboard import keyboard_plan

class SpecialistTests(unittest.IsolatedAsyncioTestCase):
    async def test_logged_segment(self):
        async def ask(*args):
            return MathPlan(status='calculate',interpretation='AP:PB=3:1',method='Internal section formula',calculations=[Calculation(operation='directed_segment',expression='-5,4,1,8,3,1')])
        async def calc(op,exp,var): return json.dumps(calculate(op,exp,var))
        result=await consult('Endpoints (-5,4), (1,8), AP:PB=3:1','',ask,calc)
        self.assertEqual(result['answer'],'(-1/2, 7)')
    async def test_missing_endpoints(self):
        async def ask(*args): return MathPlan(status='need_information',interpretation='Endpoints missing',method='',missing_information='Read both endpoints from the diagram.')
        async def calc(*args): self.fail('Must not calculate missing endpoints')
        self.assertEqual((await consult('from to ratio 1:5','',ask,calc))['status'],'needs_information')
    async def test_bounded_research(self):
        calls=[]
        async def ask(*args):
            calls.append('model')
            return MathPlan(status='research',interpretation='',method='',research_query='section formula')
        async def research(q): calls.append('search');return 'not found'
        async def calc(*args): self.fail('No calculation expected')
        result=await consult('question','',ask,calc,research)
        self.assertEqual(calls,['model','search','model'])
        self.assertEqual(result['status'],'needs_information')
    async def test_solver_failure(self):
        async def ask(*args): return MathPlan(status='calculate',interpretation='',method='test',calculations=[Calculation(operation='solve',expression='x_mid=2')])
        async def calc(*args): return {'error':'unknown variable'}
        self.assertEqual((await consult('question','',ask,calc))['status'],'calculation_failed')

class KeyboardTests(unittest.TestCase):
    def test_fraction_exit_before_x(self):
        plan=keyboard_plan(r'\frac{1}{2}x+6=y')
        i=plan.index(('text','x'))
        self.assertEqual(plan[i-1],('key','ArrowRight'))
    def test_tuple_and_power(self):
        self.assertIn(('key','ArrowRight'),keyboard_plan(r'(-\frac{1}{2},7)'))
        self.assertEqual(keyboard_plan('x^{2}y')[-2:], [('key','ArrowRight'),('text','y')])
    def test_unsupported_fails(self):
        for value in [r'\sqrt',r'\frac{1}',r'\foo{x}', 'x/2']:
            with self.subTest(value=value),self.assertRaises(ValueError): keyboard_plan(value)
    def test_ratio_order(self):
        r=calculate('directed_segment','0,0,6,12,1,5')
        self.assertEqual(r['point'],'(1, 2)')
        with self.assertRaises(ValueError): calculate('directed_segment','0,0,6,12,0,5')


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_consultation(self):
        from unittest.mock import AsyncMock,patch
        import agent
        token=agent.MATH_CONSULTATIONS.set({})
        try:
            with patch('math_specialist.second_opinion',new_callable=AsyncMock) as mock:
                mock.return_value={'status':'ready_for_review','answer':'3'}
                first=await agent.second_math_impl('Solve x=3','first attempt')
                second=await agent.second_math_impl('Solve x=3','another attempt')
                self.assertEqual(first,second)
                self.assertEqual(mock.await_count,1)
        finally: agent.MATH_CONSULTATIONS.reset(token)
    async def test_schema(self):
        import agent
        model=agent.browser_tools.registry.create_action_model()
        obj=model.model_validate({'browser_second_math_opinion':{'problem':'Solve x=3','failed_attempt':''}})
        self.assertIn('browser_second_math_opinion',obj.model_dump(exclude_none=True))

if __name__=='__main__': unittest.main()
