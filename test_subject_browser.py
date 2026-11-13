import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from playwright.async_api import async_playwright
from subject_browser import SubjectController
from subject_solver import SubjectAnswer,SubjectCheck
from test_subject_solver import candidate


@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS')=='1','Set RUN_BROWSER_TESTS=1 for Chrome fixtures')
class SubjectBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw=await async_playwright().start()
        self.chrome=await self.pw.chromium.launch(headless=True,executable_path=os.getenv('TEST_CHROME_PATH') or None)
        self.page=await self.chrome.new_page()
        self.tmp=tempfile.TemporaryDirectory()
        browser=SimpleNamespace(lock=asyncio.Lock(),start=AsyncMock(),subject_page=self.page)
        self.ctrl=SubjectController(browser,'test',lambda _:None,Path(self.tmp.name)/'subject.db','Spanish')
        self.patch=patch('subject_browser.boom_activity',return_value=True)
        self.patch.start()
        await self.page.set_content('''<p>Yo ___ estudiante.</p>
        <button onclick="window.clicks=(window.clicks||0)+1;document.querySelector('#status').textContent='Correct!'">soy</button>
        <button onclick="window.wrong=true">estoy</button><p id="status"></p>''')
        async def solve(request,card,image):
            raw=candidate();raw['target_id']=next(c['id'] for c in card['controls'] if c['label']=='soy')
            return SubjectAnswer(**raw),SubjectCheck(correct=True,target_matches=True,reason='Agreement checked')
        self.ctrl.solver.solve=solve

    async def asyncTearDown(self):
        self.patch.stop()
        await self.chrome.close()
        await self.pw.stop()
        self.tmp.cleanup()

    async def test_one_verified_choice_and_feedback(self):
        result=await self.ctrl.run('Solve the visible card')
        self.assertIn('Website acceptance observed',result)
        self.assertEqual(await self.page.evaluate('window.clicks'),1)
        self.assertIsNone(await self.page.evaluate('window.wrong'))

    async def test_translation_never_clicks(self):
        result=await self.ctrl.run('Translate the visible card')
        self.assertIn('Suggestion only',result)
        self.assertIsNone(await self.page.evaluate('window.clicks'))

    async def test_failed_second_check_never_clicks(self):
        original=self.ctrl.solver.solve
        async def solve(*args):
            answer,check=await original(*args)
            check.correct=False
            return answer,check
        self.ctrl.solver.solve=solve
        self.assertIn('verification failed',await self.ctrl.run('Solve the visible card'))
        self.assertIsNone(await self.page.evaluate('window.clicks'))

    async def test_changed_question_never_clicks(self):
        original=self.ctrl.solver.solve
        async def change(*args):
            result=await original(*args)
            await self.page.locator('p').first.evaluate("el=>el.textContent='Yo ___ cansado.'")
            return result
        self.ctrl.solver.solve=change
        self.assertIn('card changed',await self.ctrl.run('Solve the visible card'))
        self.assertIsNone(await self.page.evaluate('window.clicks'))

    async def test_unknown_feedback_does_not_retry(self):
        await self.page.locator('button').first.evaluate("el=>el.onclick=()=>window.clicks=(window.clicks||0)+1")
        self.assertIn('not confirmed',await self.ctrl.run('Solve the visible card'))
        self.assertIn('Previous subject-card attempt',await self.ctrl.run('Solve the visible card'))
        self.assertEqual(await self.page.evaluate('window.clicks'),1)

    async def test_instruction_advances_then_answers_one_question(self):
        await self.page.set_content('''<p id="lesson">Ser is used for identity.</p>
        <button onclick="document.querySelector('#lesson').textContent='Yo ___ estudiante.';this.textContent='soy';this.onclick=()=>document.querySelector('#status').textContent='Correct!'">Next</button>
        <p id="status"></p>''')
        original=self.ctrl.solver.solve
        async def solve(request,card,image):
            if 'Ser is used' not in card['text']:return await original(request,card,image)
            raw=candidate();raw.update(action='instruction',answer='Ser describes identity.',target_id=card['controls'][0]['id'])
            return SubjectAnswer(**raw),SubjectCheck(correct=True,target_matches=True,reason='Instruction card only')
        self.ctrl.solver.solve=solve
        self.assertIn('Website acceptance observed',await self.ctrl.run('Solve the visible card'))

    async def test_matching_drag_layout_verified_before_submission(self):
        await self.page.set_content('''<style>.drag-source{display:block;width:100px;height:35px;background:orange}.drag-zone{display:inline-block;width:160px;height:120px;border:1px solid}</style>
        <p>Match each word to its translation.</p>
        <div class="drag-zone" ondragover="event.preventDefault()" ondrop="event.preventDefault();this.appendChild(document.getElementById(event.dataTransfer.getData('text/plain')))">short</div>
        <div class="drag-zone" ondragover="event.preventDefault()" ondrop="event.preventDefault();this.appendChild(document.getElementById(event.dataTransfer.getData('text/plain')))">tired</div>
        <div id="bajo" class="drag-source" draggable="true" ondragstart="event.dataTransfer.setData('text/plain',this.id)">bajo</div>
        <div id="cansado" class="drag-source" draggable="true" ondragstart="event.dataTransfer.setData('text/plain',this.id)">cansado</div>
        <button onclick="document.querySelector('#status').textContent=[...document.querySelectorAll('.drag-zone')].map(e=>e.innerText.replace(/\\s/g,'')).join(',')==='shortbajo,tiredcansado'?'Correct!':'Incorrect'">Submit</button><p id="status"></p>''')
        async def solve(request,card,image):
            by_label={c['label'].strip():c['id'] for c in card['controls']}
            raw=candidate();raw.update(action='match',matches=[dict(source_id=by_label['bajo'],target_id=by_label['short']),dict(source_id=by_label['cansado'],target_id=by_label['tired'])])
            return SubjectAnswer(**raw),SubjectCheck(correct=True,target_matches=True,reason='Translation checked')
        self.ctrl.solver.solve=solve
        self.ctrl.solver.verify_entry=AsyncMock(return_value=SubjectCheck(correct=True,target_matches=True,reason='Both words placed'))
        self.assertIn('Website acceptance observed',await self.ctrl.run('Solve the visible card'))
        self.ctrl.solver.verify_entry.assert_awaited_once()

    async def test_incomplete_matches_never_interact(self):
        from subject_browser import READ_CARD,fingerprint
        await self.page.set_content('<div class="drag-source">bajo</div><div class="drag-zone">short</div>')
        card=await self.page.evaluate(READ_CARD,'test')
        raw=candidate();raw.update(action='match',matches=[])
        self.assertIn('exactly once',await self.ctrl.match_card(self.page,card,fingerprint(card),SubjectAnswer(**raw),'test'))

    async def test_verb_and_origin_tile_both_completed_before_submit(self):
        from spanish_rules import category_control
        await self.page.set_content('''<p>Fill the verb and choose DOCTOR. Ellos ___ de India.</p><input id="verb">
        <div style="display:flex;gap:10px">
        <button class="ol_answer" role="button">D</button><button class="ol_answer" role="button" onclick="window.category='Origin'">O</button>
        <button class="ol_answer" role="button">C</button><button class="ol_answer" role="button">T</button>
        <button class="ol_answer" role="button" onclick="window.category='Occupation'">O</button><button class="ol_answer" role="button">R</button></div>
        <button onclick="window.submits=(window.submits||0)+1;document.querySelector('#status').textContent=document.querySelector('#verb').value==='son'&&window.category==='Origin'?'Correct!':'Incorrect'">Submit</button><p id="status"></p>''')
        async def solve(request,card,image):
            raw=candidate();raw.update(action='form',acronym='DOCTOR',category='Origin',answer='son; Origin',entries=[
                dict(target_id=next(c['id'] for c in card['controls'] if c['kind']=='text'),value='son'),
                dict(target_id=category_control(card['controls'],'DOCTOR','Origin'),value='')])
            return SubjectAnswer(**raw),SubjectCheck(correct=True,target_matches=True,reason='Both checked')
        self.ctrl.solver.solve=solve
        self.ctrl.solver.verify_entry=AsyncMock(return_value=SubjectCheck(correct=True,target_matches=True,reason='Verb and Origin selected'))
        self.assertIn('Website acceptance observed',await self.ctrl.run('Solve the visible card'))
        self.assertEqual(await self.page.evaluate('window.category'),'Origin')
        self.assertEqual(await self.page.evaluate('window.submits'),1)
        self.ctrl.solver.verify_entry.assert_awaited_once()

    async def test_missing_or_wrong_category_blocks_all_entry(self):
        from subject_browser import READ_CARD,fingerprint
        from spanish_rules import category_control
        await self.page.set_content('<input><div style="display:flex">'+''.join(
            f'<button class="ol_answer" role="button">{letter}</button>' for letter in 'DOCTOR')+'</div>')
        card=await self.page.evaluate(READ_CARD,'category-test')
        field=next(c['id'] for c in card['controls'] if c['kind']=='text')
        raw=candidate();raw.update(action='form',acronym='DOCTOR',category='Origin',entries=[dict(target_id=field,value='son')])
        result=await self.ctrl.fill_card(self.page,card,fingerprint(card),SubjectAnswer(**raw),'test')
        self.assertIn('category choice is missing',result)
        raw['entries'].append(dict(target_id=category_control(card['controls'],'DOCTOR','Occupation'),value=''))
        result=await self.ctrl.fill_card(self.page,card,fingerprint(card),SubjectAnswer(**raw),'test')
        self.assertIn('does not match Origin',result)
        self.assertEqual(await self.page.locator('input').input_value(),'')


if __name__=='__main__':unittest.main()
