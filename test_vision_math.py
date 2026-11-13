import json
import unittest
from unittest.mock import AsyncMock
from vision_math import VisionMath, VisualResult, VisualCalculation

class Locator:
    def __init__(self, count=1): self.n=count
    async def count(self): return self.n
    async def bounding_box(self,**kw): return {'x':0,'y':0,'width':800,'height':600}
    async def screenshot(self,**kw): return b'question pixels'

class Page:
    url='https://www.deltamath.com/test'
    def locator(self, selector): return Locator(2 if selector=='ambiguous' else 1)
    async def screenshot(self,**kw): return b'viewport pixels'

class VisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.solver=VisionMath('test')
        self.page=Page()
        self.answer=VisualResult(status='candidate',question='Which angle forms a linear pair?',diagram_observations=['Shared ray GB; GC and GH are opposite'],method='Adjacent angles on a straight line',answer='2')
        self.solver.ask=AsyncMock(return_value=self.answer)
    async def test_visual_geometry_needs_no_numeric_solver(self):
        calc=AsyncMock()
        r=await self.solver.solve(self.page,calculate=calc)
        self.assertEqual(r['answer'],'2')
        self.assertEqual(r['capture']['scope'],'main')
        self.assertFalse(r['website_accepted'])
        calc.assert_not_awaited()
    async def test_identical_pixels_cached(self):
        await self.solver.solve(self.page)
        self.assertTrue((await self.solver.solve(self.page))['cache_hit'])
        self.assertEqual(self.solver.ask.await_count,1)
    async def test_verify_uses_separate_cache_and_rejects_denominator_x(self):
        await self.solver.solve(self.page)
        self.solver.ask.return_value=VisualResult(status='candidate',question='Check field',method='x is under fraction bar',observed_entry='1/(2*x)+6=y',entry_comparison='mismatch')
        r=await self.solver.solve(self.page,mode='verify_entry',expected_latex=r'\frac{1}{2}x+6=y')
        self.assertEqual(r['status'],'needs_review')
        self.assertEqual(self.solver.ask.await_count,2)
    async def test_low_readability_blocks(self):
        self.solver.ask.return_value=self.answer.model_copy(update={'uncertainty':'Point C is unreadable'})
        self.assertEqual((await self.solver.solve(self.page))['status'],'needs_review')
    async def test_bad_selector(self):
        with self.assertRaises(ValueError): await self.solver.solve(self.page,selector='ambiguous')
    async def test_missing_expected_answer(self):
        with self.assertRaises(ValueError): await self.solver.solve(self.page,mode='verify_entry')
    async def test_worker_failure_blocks(self):
        self.solver.ask.return_value=self.answer.model_copy(update={'calculations':[VisualCalculation(operation='solve',expression='x_mid=3')]})
        calc=AsyncMock(return_value=json.dumps({'error':'unsupported variable'}))
        self.assertEqual((await self.solver.solve(self.page,calculate=calc))['status'],'needs_review')
    async def test_navigation_during_model(self):
        async def ask(*args): self.page.url='https://www.deltamath.com/next';return self.answer
        self.solver.ask=ask
        with self.assertRaisesRegex(ValueError,'navigated'): await self.solver.solve(self.page)
    async def test_model_timeout(self):
        self.solver.ask=AsyncMock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError): await self.solver.solve(self.page)
    async def test_prompt_and_image_sent(self):
        await self.solver.solve(self.page,request='Solve this diagram')
        pixels,prompt=self.solver.ask.call_args.args
        self.assertEqual(pixels,b'question pixels')
        self.assertEqual(json.loads(prompt)['request'],'Solve this diagram')

class WiringTests(unittest.TestCase):
    def test_both_registries(self):
        import agent
        self.assertIn('solve_math_from_screenshot',[t.name for t in agent.TOOLS])
        model=agent.browser_tools.registry.create_action_model()
        value=model.model_validate({'browser_solve_math_from_screenshot':{'mode':'verify_entry','expected_latex':'x/2+6=y'}})
        self.assertIn('browser_solve_math_from_screenshot',value.model_dump(exclude_none=True))
    def test_launchers_share_main(self):
        import agent,app,agent_rate_limited
        self.assertIs(app.main,agent.main)
        self.assertIs(agent_rate_limited.main,agent.main)

if __name__=='__main__': unittest.main()
