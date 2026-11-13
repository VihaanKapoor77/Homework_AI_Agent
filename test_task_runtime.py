import asyncio
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import AsyncMock
from task_runtime import BrowserTimedOut,recover_once,ScheduleStore,scheduled_timestamp
from delta_workflow import enter_solution_set,ExampleNotes

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_reopens_once_and_resumes(self):
        invoke=AsyncMock(side_effect=[BrowserTimedOut('timeout'),'done']);reopen=AsyncMock();sleep=AsyncMock()
        self.assertEqual(await recover_once(invoke,reopen,lambda x:None,sleep=sleep),'done')
        sleep.assert_awaited_once_with(60);reopen.assert_awaited_once()
        self.assertEqual([c.args[0] for c in invoke.await_args_list],[False,True])
    async def test_second_timeout_is_not_looped(self):
        invoke=AsyncMock(side_effect=BrowserTimedOut());reopen=AsyncMock()
        with self.assertRaises(BrowserTimedOut): await recover_once(invoke,reopen,lambda x:None,sleep=AsyncMock())
        self.assertEqual(invoke.await_count,2);reopen.assert_awaited_once()
    async def test_cancel_does_not_restart(self):
        reopen=AsyncMock()
        with self.assertRaises(asyncio.CancelledError):
            await recover_once(AsyncMock(side_effect=asyncio.CancelledError()),reopen,lambda x:None,sleep=AsyncMock())
        reopen.assert_not_awaited()
    async def test_non_timeout_not_restarted(self):
        reopen=AsyncMock()
        with self.assertRaises(ValueError): await recover_once(AsyncMock(side_effect=ValueError()),reopen,lambda x:None)
        reopen.assert_not_awaited()

class ScheduleTests(unittest.TestCase):
    def test_eastern_example(self):
        stamp=scheduled_timestamp('2026-11-15 16:00','America/New_York',now=0)
        self.assertEqual(datetime.fromtimestamp(stamp,timezone.utc).isoformat(),'2026-11-15T21:00:00+00:00')
    def test_ambiguous_and_nonexistent_times_rejected(self):
        for when in ('2026-11-01 01:30','2026-03-08 02:30'):
            with self.assertRaises(ValueError):scheduled_timestamp(when,'America/New_York',now=0)
    def test_past_rejected(self):
        with self.assertRaises(ValueError):scheduled_timestamp('2020-01-01 10:00','UTC')
    def test_persistence_claim_once_cancel_and_missed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'jobs.db';a=ScheduleStore(path)
            job=a.add('2099-11-15 16:00','America/New_York','test')
            b=ScheduleStore(path);due=b.listing()[0]['due']
            self.assertIsNone(b.claim(due-1))
            self.assertEqual(b.claim(due)['id'],job)
            self.assertIsNone(a.claim(due))
            a.interrupt_running();self.assertEqual(a.listing()[0]['status'],'interrupted')
            job=a.add('2099-11-16 16:00','UTC','test')
            self.assertEqual(a.cancel(job),'Cancelled.')
            job=a.add('2099-11-17 16:00','UTC','test')
            due=a.listing()[0]['due'];self.assertIsNone(a.claim(due+901))
            self.assertEqual(a.listing()[0]['status'],'missed')

class Delta:
    def __init__(self,page):
        self.page=page;self.n=1;self.enters=[];self.latest={'token':'t','signature':'q','page':page}
    async def inspect(self,page):
        return {'signature':'q','snapshot_token':'t','fields':[{'id':str(i),'kind':'text'} for i in range(self.n)],'buttons':[{'text':'Add Solution','selector':'button','disabled':False}]}
    async def enter(self,*args):self.enters.append(args);return {'requires_visual_verification':False}
class Page:
    def locator(self,sel):return self
    async def count(self):return 1
    async def click(self,**kwargs):self.delta.n+=1

class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_roots_adds_field_and_enters_both(self):
        p=Page();d=Delta(p);p.delta=d
        result=await enter_solution_set(d,p,'t',['2','3'])
        self.assertEqual(d.n,2);self.assertEqual([a[3] for a in d.enters],['2','3'])
        self.assertFalse(result['submitted'])
    async def test_stale_snapshot_never_enters(self):
        p=Page();d=Delta(p)
        with self.assertRaises(ValueError): await enter_solution_set(d,p,'old',['2','3'])
        self.assertFalse(d.enters)
    async def test_extra_fields_rejected(self):
        p=Page();d=Delta(p);d.n=3
        with self.assertRaises(ValueError):await enter_solution_set(d,p,'t',['2','3'])
        self.assertFalse(d.enters)
    def test_example_memory_retrieves_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ExampleNotes(Path(tmp)/'examples.db')
            store.save('quadratic equation',{'method':'Factor and set each factor to zero.'})
            self.assertEqual(len(store.search('solve quadratic equation')),1)
            self.assertEqual(store.search('circle diameter'),[])

class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_task_runs_once_and_records_result(self):
        import agent
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            store=ScheduleStore(Path(tmp)/'jobs.db')
            identity=store.add('2099-01-01 10:00','UTC','Open test page')
            import time
            with store.connect() as db:db.execute('UPDATE jobs SET due=?',(time.time(),))
            calls=[]
            async def fake_chat(message,history,request):
                calls.append(message)
                yield [{'role':'assistant','content':'Stopped for missing diagram labels.'}]
            with patch.object(agent,'schedule_store',store),patch.object(agent,'chat',fake_chat),patch.object(agent,'TASK_LOCK',asyncio.Lock()):
                worker=asyncio.create_task(agent.schedule_loop())
                try:
                    for _ in range(100):
                        if store.listing()[0]['status']=='finished':break
                        await asyncio.sleep(.01)
                    self.assertEqual(store.listing()[0]['status'],'finished')
                    self.assertIn('missing diagram',store.listing()[0]['result'])
                    self.assertEqual(calls,['Open test page'])
                finally:
                    worker.cancel()
                    with self.assertRaises(asyncio.CancelledError):await worker
    async def test_example_tool_reads_screenshot_and_saves_note(self):
        import agent
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            notes=ExampleNotes(Path(tmp)/'notes.db')
            page=object()
            class Browser:
                lock=asyncio.Lock()
                async def page(self):return page
            with patch.object(agent,'browser',Browser()),patch.object(agent.delta,'inspect',AsyncMock(return_value={})),patch.object(agent,'click_discovered',AsyncMock()) as click,patch.object(agent.vision_solver,'solve',AsyncMock(return_value={'status':'candidate','method':'Factor first','question':'x*x=4','answer':'-2,2'})) as vision,patch.object(agent,'example_notes',notes):
                result=await agent.learn_example_impl('quadratic equation')
            click.assert_awaited_once();vision.assert_awaited_once()
            self.assertEqual(vision.await_args.args[0],page)
            self.assertEqual(notes.search('quadratic equation')[0]['example']['method'],'Factor first')
            self.assertIn('Close the example',result)
