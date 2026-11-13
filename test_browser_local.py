"""Real Chromium DOM interaction, no external DeltaMath access or account required."""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch
from playwright.async_api import async_playwright
from deltamath_tools import DeltaMathTools
from delta_workflow import enter_solution_set

@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS')=='1','Set RUN_BROWSER_TESTS=1 for Chromium fixtures')
class LocalBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw=await async_playwright().start()
        path=os.getenv('TEST_CHROME_PATH')
        self.browser=await self.pw.chromium.launch(headless=True,executable_path=path or None,args=['--no-sandbox'])
        self.page=await self.browser.new_page()
        self.host_patch=patch('deltamath_tools.is_deltamath',lambda url: True)
        self.host_patch.start()
        self.delta=DeltaMathTools()
        self.delta.ready_timeout_ms=3000
    async def asyncTearDown(self):
        self.host_patch.stop()
        await self.browser.close()
        await self.pw.stop()
    async def test_plain_read_write_and_stale(self):
        await self.page.set_content('<main><h3 id="q">Solve x+1=3</h3><input aria-label="Answer"><button>Submit</button></main>')
        snap=await self.delta.inspect(self.page)
        self.assertIn('x+1=3',snap['question_text'])
        r=await self.delta.enter(self.page,snap['snapshot_token'],snap['fields'][0]['id'],'2','text')
        self.assertTrue(r['readback_matches'])
        self.assertEqual(await self.page.locator('input').input_value(),'2')
        await self.page.locator('#q').evaluate('(el) => el.textContent="Solve x+1=8"')
        with self.assertRaisesRegex(ValueError,'Question changed'):
            await self.delta.enter(self.page,snap['snapshot_token'],snap['fields'][0]['id'],'7','text')
    async def test_multiple_roots_are_both_written(self):
        await self.page.set_content('''<main><p>Solve x^2=4</p><div id="answers"><input></div>
        <button onclick="document.querySelector('#answers').insertAdjacentHTML('beforeend','<input>')">Add Solution</button>
        <button>Submit</button></main>''')
        snap=await self.delta.inspect(self.page)
        result=await enter_solution_set(self.delta,self.page,snap['snapshot_token'],['-2','2'])
        self.assertFalse(result['submitted'])
        self.assertEqual(await self.page.locator('#answers input').evaluate_all('xs=>xs.map(e=>e.value)'),['-2','2'])
    async def test_mathquill_public_interface(self):
        await self.page.set_content('<main><p>Solve x=1/2</p><span class="mq-editable-field" tabindex="0" style="display:inline-block;min-width:100px;min-height:28px"></span></main>')
        await self.page.evaluate('''() => {const el=document.querySelector('.mq-editable-field');
            const editor={value:'',focus(){el.focus()},latex(x){if(arguments.length)this.value=x;return this.value},write(x){this.value=x;el.textContent=x}};
            window.MathQuill={getInterface:()=>node=>node===el?editor:null};}''')
        snap=await self.delta.inspect(self.page)
        r=await self.delta.enter(self.page,snap['snapshot_token'],snap['fields'][0]['id'],r'\frac{1}{2}','latex')
        self.assertTrue(r['readback_matches'])
        self.assertFalse(r['used_keyboard'])
    async def test_dropdown_selection_by_label(self):
        await self.page.set_content('<main><p>Select quadrant</p><select aria-label="Quadrant"><option>Select</option><option value="2">II</option></select></main>')
        snap=await self.delta.inspect(self.page)
        self.assertEqual(snap['fields'][0]['kind'],'select')
        out=await self.delta.enter(self.page,snap['snapshot_token'],snap['fields'][0]['id'],'II','text')
        self.assertTrue(out['readback_matches'])
        self.assertEqual(await self.page.locator('select').input_value(),'2')

    async def test_delayed_question_render(self):
        await self.page.set_content('<main></main>')
        await self.page.evaluate('''() => setTimeout(()=>{
           document.querySelector('main').innerHTML='<p>Solve x=4</p><input>'},120)''')
        snap=await self.delta.inspect(self.page)
        self.assertIn('x=4',snap['question_text'])
        self.assertEqual(len(snap['fields']),1)
    async def test_feedback_is_not_claimed_before_submission(self):
        await self.page.set_content('<main><p>Solve x=3</p><input><button>Submit</button><div role="status"></div></main>')
        snap=await self.delta.inspect(self.page)
        self.assertEqual((await self.delta.feedback(self.page))['feedback'],[])
        await self.page.locator('[role=status]').evaluate('(el) => el.textContent="Correct!"')
        self.assertIn('Correct!',(await self.delta.feedback(self.page))['feedback'])

if __name__=='__main__': unittest.main()
