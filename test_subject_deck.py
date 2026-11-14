import unittest
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
from subject_browser import SubjectController,whole_deck_request


class DeckTests(unittest.IsolatedAsyncioTestCase):
    def controller(self,results):
        ctrl=object.__new__(SubjectController)
        ctrl.emit=lambda _:None
        ctrl._run_once=AsyncMock(side_effect=results)
        return ctrl

    async def test_whole_deck_continues_beyond_one_answer_and_five_lessons(self):
        ctrl=self.controller(['__instruction_advanced__']*6+['Website acceptance observed: correct']*3+['__deck_complete__'])
        with patch('subject_browser.asyncio.sleep',new=AsyncMock()):
            result=await ctrl.run('Complete the whole deck https://wow.boomlearning.com/play/example')
        self.assertIn('Whole deck complete',result)
        self.assertIn('3 answers accepted',result)
        self.assertEqual(ctrl._run_once.await_count,10)
        self.assertNotIn('https://',ctrl._run_once.call_args_list[1].args[0])

    async def test_single_card_still_stops(self):
        ctrl=self.controller(['Website acceptance observed: correct'])
        self.assertIn('Website acceptance',await ctrl.run('Complete one card'))
        self.assertEqual(ctrl._run_once.await_count,1)

    async def test_blocker_is_paused_not_completed(self):
        ctrl=self.controller(['Website acceptance observed: correct','Answer interaction completed; website correctness was not confirmed.'])
        with patch('subject_browser.asyncio.sleep',new=AsyncMock()):
            result=await ctrl.run('Finish the whole thing')
        self.assertIn('Deck paused after 1',result)
        self.assertIn('not complete',result)
        self.assertEqual(ctrl._run_once.await_count,2)

    async def test_explicit_rejection_gets_bounded_correction(self):
        ctrl=self.controller(['Website reported incorrect.','Website acceptance observed: correct','__deck_complete__'])
        ctrl.last_plan=('old',)
        with patch('subject_browser.asyncio.sleep',new=AsyncMock()):
            result=await ctrl.run('Complete the whole deck')
        self.assertIn('Whole deck complete',result)
        self.assertIn('explicitly rejected',ctrl._run_once.call_args_list[1].args[0])

    def test_translation_does_not_start_whole_deck(self):
        self.assertFalse(whole_deck_request('Translate the whole deck'))

    async def test_unsubmitted_plan_replans_but_pending_submission_does_not(self):
        for pending in (None,'submission_pending'):
            ctrl=self.controller(['Not entered: incomplete plan','__deck_complete__'])
            ctrl.last_signature='card'
            ctrl.journal=SimpleNamespace(get=lambda _:pending)
            result=await ctrl.run('Finish the whole thing')
            self.assertEqual(ctrl._run_once.await_count,1 if pending else 2)
            self.assertIn('Deck paused' if pending else 'Whole deck complete',result)

    async def test_screenshot_timeout_uses_read_only_capture(self):
        import base64
        from subject_browser import card_screenshot,PlaywrightTimeoutError
        session=SimpleNamespace(send=AsyncMock(return_value={'data':base64.b64encode(b'png').decode()}),detach=AsyncMock())
        page=SimpleNamespace(bring_to_front=AsyncMock(),screenshot=AsyncMock(side_effect=PlaywrightTimeoutError('timeout')),
            context=SimpleNamespace(new_cdp_session=AsyncMock(return_value=session)))
        self.assertEqual(await card_screenshot(page),b'png')
        self.assertEqual(session.send.call_args.args[0],'Page.captureScreenshot')
        session.detach.assert_awaited_once()


if __name__=='__main__':unittest.main()
