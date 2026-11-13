"""Regression: model JSON often contains explicit null for fields it does not use."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from unified_controller import Plan, Check, UnifiedController, geometry_valid
from vision_math import VisualResult


class NullableModelResponseTests(unittest.TestCase):
    def test_empty_unused_geometry_lists_from_live_graph_plan(self):
        plan=Plan(target_rays='',answer_rays='',opposite_rays='')
        self.assertEqual((plan.target_rays,plan.answer_rays,plan.opposite_rays),([],[],[]))
        self.assertFalse(geometry_valid(Plan(geometry_relation='linear_pair',target_rays='')))

    def test_exact_reported_six_nulls(self):
        data={
            'action':'answer', 'summary':'Solve x=2',
            'equation':'x=2', 'submit':True,
            'geometry_relation':None,'vertex':None,
            'target_rays':None,'answer_rays':None,
            'opposite_rays':None,'uncertainty':None
        }
        plan=Plan.model_validate(data)
        self.assertEqual(plan.geometry_relation, '')
        self.assertEqual(plan.vertex, '')
        self.assertEqual(plan.target_rays, [])
        self.assertEqual(plan.answer_rays, [])
        self.assertEqual(plan.opposite_rays, [])
        self.assertEqual(plan.uncertainty, '')
        self.assertEqual(plan.equation,'x=2')
        self.assertTrue(plan.submit)
        self.assertTrue(geometry_valid(plan))

    def test_null_answers_only_when_equation_is_present(self):
        p=Plan.model_validate({'action':'answer','summary':'Two roots',
            'answers':None,'equation':'x^2=4','method':None,
            'submit':True,'variable':None})
        self.assertEqual(p.answers,[])
        self.assertEqual(p.variable,'x')

    def test_null_action_and_submit_fail_safe(self):
        p=Plan.model_validate({'action':None,'summary':None,'submit':None,
            'answers':['2']})
        self.assertEqual(p.action,'report')
        self.assertFalse(p.submit)
        self.assertEqual(p.summary,'')

    def test_null_geometry_with_claimed_linear_pair_remains_invalid(self):
        p=Plan.model_validate({'action':'answer','summary':'angle',
            'geometry_relation':'linear_pair', 'target_rays':None,
            'answer_rays':None, 'opposite_rays':None})
        self.assertFalse(geometry_valid(p))

    def test_wrong_nonnull_type_is_still_rejected(self):
        with self.assertRaises(ValidationError):
            Plan.model_validate({'action':'answer','summary':'x',
                'target_rays':42})

    def test_mutable_default_lists_are_not_shared(self):
        a=Plan.model_validate({'target_rays':None})
        b=Plan.model_validate({'target_rays':None})
        a.target_rays.append('A')
        self.assertEqual(b.target_rays,[])

    def test_check_null_does_not_approve_submission(self):
        result=Check.model_validate({'entry_matches':None,'math_correct':None,
            'all_solutions_present':None,'reason':None})
        self.assertFalse(result.entry_matches)
        self.assertFalse(result.math_correct)
        self.assertFalse(result.all_solutions_present)
        self.assertTrue(result.reason)

    def test_vision_nulls_not_a_candidate(self):
        result=VisualResult.model_validate({'status':None,'answers':None,
            'diagram_observations':None,'uncertainty':None,'calculations':None,
            'entry_comparison':None})
        self.assertEqual(result.status,'needs_review')
        self.assertEqual(result.answers,[])
        self.assertEqual(result.entry_comparison,'unknown')


class RealModelParsingPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_ask_parses_nulls_from_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctrl=UnifiedController(None,None,None,None,None,None,
                'test', lambda _:None, Path(tmp)/'attempts.db')
            response={'action':'answer','summary':'Solve','equation':'x=3',
                'geometry_relation':None,'vertex':None,'target_rays':None,
                'answer_rays':None,'opposite_rays':None,'uncertainty':None}
            with patch('unified_controller.generate_json',new_callable=AsyncMock,
                return_value=response) as ai:
                plan=await ctrl.ask('plan',{'observed':{'text':'Solve x=3'}},b'pixels')
            self.assertEqual(plan.equation,'x=3')
            self.assertEqual(plan.target_rays,[])
            ai.assert_awaited_once()

    async def test_check_ask_rejects_unknown_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctrl=UnifiedController(None,None,None,None,None,None,
                'test', lambda _:None, Path(tmp)/'attempts.db')
            with patch('unified_controller.generate_json',new_callable=AsyncMock,
                return_value={'entry_matches':None,'math_correct':None,
                              'all_solutions_present':None,'reason':None}):
                check=await ctrl.ask('check',{},b'pixels')
            self.assertFalse(check.entry_matches and check.math_correct and check.all_solutions_present)


if __name__=='__main__':
    unittest.main()
