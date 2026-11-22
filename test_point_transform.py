import unittest
from point_transform import coordinate, point_choice, solve_point


class PointTests(unittest.TestCase):
    def test_timed_request_count(self):
        from unified_controller import UnifiedController
        self.assertEqual(UnifiedController.question_goal('Do this, 100 seconds for 10 questions'),10)

    def test_user_example_and_axes(self):
        for axis,expected in [('y = x',(2,-5)),('y = -x',(-2,5)),('x-axis',(-5,-2)),('y-axis',(5,2))]:
            self.assertEqual(solve_point(f'Reflection over the line {axis} of the point (-5, 2)'),expected)

    def test_rotation(self):
        self.assertEqual(solve_point('Rotation 90 degrees clockwise about the origin of the point (-5, 2)'),(2,5))
        self.assertEqual(solve_point(r'Rotation 270^{\circ} counterclockwise around the origin of the point (-2,4)'),(4,2))

    def test_unique_choice_only(self):
        snap={'question_text':'Reflection over the line y = x of the point (-5, 2)',
              'buttons':[{'text':s} for s in ['(-2, -5)','(2, 5)','(5, 2)','(2, -5)']]}
        self.assertEqual(point_choice(snap)['text'],'(2, -5)')
        snap['buttons'].append({'text':'(2,-5)'})
        self.assertIsNone(point_choice(snap))

    def test_reject_ambiguous_or_unsupported(self):
        for text in ['Reflection over the line y = 2x of the point (-5, 2)',
                     'NOT Reflection over the line y = x of the point (-5, 2)',
                     'Reflection over the line y = x of the point (-5, 2) and then translate']:
            self.assertIsNone(solve_point(text))
        self.assertEqual(coordinate('(2, \u22125)'),(2,-5))

