import asyncio
import unittest
from safe_entry import fill_known_field

class Locator:
    def __init__(self):
        self.info=dict(tag='input',type='text',math=False,editable=False,disabled=False,readonly=False,visible=True)
        self.value='';self.fills=0;self.n=1
    async def count(self): return self.n
    async def evaluate(self,script,**kwargs): return self.info if 'tag:' in script else self.value
    async def fill(self,value,**kwargs): self.fills+=1;self.value=value

class Browser:
    def __init__(self): self.lock=asyncio.Lock();self.field=Locator()
    async def page(self): return self
    def locator(self,selector): return self.field

class EntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_mathquill_not_filled(self):
        b=Browser();b.field.info['math']=True
        self.assertIn('[MATH_EDITOR]',await fill_known_field(b,'field','2'))
        self.assertEqual(b.field.fills,0)
    async def test_missing_target(self):
        b=Browser();b.field.n=0
        self.assertIn('[STALE_FIELD]',await fill_known_field(b,'field','2'))
    async def test_readonly(self):
        b=Browser();b.field.info['readonly']=True
        self.assertIn('[FIELD_NOT_READY]',await fill_known_field(b,'field','2'))
    async def test_success_readback(self):
        b=Browser()
        self.assertIn('matching readback',await fill_known_field(b,'field','2'))
    async def test_lock_timeout(self):
        b=Browser();await b.lock.acquire()
        result=await fill_known_field(b,'field','2',budget=.02)
        self.assertIn('[ENTRY_TIMEOUT]',result)
        self.assertEqual(b.field.fills,0)
        b.lock.release()
    async def test_fill_hang_cancelled(self):
        b=Browser()
        async def hang(*args,**kwargs): await asyncio.Event().wait()
        b.field.fill=hang
        self.assertIn('[ENTRY_TIMEOUT]',await fill_known_field(b,'field','2',budget=.02))
        self.assertFalse(b.lock.locked())
    async def test_button_rejected(self):
        b=Browser();b.field.info['tag']='button';b.field.info['type']='button'
        self.assertIn('[NOT_TEXT_FIELD]',await fill_known_field(b,'field','2'))

@unittest.skip("Obsolete LangGraph loop replaced by unified_controller; see test_unified_controller.")
class GraphEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_failures_end_graph(self):
        import os
        from unittest.mock import AsyncMock,patch
        import agent
        from langchain_core.messages import AIMessage,HumanMessage
        class Model:
            calls=0
            async def ainvoke(self,*args,**kwargs):
                self.calls+=1
                return AIMessage(content='',tool_calls=[{'name':'fill','args':{'selector':'field','value':'2'},'id':str(self.calls)}])
        model=Model()
        token=agent.ENTRY_FAILURES.set({})
        try:
            with patch.dict(os.environ,{'GOOGLE_API_KEY':'test-key'}), patch.object(agent,'ChatGoogleGenerativeAI') as constructor, patch('safe_entry.fill_known_field',new_callable=AsyncMock) as entry:
                constructor.return_value.bind_tools.return_value=model
                entry.return_value='[MATH_EDITOR] use dedicated entry'
                graph=agent.build_graph()
                result=await graph.ainvoke({'messages':[HumanMessage(content='enter 2')]})
                self.assertEqual(entry.await_count,2)
                self.assertIn('[INPUT_STALLED]',result['messages'][-1].content)
                self.assertEqual(model.calls,3)
        finally: agent.ENTRY_FAILURES.reset(token)

if __name__=='__main__': unittest.main()
