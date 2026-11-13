import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from adaptive_math import MathMemory
from math_solver import calculate

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.memory=MathMemory(Path(self.temp.name)/'memory.sqlite3')
    def tearDown(self): self.temp.cleanup()
    def test_seed_exact(self):
        result=self.memory.search('Solve 3*x+5=20')
        first=result['matches'][0]
        self.assertEqual(first['match'],'exact_text')
        self.assertEqual(first['result']['result'],'{5}')
        self.assertEqual(first['source'],'original_example')
    def test_new_values_are_not_exact(self):
        first=self.memory.search('Solve 3*x+5=23','linear equation')['matches'][0]
        self.assertEqual(first['match'],'similar_method')
    def test_persistence(self):
        self.memory.save('Solve 7*x=49','linear','Divide by seven','solve','7*x=49','x',calculate('solve','7*x=49'))
        other=MathMemory(self.memory.path)
        self.assertEqual(other.search('Solve 7*x=49')['matches'][0]['result']['result'],'{7}')
    def test_failed_results_not_saved(self):
        with self.assertRaises(ValueError): self.memory.save('test','topic','method','solve','x','x',{'error':'bad'})
        with self.assertRaises(ValueError): self.memory.save('test','topic','method','solve','x','x',{'complete':False})
    def test_conflicting_formulations_preserved(self):
        for exp in ['x=2','x=3']:
            self.memory.save('ambiguous question','linear','Check original','solve',exp,'x',calculate('solve',exp))
        matches=self.memory.search('ambiguous question')['matches']
        self.assertEqual(len([m for m in matches if m['match']=='exact_text']),2)
    def test_empty_bank_miss(self):
        self.assertEqual(self.memory.search('zzzzzzzz')['matches'],[])
    def test_auto(self):
        self.assertEqual(calculate('auto','x+1=4')['result'],'{3}')
        self.assertEqual(calculate('auto','1/2+1/4')['exact'],'3/4')
    def test_seed_idempotent(self):
        self.memory.seed();self.memory.seed()
        with self.memory.connect() as conn:
            self.assertEqual(conn.execute('select count(*) from examples').fetchone()[0],15)

class IntegrationTests(unittest.TestCase):
    def test_browser_tool_schemas(self):
        import agent
        model=agent.browser_tools.registry.create_action_model()
        for name,args in [
            ('browser_math_lookup',{'problem':'Solve x=1','topic':'linear'}),
            ('browser_math_research',{'topic_query':'quadratic equation methods'}),
            ('browser_math_remember',{'problem':'Solve x=1','topic':'linear','method':'isolate x','operation':'solve','expression':'x=1'})]:
            self.assertIn(name,model.model_validate({name:args}).model_dump(exclude_none=True))
    def test_research_returns_sources_and_failure(self):
        import agent
        with patch.object(agent,'DDGS') as search:
            search.return_value.text.return_value=[{'title':'Example','href':'https://example.org/math','body':'A method'}]
            result=json.loads(asyncio.run(agent.math_research_impl('linear equations')))
            self.assertEqual(result['sources'][0]['url'],'https://example.org/math')
            search.return_value.text.side_effect=RuntimeError('offline')
            self.assertIn('MATH_RESEARCH_FAILED',asyncio.run(agent.math_research_impl('linear equations')))

if __name__=='__main__': unittest.main()
