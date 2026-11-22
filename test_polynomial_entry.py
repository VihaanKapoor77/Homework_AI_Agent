import unittest
from unittest.mock import AsyncMock
from polynomial_entry import factor_question,normalized_polynomial
from math_keyboard import enter_keyboard


class FactorTests(unittest.TestCase):
    def snapshot(self,latex):
        return {'question_text':'Factor out GCF (Variable Only) Factor the expression completely.',
                'fields':[{'kind':'mathquill'}],'math':[{'latex':latex}]}

    def test_live_problem(self):
        self.assertEqual(normalized_polynomial(factor_question(self.snapshot('x^2y^3+xy^5'))),'xy^3(x+y^2)')

    def test_common_factor_and_sign(self):
        self.assertEqual(normalized_polynomial(factor_question(self.snapshot('x^4y^2-x^2y^3'))),'x^2y^2(x^2-y)')

    def test_ambiguous_or_unsupported(self):
        for value in ['x/2+y','x^100+y','sin(x)+y','x^2=y','x^-2+y']:
            self.assertIsNone(factor_question(self.snapshot(value)))
        snap=self.snapshot('x^2+x');snap['math'].append({'latex':'y^2+y'})
        self.assertIsNone(factor_question(snap))


class KeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_exponents_exit_and_latex_spaces_are_not_typed(self):
        field=AsyncMock();field.evaluate.return_value=''
        await enter_keyboard(field,r'x y^{3} \left(x + y^{2}\right)')
        typed=[call.args[0] for call in field.press_sequentially.call_args_list]
        self.assertEqual(typed,['x','y','^3','(','x','+','y','^2',')'])
        self.assertEqual([c.args[0] for c in field.press.call_args_list].count('ArrowRight'),2)
