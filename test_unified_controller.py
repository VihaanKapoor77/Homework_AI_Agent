import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from unified_controller import Plan, Check, geometry_valid, feedback_status, UnifiedController
from math_keyboard import enter_keyboard

class UnitTests(unittest.TestCase):
    def test_vertical_is_not_linear_pair(self):
        p=Plan(action='answer',summary='test',geometry_relation='linear_pair',vertex='G',target_rays=['C','B'],answer_rays=['D','A'],opposite_rays=[['C','D'],['A','B']])
        self.assertFalse(geometry_valid(p))
        p.answer_rays=['D','B'];self.assertTrue(geometry_valid(p))
    def test_feedback_does_not_confuse_explanation_with_success(self):
        self.assertEqual(feedback_status(['Correct!']),'accepted')
        self.assertEqual(feedback_status(['Incorrect. The correct answer is 5.']),'incorrect')
        self.assertEqual(feedback_status(['Your answer is 6','Yes']),'unknown')
        self.assertEqual(feedback_status(['The correct answer is 5']),'unknown')

class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_uncleared_field_does_not_type_111(self):
        field=AsyncMock();field.evaluate.return_value='1'
        with self.assertRaises(ValueError):await enter_keyboard(field,'1',5000)
        field.press_sequentially.assert_not_awaited()
    async def test_missing_mathquill_interface_does_not_call_object(self):
        from deltamath_tools import READ_FIELD,WRITE_MATH
        self.assertIn("typeof MQ === 'function'",READ_FIELD)
        self.assertIn('written:false',WRITE_MATH)

    async def run_case(self,check,outcome='accepted',prior=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        page=Mock();page.evaluate=AsyncMock(return_value=[]);page.url='https://www.deltamath.com/question'
        browser=Mock();browser.lock=asyncio.Lock();browser.page=AsyncMock(return_value=page)
        ctrl=UnifiedController(browser,Mock(),Mock(),AsyncMock(),AsyncMock(),Mock(), 'test',lambda x:None,Path(tmp.name)/'attempts.db')
        ctrl.notes.search.return_value=[]
        snap={'signature':'q','snapshot_token':'t','question_text':'Solve x=2','fields':[{'id':'f','kind':'text'}],'buttons':[]}
        ctrl.observe=AsyncMock(return_value=({'text':'Solve x=2','controls':[]},snap,b'png'))
        ctrl.ask=AsyncMock(side_effect=[Plan(action='answer',summary='answer',answers=['2'],submit=True),check,Plan(action='report',summary='One problem finished')])
        ctrl.enter=AsyncMock();ctrl.submit=AsyncMock(return_value=outcome)
        ctrl.delta.inspect=AsyncMock(return_value=snap)
        if prior:ctrl.journal.set('q',prior)
        result=await ctrl.run('Complete one practice question')
        return ctrl,result
    async def test_verification_failure_never_submits(self):
        ctrl,result=await self.run_case(Check(entry_matches=False,math_correct=True,all_solutions_present=True,reason='111 instead of 1'))
        ctrl.enter.assert_awaited_once();ctrl.submit.assert_not_awaited()
        self.assertIn('Not submitted',result)
    async def test_geometry_check_failure_never_submits(self):
        ctrl,result=await self.run_case(Check(entry_matches=True,math_correct=False,all_solutions_present=True,reason='vertical, not linear pair'))
        ctrl.submit.assert_not_awaited()
    async def test_unknown_feedback_never_advances(self):
        ctrl,result=await self.run_case(Check(entry_matches=True,math_correct=True,all_solutions_present=True,reason='ok'),outcome='unknown')
        self.assertIn('unknown',result)
        self.assertEqual(ctrl.ask.await_count,2)
    async def test_prior_attempt_is_not_retyped(self):
        ctrl,result=await self.run_case(Check(entry_matches=True,math_correct=True,all_solutions_present=True,reason='ok'),prior='submission_pending')
        ctrl.enter.assert_not_awaited();ctrl.submit.assert_not_awaited()
    async def test_acceptance_required_for_count(self):
        ctrl,result=await self.run_case(Check(entry_matches=True,math_correct=True,all_solutions_present=True,reason='ok'))
        self.assertIn('observed: 1',result)
    async def test_roots_come_from_worker(self):
        with tempfile.TemporaryDirectory() as d:
            calculate=AsyncMock(return_value={'solutions':[{'latex':'-2','verified':True},{'latex':'2','verified':True}],'complete':True})
            ctrl=UnifiedController(None,None,None,calculate,None,None,'test',print,Path(d)/'j.db')
            roots=await ctrl.answers_for(Plan(action='answer',summary='roots',equation='x^2=4',answers=['2']))
            self.assertEqual(roots,['-2','2'])
    async def test_chat_uses_unified_controller_not_legacy_graph(self):
        import agent
        with patch('unified_controller.UnifiedController.run',AsyncMock(return_value='Unified result')) as run,patch.object(agent,'build_graph',side_effect=AssertionError('Legacy graph must not run')),patch.object(agent,'rate_limit_retry_after',AsyncMock(return_value=0)):
            outputs=[update async for update in agent.chat('Solve the visible question',[],None)]
        run.assert_awaited_once()
        self.assertIn('Unified result',outputs[-1][-1]['content'])
    async def test_mathquill_object_interface_runtime(self):
        import shutil,subprocess,json
        from deltamath_tools import READ_FIELD,WRITE_MATH
        if not shutil.which('node'):self.skipTest('Node unavailable for JS regression fixture')
        script='global.window={MathQuill:{getInterface:()=>({})}};const el={classList:{contains:()=>true},innerText:"3"};'
        script+='console.log(JSON.stringify([('+READ_FIELD+')(el),('+WRITE_MATH+')(el,"3")]));'
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,check=True)
        read,write=json.loads(result.stdout)
        self.assertIsNone(read['latex']);self.assertFalse(write['written'])
