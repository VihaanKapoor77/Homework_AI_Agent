import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from unified_controller import Plan, UnifiedController


class VisualFallbackTests(unittest.IsolatedAsyncioTestCase):
    def test_numeric_uncertainty_from_live_model(self):
        self.assertEqual(Plan(uncertainty=0.0).uncertainty,'')
        self.assertTrue(Plan(uncertainty=0.2).uncertainty)

    def test_live_additional_solution_label(self):
        from delta_workflow import ADD
        self.assertIsNotNone(ADD.fullmatch('Additional Solution'))

    def test_unavailable_readback_requires_visual_check(self):
        entry={'used_keyboard':True,'requires_visual_verification':True,
               'observed':{'kind':'mathquill','latex':None}}
        self.assertTrue(UnifiedController.readback_or_visual(entry))
        entry['observed']['latex']='wrong'
        self.assertFalse(UnifiedController.readback_or_visual(entry))
        self.assertFalse(UnifiedController.readback_or_visual({}))

    def test_boolean_uncertainty_in_both_visual_schemas(self):
        from vision_math import VisualResult
        for schema in (Plan,VisualResult):
            with self.subTest(schema=schema.__name__):
                self.assertEqual(schema.model_validate({'uncertainty':False}).uncertainty,'')
                self.assertTrue(schema.model_validate({'uncertainty':True}).uncertainty)
                self.assertEqual(schema.model_validate({'uncertainty':'Label unreadable'}).uncertainty,'Label unreadable')

    async def test_unsupported_syntax_withholds_visual_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            controller=UnifiedController(None,None,None,
                AsyncMock(return_value='{"error":"Unsupported syntax: invalid expression."}'),
                None,None,'test',lambda _:None,Path(folder)/'journal.db')
            plan=Plan(action='answer',equation='2x=10',answers=['5'])
            self.assertEqual(await controller.answers_for(plan),[])

    async def test_live_quadratic_replaces_sign_reversed_candidates(self):
        from math_solver import calculate
        async def solve(operation,expression,variable):
            return calculate(operation,expression,variable)
        with tempfile.TemporaryDirectory() as folder:
            controller=UnifiedController(None,None,None,solve,None,None,'test',lambda _:None,Path(folder)/'journal.db')
            for equation in ('3x^2+3x-9=4x-7','3x² + 3x − 9 = 4x − 7','3*x^{2}+3*x-9=4*x-7'):
                roots=await controller.answers_for(Plan(equation=equation,answers=['2/3','-1']))
                self.assertEqual([root.replace(' ','') for root in roots],[r'-\frac{2}{3}','1'])

    async def test_unsupported_syntax_does_not_invent_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            controller=UnifiedController(None,None,None,
                AsyncMock(return_value='{"error":"Unsupported syntax"}'),
                None,None,'test',lambda _:None,Path(folder)/'journal.db')
            self.assertEqual(await controller.answers_for(Plan(equation='2x=10')),[])
