"""Run: python -m unittest -v test_regressions (no model key needed)."""
import asyncio
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import sympy as sp
from math_solver import calculate, parse_expression
from settings import milliseconds, MAX_TIMER_MS
from deltamath_tools import DeltaMathTools, normalize_latex

class MathTests(unittest.TestCase):
    def test_logged_problem(self):
        result = calculate('perpendicular_bisector', '-8,6,-4,2')
        self.assertEqual(result['rhs'], 'x + 10')
        self.assertEqual(result['midpoint'], ['-6', '4'])
    def test_vertical_horizontal(self):
        self.assertEqual(calculate('perpendicular_bisector','0,0,4,0')['lhs'], 'x')
        self.assertEqual(calculate('perpendicular_bisector','0,0,0,4')['rhs'], '2')
        with self.assertRaises(ValueError): calculate('perpendicular_bisector','1,1,1,1')
    def test_logs_latex_exact(self):
        self.assertEqual(calculate('evaluate','log10(1000)')['exact'],'3')
        self.assertEqual(calculate('evaluate','ln(E)')['exact'],'1')
        self.assertEqual(calculate('evaluate','1/3')['latex'],r'\frac{1}{3}')
        self.assertEqual(calculate('evaluate','0.1+0.2')['exact'],'3/10')
    def test_roots_and_domains(self):
        self.assertEqual(calculate('solve','(x^2-1)/(x-1)=0')['result'],'{-1}')
        self.assertEqual(calculate('solve','x^2+1=0')['result'],'EmptySet')
        self.assertEqual(calculate('solve','sqrt(x)=-1')['result'],'EmptySet')
        self.assertTrue(all(r['verified'] for r in calculate('solve','x^2=9')['solutions']))
    def test_ast_security_and_errors(self):
        for text in ["__import__('os')",'x.__class__','[x for x in y]','y_mid','2**1001','1/0']:
            with self.subTest(text=text), self.assertRaises((ValueError,SyntaxError)): parse_expression(text)
    def test_worker_protocol(self):
        out = subprocess.run([sys.executable,str(Path(__file__).with_name('math_solver.py'))],input=json.dumps({'operation':'evaluate','expression':'2+3'}),capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(out.stdout)['exact'],'5')
    def test_overflow(self):
        with patch.dict(os.environ,{'TEST_WAIT':'5000000000'}):
            with self.assertWarns(UserWarning): self.assertEqual(milliseconds('TEST_WAIT',1),MAX_TIMER_MS)
        with patch.dict(os.environ,{'TEST_WAIT':'nan'}):
            with self.assertRaises(ValueError): milliseconds('TEST_WAIT',1)

class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_poll_delayed_content(self):
        class Page:
            url='https://www.deltamath.com/test'
            calls=0
            async def evaluate(self, script, args):
                self.calls+=1
                text='' if self.calls==1 else 'Solve x=3'
                return dict(url=self.url,question_text=text,math=[],images=[],fields=[],buttons=[],feedback=[],visible_text=text)
        page=Page(); delta=DeltaMathTools(); delta.ready_timeout_ms=2000
        result=await delta.inspect(page)
        self.assertEqual(result['question_text'],'Solve x=3')
        self.assertGreaterEqual(page.calls,4)
        self.assertIn('snapshot_token',result)
    async def test_empty_content_deadline(self):
        class Page:
            url='https://www.deltamath.com/test'
            async def evaluate(self, script, args):
                return dict(url=self.url,question_text='',math=[],images=[],fields=[],buttons=[],feedback=[],visible_text='')
        delta=DeltaMathTools(); delta.ready_timeout_ms=20
        with self.assertRaisesRegex(TimeoutError,'readiness deadline'):
            await delta.inspect(Page())
    async def test_readback_does_not_reassign_snapshot(self):
        class Page:
            url='https://www.deltamath.com/test'
            async def evaluate(self, script, args):
                return dict(url=self.url,question_text='Solve x=3',math=[],images=[],fields=[],buttons=[],feedback=[],visible_text='Solve x=3')
        page=Page(); delta=DeltaMathTools()
        first=await delta.inspect(page)
        second=await delta.inspect(page,assign=False)
        self.assertEqual(delta.latest['token'],first['snapshot_token'])
        self.assertEqual(first['signature'],second['signature'])

class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import agent
        cls.agent = agent
        cls.model = agent.browser_tools.registry.create_action_model()
    def test_logged_placeholder(self):
        for name in ('browser_delta_read', 'browser_delta_feedback'):
            for payload in ({'_placeholder':''}, {'_placeholder':'read'}, {}, {'request':'read'}):
                with self.subTest(name=name,payload=payload):
                    result=self.model.model_validate({name:payload})
                    self.assertEqual(result.model_dump(exclude_none=True)[name]['request'], 'read')
    def test_unknown_argument_rejected(self):
        with self.assertRaises(ValueError):
            self.model.model_validate({'browser_delta_read':{'unexpected':'x'}})
    def test_nonempty_schema(self):
        schema=self.agent.DeltaReadParams.model_json_schema()
        self.assertIn('request',schema['properties'])
    def test_browser_math_error_result(self):
        action=self.agent.browser_tools.registry.registry.actions['browser_math']
        params=action.param_model(operation='solve',expression='y-y_mid=m_perp*(x-x_mid)',variable='y')
        result=asyncio.run(action.function(params=params))
        self.assertIn('Unsupported syntax', result.error)

@unittest.skipUnless(os.getenv("RUN_LEGACY_BROWSER_TESTS") == "1", "Legacy HTTPS route fixtures require an unrestricted test network; use test_browser_local.py instead")
class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.pw=await async_playwright().start()
        kwargs={'headless':True}
        if os.getenv('TEST_CHROME_PATH'): kwargs['executable_path']=os.environ['TEST_CHROME_PATH']
        self.browser=await self.pw.chromium.launch(**kwargs)
        self.page=await self.browser.new_page()
        await self.page.route('https://www.deltamath.com/**',lambda route: route.fulfill(body='<main><p id="question">Solve x + 1 = 3</p><input aria-label="Answer"><button>Submit</button><div role="status"></div></main>',content_type='text/html'))
        await self.page.goto('https://www.deltamath.com/test')
        self.delta=DeltaMathTools()
        self.delta.ready_timeout_ms=2000
    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()
    async def test_plain_entry_and_stale_snapshot(self):
        data=await self.delta.inspect(self.page)
        result=await self.delta.enter(self.page,data['snapshot_token'],data['fields'][0]['id'],'2','text')
        self.assertTrue(result['readback_matches'])
        self.assertFalse(result['submitted'])
        self.assertEqual(await self.page.locator(data['buttons'][0]['selector']).count(),1)
        await self.page.locator('#question').evaluate('(el)=>el.textContent="Solve x + 4 = 9"')
        with self.assertRaisesRegex(ValueError,'Question changed'):
            await self.delta.enter(self.page,data['snapshot_token'],data['fields'][0]['id'],'2','text')
    async def test_delayed_render(self):
        await self.page.evaluate('''() => { document.querySelector('main').innerHTML=''; setTimeout(()=>{document.querySelector('main').innerHTML='<p>Solve x=4</p><input>'}, 150); }''')
        data=await self.delta.inspect(self.page)
        self.assertIn('x=4',data['question_text'])
        self.assertEqual(len(data['fields']),1)
    async def test_mathquill_public_api(self):
        # A test double for the public MathQuill API, not a claim about the live site.
        await self.page.evaluate('''() => {
            document.querySelector('input').outerHTML='<span class="mq-editable-field"><textarea></textarea></span>';
            const el=document.querySelector('.mq-editable-field');
            const api={value:'',focus(){},select(){this.value=''},write(s){this.value=s;el.dataset.value=s},latex(){return this.value}};
            window.MathQuill={getInterface:()=>node=>node===el?api:null};
        }''')
        data=await self.delta.inspect(self.page)
        self.assertEqual(len(data['fields']),1)
        result=await self.delta.enter(self.page,data['snapshot_token'],data['fields'][0]['id'],r'\frac{1}{2}','latex')
        self.assertTrue(result['readback_matches'])
        await self.page.locator('[role=status]').evaluate('(el)=>el.textContent="Correct!"')
        self.assertIn('Correct!',(await self.delta.feedback(self.page))['feedback'])
    async def test_missing_mathquill_api(self):
        await self.page.evaluate('''() => { document.querySelector('input').outerHTML='<span class="mq-editable-field">answer</span>'; }''')
        data=await self.delta.inspect(self.page)
        result=await self.delta.enter(self.page,data['snapshot_token'],data['fields'][0]['id'],'2','latex')
        self.assertTrue(result['requires_visual_verification'])
        self.assertTrue(result['used_keyboard'])
        self.assertFalse(result['readback_matches'])

if __name__=='__main__': unittest.main()
