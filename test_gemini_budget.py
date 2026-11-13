import asyncio
import unittest
from gemini_budget import GeminiBudget, browser_model_class

class Clock:
    now=0
    def time(self): return self.now
    async def sleep(self,seconds): self.now+=seconds

class BudgetTests(unittest.IsolatedAsyncioTestCase):
    def budget(self):
        clock=Clock()
        return GeminiBudget(10,clock.time,clock.sleep),clock
    async def test_concurrent_calls_share_spacing(self):
        budget,clock=self.budget();starts=[]
        async def request(): starts.append(clock.now);return 'ok'
        await asyncio.gather(*(budget.call(request) for _ in range(20)))
        self.assertTrue(all(b-a>=6.09 for a,b in zip(starts,starts[1:])))
    async def test_retry_delay_honored(self):
        budget,clock=self.budget();starts=[]
        async def request():
            starts.append(clock.now)
            if len(starts)==1: raise RuntimeError('429 Please retry in 75.5s')
            return 'ok'
        self.assertEqual(await budget.call(request),'ok')
        self.assertGreaterEqual(starts[1]-starts[0],76.5)
    async def test_retries_bounded(self):
        budget,_=self.budget();calls=[]
        async def fail(): calls.append(1);raise RuntimeError('429 RESOURCE_EXHAUSTED')
        with self.assertRaises(RuntimeError): await budget.call(fail)
        self.assertEqual(len(calls),3)
    async def test_daily_quota_stops_future_calls(self):
        budget,_=self.budget();calls=[]
        async def fail(): calls.append(1);raise RuntimeError('429 requests per day quota exceeded')
        for _ in range(2):
            with self.assertRaises(RuntimeError): await budget.call(fail)
        self.assertEqual(len(calls),1)
    async def test_non_quota_errors_not_retried(self):
        budget,_=self.budget();calls=[]
        async def fail(): calls.append(1);raise ValueError('400 invalid input')
        with self.assertRaises(ValueError): await budget.call(fail)
        self.assertEqual(len(calls),1)
    async def test_cancel_releases_lock(self):
        budget,_=self.budget()
        async def cancelled(seconds): raise asyncio.CancelledError()
        budget.sleep=cancelled
        await budget.reserve()
        with self.assertRaises(asyncio.CancelledError): await budget.reserve()
        self.assertFalse(budget.lock.locked())
    async def test_browser_provider_uses_shared_budget(self):
        from browser_use import ChatGoogle
        from unittest.mock import AsyncMock, patch
        budget,clock=self.budget()
        model=browser_model_class(ChatGoogle)(model='gemini-3.5-flash-lite', max_retries=1, http_options={'retry_options': {'attempts': 1}})
        with patch('gemini_budget.BUDGET',budget), patch.object(ChatGoogle,'ainvoke',AsyncMock(return_value='ok')) as invoke:
            self.assertEqual(await model.ainvoke([]),'ok')
            self.assertEqual(await model.ainvoke([]),'ok')
        self.assertEqual(invoke.await_count,2)
        self.assertGreaterEqual(clock.now,6.1)
        self.assertEqual(model.max_retries,1)

    async def test_langchain_provider_uses_shared_budget(self):
        from unittest.mock import AsyncMock,patch
        from gemini_budget import paced_invoke
        budget,clock=self.budget();model=AsyncMock()
        with patch('gemini_budget.BUDGET',budget):
            await paced_invoke(model,['main'])
            await paced_invoke(model,['vision'])
        self.assertGreaterEqual(clock.now,6.1)
        self.assertEqual(model.ainvoke.await_count,2)
