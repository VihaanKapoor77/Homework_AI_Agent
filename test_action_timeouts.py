import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from test_safe_entry import Browser
from safe_entry import act_on_target

class ActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_hidden_math_textarea_never_clicked(self):
        b=Browser(); b.field.info.update(tag='textarea',math=True,visible=False)
        b.field.click=AsyncMock()
        self.assertIn('[MATH_EDITOR]',await act_on_target(b,'textarea'))
        b.field.click.assert_not_awaited()

    async def test_visible_button_clicked_once(self):
        b=Browser(); b.field.info.update(tag='button',type='button')
        b.field.click=AsyncMock()
        self.assertIn('completed',await act_on_target(b,'button'))
        b.field.click.assert_awaited_once_with(timeout=5000)

    async def test_hanging_click_cancels_and_releases_lock(self):
        b=Browser()
        async def hang(**kwargs): await asyncio.Event().wait()
        b.field.click=hang
        self.assertIn('[ACTION_TIMEOUT]',await act_on_target(b,'button',budget=.01))
        self.assertFalse(b.lock.locked())

    async def test_math_typing_blocked(self):
        b=Browser(); b.field.info['math']=True
        b.field.press_sequentially=AsyncMock()
        self.assertIn('[MATH_EDITOR]',await act_on_target(b,'math',text='1/2x'))
        b.field.press_sequentially.assert_not_awaited()

    async def test_delta_failure_is_visible(self):
        import agent
        b=Browser(); messages=[]
        with patch.object(agent,'browser',b), patch.object(agent,'emit',messages.append), patch.object(agent.delta,'enter',AsyncMock(side_effect=ValueError('Stale snapshot'))):
            result=await agent.delta_action('enter')
        self.assertIn('Stale snapshot',result)
        self.assertTrue(any('Stale snapshot' in m for m in messages))
        self.assertFalse(b.lock.locked())

    async def test_browser_delta_does_not_reacquire_lock(self):
        import agent
        b=Browser(); await b.lock.acquire()
        with patch.object(agent,'browser',b), patch.object(agent.delta,'enter',AsyncMock(return_value={'readback_matches':True})):
            result=await asyncio.wait_for(agent.delta_browser_result('enter'),.2)
        self.assertIn('true',result.extracted_content)
        b.lock.release()

    async def test_dedicated_entry_timeout_is_visible(self):
        import agent
        from safe_entry import bounded_action
        b=Browser(); messages=[]
        async def hang(*args,**kwargs): await asyncio.Event().wait()
        async def short(operation,emit): return await bounded_action(operation,emit,budget=.01)
        with patch.object(agent,'browser',b), patch.object(agent,'emit',messages.append), patch.object(agent.delta,'enter',hang), patch('safe_entry.bounded_action',short):
            result=await agent.delta_action('enter')
        self.assertIn('[ACTION_TIMEOUT]',result)
        self.assertIn(result,messages)
        self.assertFalse(b.lock.locked())
