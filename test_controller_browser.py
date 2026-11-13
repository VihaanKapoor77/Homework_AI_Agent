"""End-to-end offline: Chrome DOM -> SymPy -> verified input -> explicit feedback."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from playwright.async_api import async_playwright
from deltamath_tools import DeltaMathTools
from unified_controller import Check, Plan, UnifiedController
from math_solver import calculate

@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS')=='1','Set RUN_BROWSER_TESTS=1 for local Chromium tests')
class OfflineControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(headless=True,executable_path=os.getenv('TEST_CHROME_PATH') or None,args=['--no-sandbox'])
        self.page=await self.browser.new_page()
        self.hostpatch=patch('deltamath_tools.is_deltamath',lambda _:True)
        self.ctrlpatch=patch('unified_controller.is_deltamath',lambda _:True)
        self.hostpatch.start();self.ctrlpatch.start()
        self.tmp=tempfile.TemporaryDirectory()
        class Wrapper:
            lock=asyncio.Lock()
            def __init__(self,page):self.p=page
            async def page(self):return self.p
        async def solver(operation,expression,variable='x'):
            return calculate(operation,expression,variable)
        self.ctrl=UnifiedController(Wrapper(self.page),DeltaMathTools(),None,solver,None,None,'unused',lambda _:None,Path(self.tmp.name)/'journal.db',fast_mode=True)
    async def asyncTearDown(self):
        self.hostpatch.stop();self.ctrlpatch.stop();self.tmp.cleanup()
        await self.browser.close();await self.pw.stop()
    async def test_single_equation_end_to_end_and_replay_blocked(self):
        await self.page.set_content('''<main><p>Solve x+1=3</p><input id="answer"><button onclick="document.querySelector('[role=status]').textContent=(document.querySelector('#answer').value==='2'?'Correct!':'Incorrect')">Submit</button><div role="status"></div></main>''')
        output=await self.ctrl.run('Solve this problem')
        self.assertIn('observed: 1',output)
        self.assertEqual(await self.page.locator('#answer').input_value(),'2')
        self.assertIn('Previous attempt',await self.ctrl.run('Do that question again'))
    async def test_two_roots_added_and_accepted(self):
        await self.page.set_content('''<main><p>Solve x^2=4</p><div id="answers"><input></div><button onclick="document.querySelector('#answers').insertAdjacentHTML('beforeend','<input>')">Add Solution</button>
        <button onclick="document.querySelector('[role=status]').textContent=(Array.from(document.querySelectorAll('#answers input')).map(x=>x.value).join(',')==='-2,2'?'Correct!':'Incorrect')">Submit</button><div role="status"></div></main>''')
        output=await self.ctrl.run('Solve all roots')
        self.assertIn('observed: 1',output)
        self.assertEqual(await self.page.locator('#answers input').evaluate_all('xs=>xs.map(x=>x.value)'),['-2','2'])
    async def test_fraction_is_written_as_plain_text_not_latex(self):
        await self.page.set_content('''<main><p>Solve 2*x=1</p><input id="answer"><button onclick="document.querySelector('[role=status]').textContent=(document.querySelector('#answer').value==='1/2'?'Correct!':'Incorrect')">Submit</button><div role="status"></div></main>''')
        output=await self.ctrl.run('Solve question')
        self.assertIn('observed: 1',output)
        self.assertEqual(await self.page.locator('#answer').input_value(),'1/2')

    async def test_multiple_choice_radio_selected_by_exact_visible_label(self):
        await self.page.set_content('''<main><p>Which transformation maps the figures?</p>
        <label><input type="radio" name="answer" value="x">A reflection over the x-axis</label>
        <label><input type="radio" name="answer" value="translation">A translation 3 units left and 4 units down</label>
        <button>Submit Answer</button></main>''')
        snapshot=await self.ctrl.delta.inspect(self.page)

        result=await self.ctrl.enter(self.page,snapshot,['A translation 3 units left and 4 units down'])

        self.assertTrue(result['entries'][0]['readback_matches'])
        self.assertTrue(await self.page.locator('input[value="translation"]').is_checked())
        self.assertFalse(await self.page.locator('input[value="x"]').is_checked())

    async def test_radio_matching_uses_visible_label_not_math_markup(self):
        await self.page.set_content(r'''<main><p>Which transformation does not map the shape onto itself?</p>
        <label><input id="reflection" type="radio" name="answer" aria-label="\text{a reflection over the x-axis}">
        <span>a reflection over the x-axis</span>
        <span style="display:block">a&nbsp;reflection&nbsp;over&nbsp;the&nbsp;x-axis</span></label>
        <button onclick="document.querySelector('[role=status]').textContent=document.querySelector('#reflection').checked?'Correct!':'Incorrect'">Submit Answer</button>
        <div role="status"></div></main>''')
        self.ctrl.fast_mode=False
        self.ctrl.ask=AsyncMock(side_effect=[
            Plan(action='answer',answers=['A reflection over the x-axis'],submit=True),
            Check(entry_matches=True,math_correct=True,all_solutions_present=True),
        ])

        result=await self.ctrl.run('Finish the whole assignment')

        self.assertIn('observed: 1',result)
        self.assertTrue(await self.page.locator('#reflection').is_checked())
        self.assertEqual(await self.page.get_by_role('status').inner_text(),'Correct!')

    async def test_coordinate_translation_is_verified_without_vision_model(self):
        alt='''A polygon labeled Figure NOP and a polygon labeled Figure QRS on a coordinate plane.
        The coordinates of Figure NOP are left parenthesis, 2, comma, 0, right parenthesis
        left parenthesis, 2, comma, 3, right parenthesis and left parenthesis, 0, comma, 5, right parenthesis.
        The coordinates of Figure QRS are left parenthesis, minus, 1, comma, minus, 4, right parenthesis
        left parenthesis, minus, 1, comma, minus, 1, right parenthesis and left parenthesis, minus, 3, comma, 1, right parenthesis.'''
        await self.page.set_content(f'''<main><p>Which transformation would accomplish this?</p>
        <img alt="{alt}" width="600" height="300">
        <label><input type="radio" name="answer" value="reflection">A reflection over the y-axis</label>
        <label><input id="translation" type="radio" name="answer" value="translation">A translation 3 units left and 4 units down</label>
        <button onclick="document.querySelector('[role=status]').textContent=document.querySelector('#translation').checked?'Correct!':'Incorrect'">Submit Answer</button>
        <div role="status"></div></main>''')

        with patch('unified_controller.generate_json',side_effect=AssertionError('vision model should not be needed')):
            result=await self.ctrl.run('Finish the whole DeltaMath assignment')

        self.assertIn('observed: 1',result)
        self.assertTrue(await self.page.locator('#translation').is_checked())
        self.assertEqual(await self.page.get_by_role('status').inner_text(),'Correct!')

    async def test_coordinate_rotation_is_verified_without_vision_model(self):
        alt='''A polygon labeled Figure FGH and a polygon labeled Figure IJK on a coordinate plane.
        The coordinates of Figure FGH are left parenthesis, 4, comma, minus, 5, right parenthesis
        left parenthesis, 3, comma, minus, 2, right parenthesis and left parenthesis, 1, comma, minus, 2, right parenthesis.
        The coordinates of Figure IJK are left parenthesis, 5, comma, 4, right parenthesis
        left parenthesis, 2, comma, 3, right parenthesis and left parenthesis, 2, comma, 1, right parenthesis.'''
        await self.page.set_content(f'''<main><p>Which transformation would accomplish this?</p>
        <img alt="{alt}" width="600" height="300">
        <label><input id="rotation" type="radio" name="answer" value="rotation">A rotation 90° counterclockwise about the origin</label>
        <label><input type="radio" name="answer" value="reflection">A reflection over the y-axis</label>
        <button onclick="document.querySelector('[role=status]').textContent=document.querySelector('#rotation').checked?'Correct!':'Incorrect'">Submit Answer</button>
        <div role="status"></div></main>''')

        with patch('unified_controller.generate_json',side_effect=AssertionError('vision model should not be needed')):
            result=await self.ctrl.run('Finish the whole DeltaMath assignment')

        self.assertIn('observed: 1',result)
        self.assertTrue(await self.page.locator('#rotation').is_checked())
        self.assertEqual(await self.page.get_by_role('status').inner_text(),'Correct!')

    async def test_quadrilateral_symmetry_selects_the_unique_nonpreserving_transform(self):
        alt='''A coordinate plane with a blue rectangle drawn on it. One vertex is at left parenthesis, 4, comma, 6, right parenthesis.
        The next vertex is at left parenthesis, minus, 6, comma, minus, 4, right parenthesis.
        The next vertex is at left parenthesis, minus, 4, comma, minus, 6, right parenthesis.
        The last vertex is at left parenthesis, 6, comma, 4, right parenthesis.'''
        await self.page.set_content(f'''<main><p>Which transformation will not carry the rectangle below onto itself?</p>
        <img alt="{alt}" width="600" height="300">
        <label><input type="radio" name="answer" value="y-neg-x">
        <span>a reflection over the line , y, equals, minus, x</span>
        <span style="display:block">a&nbsp;reflection&nbsp;over&nbsp;the&nbsp;line&nbsp;y=−x</span></label>
        <label><input type="radio" name="answer" value="y-x">
        <span>a reflection over the line , y, equals, x</span>
        <span style="display:block">a&nbsp;reflection&nbsp;over&nbsp;the&nbsp;line&nbsp;y=x</span></label>
        <label><input id="x-axis" type="radio" name="answer" value="x">
        <span>a reflection over the x-axis</span>
        <span style="display:block">a&nbsp;reflection&nbsp;over&nbsp;the&nbsp;x-axis</span></label>
        <label><input type="radio" name="answer" value="rotation">
        <span>a rotation of 180, degrees, counterclockwise about the origin</span>
        <span style="display:block">a&nbsp;rotation&nbsp;of&nbsp;180<br>∘<br>counterclockwise&nbsp;about&nbsp;the&nbsp;origin</span></label>
        <button onclick="document.querySelector('[role=status]').textContent=document.querySelector('#x-axis').checked?'Correct!':'Incorrect'">Submit Answer</button>
        <div role="status"></div></main>''')

        with patch('unified_controller.generate_json',side_effect=AssertionError('vision model should not be needed')):
            result=await self.ctrl.run('Finish the whole DeltaMath assignment')

        self.assertIn('observed: 1',result)
        self.assertTrue(await self.page.locator('#x-axis').is_checked())
        self.assertEqual(await self.page.get_by_role('status').inner_text(),'Correct!')

    async def test_coordinate_reflection_matches_axis_with_spaced_hyphen(self):
        alt='''A polygon labeled Figure K and a polygon labeled Figure L on a coordinate plane.
        The coordinates of Figure K are left parenthesis, 4, comma, 0, right parenthesis
        left parenthesis, 3, comma, 4, right parenthesis and left parenthesis, 1, comma, 4, right parenthesis.
        The coordinates of Figure L are left parenthesis, 4, comma, 0, right parenthesis
        left parenthesis, 3, comma, minus, 4, right parenthesis and left parenthesis, 1, comma, minus, 4, right parenthesis.'''
        await self.page.set_content(f'''<main><p>Which transformation would accomplish this?</p>
        <img alt="{alt}" width="600" height="300">
        <label><input id="x-axis" type="radio" name="answer" value="x"><span>A reflection over the </span><i>x</i> -axis</label>
        <label><input id="y-axis" type="radio" name="answer" value="y"><span>A reflection over the </span><i>y</i> -axis</label>
        <button onclick="document.querySelector('[role=status]').textContent=document.querySelector('#x-axis').checked?'Correct!':'Incorrect'">Submit Answer</button>
        <div role="status"></div></main>''')

        with patch('unified_controller.generate_json',side_effect=AssertionError('vision model should not be needed')):
            result=await self.ctrl.run('Finish the whole DeltaMath assignment')

        self.assertIn('observed: 1',result)
        self.assertTrue(await self.page.locator('#x-axis').is_checked())
        self.assertFalse(await self.page.locator('#y-axis').is_checked())
        self.assertEqual(await self.page.get_by_role('status').inner_text(),'Correct!')

    async def test_explicit_finish_overrides_model_submit_false(self):
        await self.page.set_content('''<main><p>Solve x+1=3</p><input id="answer">
        <button onclick="document.querySelector('[role=status]').textContent=document.querySelector('#answer').value==='2'?'Correct!':'Incorrect'">Submit Answer</button>
        <div role="status"></div></main>''')
        self.ctrl.fast_mode=False
        self.ctrl.ask=AsyncMock(side_effect=[
            Plan(action='answer',answers=['2'],submit=False),
            Check(entry_matches=True,math_correct=True,all_solutions_present=True),
        ])

        result=await self.ctrl.run('Finish the whole assignment')

        self.assertIn('observed: 1',result)
        self.assertEqual(await self.page.get_by_role('status').inner_text(),'Correct!')

    async def test_coordinate_reflection_matches_exact_visible_option(self):
        alt='''The coordinates of Figure ABC are left parenthesis, 4, comma, minus, 5, right parenthesis
        left parenthesis, 3, comma, minus, 2, right parenthesis and left parenthesis, 1, comma, minus, 2, right parenthesis.
        The coordinates of Figure DEF are left parenthesis, minus, 4, comma, minus, 5, right parenthesis
        left parenthesis, minus, 3, comma, minus, 2, right parenthesis and left parenthesis, minus, 1, comma, minus, 2, right parenthesis.'''
        snapshot={
            'question_text':'Which transformation would accomplish this?',
            'images':[{'alt':alt}],
            'fields':[
                {'kind':'radio_option','label':'A reflection over the x-axis'},
                {'kind':'radio_option','label':'A reflection over the y-axis'},
            ],
        }

        plan=self.ctrl.coordinate_transformation_plan(snapshot,'Finish the assignment')

        self.assertEqual(plan.action,'answer')
        self.assertEqual(plan.answers,['A reflection over the y-axis'])

    async def test_advances_to_next_incomplete_skill_after_completion(self):
        body='''<aside>
        <a href="/app/student/1/2/current">Skill is complete. Current skill</a>
        <a href="/app/student/1/2/next">0 out of 5 complete. Next skill</a>
        </aside><main><p>Current question</p><input aria-label="Answer"></main>'''
        await self.page.route('http://delta.test/**',lambda route:route.fulfill(body=body,content_type='text/html'))
        await self.page.goto('http://delta.test/app/student/1/2/current')

        self.assertTrue(await self.ctrl.advance_to_next())
        self.assertTrue(self.page.url.endswith('/next'))

    async def test_does_not_skip_an_incomplete_current_skill(self):
        body='''<aside>
        <a href="/app/student/1/2/current">0 out of 5 complete. Current skill</a>
        <a href="/app/student/1/2/next">0 out of 5 complete. Next skill</a>
        </aside><main><p>Current question</p><input aria-label="Answer"></main>'''
        await self.page.route('http://delta.test/**',lambda route:route.fulfill(body=body,content_type='text/html'))
        await self.page.goto('http://delta.test/app/student/1/2/current')

        self.assertFalse(await self.ctrl.advance_to_next())
        self.assertTrue(self.page.url.endswith('/current'))

    async def test_y_variable_equation(self):
        await self.page.set_content('''<main><p>Solve y+1=4</p><input id="answer"><button onclick="document.querySelector('[role=status]').textContent=(document.querySelector('#answer').value==='3'?'Correct!':'Incorrect')">Submit</button><div role="status"></div></main>''')
        output=await self.ctrl.run('Solve for y')
        self.assertIn('observed: 1',output)

    async def test_submit_requires_yes_before_grading(self):
        await self.page.set_content('''<main><p>Solve x+1=3</p><input id="answer">
        <button onclick="document.querySelector('[role=dialog]').hidden=false">Submit Answer</button>
        <div role="status"></div></main>
        <div role="dialog" hidden>Are you sure you want to submit your answer?
        <button onclick="window.confirmCount=(window.confirmCount||0)+1;this.parentElement.hidden=true;document.querySelector('[role=status]').textContent=document.querySelector('#answer').value==='2'?'Correct!':'Incorrect'">Yes</button>
        <button>No</button></div>''')
        output=await self.ctrl.run('Solve and submit this question')
        self.assertIn('observed: 1',output)
        self.assertEqual(await self.page.evaluate('window.confirmCount'),1)

    async def test_live_verify_solution_without_dialog_role(self):
        await self.page.set_content('''<main><p>Solve x+1=3</p><input id="answer">
        <button onclick="setTimeout(()=>document.querySelector('#verify').hidden=false,400)">Submit Answer</button>
        <div role="status"></div></main>
        <div id="verify" hidden><div><h2>Verify Solution</h2>
        <p>Are you sure you want to submit this answer?</p><div>No<button>No</button>
        <button onclick="window.confirmCount=(window.confirmCount||0)+1;document.querySelector('#verify').hidden=true;document.querySelector('[role=status]').textContent='Correct!'">Yes</button>
        </div></div></div><button hidden>Yes</button>''')
        output=await self.ctrl.run('Solve and submit this question')
        self.assertIn('observed: 1',output)
        self.assertEqual(await self.page.evaluate('window.confirmCount'),1)

    async def test_incorrect_site_feedback_does_not_report_success(self):
        await self.page.set_content('''<main><p>Solve x+3=5</p><input><button onclick="document.querySelector('[role=status]').textContent='Incorrect'">Submit</button><div role="status"></div></main>''')
        output=await self.ctrl.run('Solve question')
        self.assertIn('incorrect',output.lower())
        self.assertNotIn('observed: 1',output)

    async def test_whole_assignment_moves_on_from_reviewed_incorrect_screen(self):
        await self.page.set_content('''<main>
        <h2>Solution</h2><p>Your Answer</p><p>Incorrect</p>
        <button id="next">Next Problem</button>
        </main>
        <script>
        document.querySelector('#next').addEventListener('click', () => {
            document.querySelector('main').innerHTML =
                '<p>Solve x+1=3</p><input id="answer"><button id="submit">Submit</button><div id="status" role="status"></div>';
            document.querySelector('#submit').addEventListener('click', () => {
                document.querySelector('#status').textContent =
                    document.querySelector('#answer').value === '2' ? 'Correct!' : 'Incorrect';
            });
        });
        </script>''')

        output=await self.ctrl.run('Finish the whole DeltaMath assignment')

        self.assertIn('1 question(s) completed',output)
        self.assertIn('1 incorrect question(s) recorded',output)
        self.assertEqual(await self.page.locator('#answer').input_value(),'2')
        self.assertEqual(await self.page.get_by_role('status').inner_text(),'Correct!')

    async def test_plain_correct_label_on_graded_solution(self):
        await self.page.set_content('''<main><p>Solve x+1=3</p><input>
        <button onclick="document.querySelector('#result').innerHTML='<h2>Correct</h2><h3>Your Answer</h3>'">Submit</button>
        <div id="result"></div></main>''')
        self.assertIn('observed: 1',await self.ctrl.run('Solve this question'))

    async def test_two_consecutive_questions_only_after_acceptance(self):
        await self.page.set_content('''<main><p id="q">Solve x+1=3</p><input id="answer">
        <button onclick="document.querySelector('[role=status]').textContent=((document.querySelector('#answer').value === (document.querySelector('#q').textContent.includes('=3')?'2':'3')) ? 'Correct!' : 'Incorrect')">Submit</button>
        <button onclick="document.querySelector('#q').textContent='Solve x+1=4';document.querySelector('#answer').value='';document.querySelector('[role=status]').textContent=''">Next Question</button>
        <div role="status"></div></main>''')
        result=await self.ctrl.run('Solve 2 questions')
        self.assertIn('observed: 2',result)
        self.assertEqual(await self.page.locator('#answer').input_value(),'3')

if __name__=='__main__':unittest.main()

# This integration uses local synthetic questions only, never the live DeltaMath site.
