import unittest

from piecewise_graph import parse_rows, drawing_points, matches


AXES={'x':{'min':-10,'max':10},'y':{'min':-10,'max':10}}


class PiecewiseTests(unittest.TestCase):
    def test_live_question_open_rays(self):
        left,right=parse_rows([['3x+5','x<-3'],['2','x>2']])
        self.assertEqual(drawing_points(left,AXES),([(-4,-7),(-3,-4)],['0','2']))
        self.assertEqual(drawing_points(right,AXES),([(2,2),(3,2)],['2','0']))

    def test_fraction_slope_uses_exact_lattice_point(self):
        left,_=parse_rows([['(1)/(2)x+1','x<=2'],['-x','x>2']])
        self.assertEqual(drawing_points(left,AXES),([(0,1),(2,2)],['0','1']))

    def test_finite_interval_and_unicode_inequalities(self):
        middle,_=parse_rows([['-2x+3','\u22122\u2264x<3'],['4','x\u22653']])
        self.assertEqual(drawing_points(middle,AXES),([(-2,7),(3,-3)],['1','2']))

    def test_unsupported_or_ambiguous_math_is_rejected(self):
        for expr,domain in [('x*x','x<0'),('1/x','x<0'),('x/x','x<2'),('x**2','x<0'),('x','x!=0'),('x','0<x<0')]:
            with self.subTest(expr=expr,domain=domain),self.assertRaises(ValueError):
                parse_rows([[expr,domain],['2','x>2']])
        with self.assertRaises(ValueError):
            parse_rows([['x','x<=2'],['2','x>=2']])

    def test_offscreen_endpoints_are_not_guessed(self):
        segment,_=parse_rows([['3x+5','x<3'],['2','x>3']])
        with self.assertRaises(ValueError):drawing_points(segment,AXES)

    def test_readback_rejects_wrong_slope_endpoint_or_missing_arrow(self):
        segment,_=parse_rows([['3x+5','x<-3'],['2','x>2']])
        points,stages=drawing_points(segment,AXES)
        drawing={'handles':[{'point':[-4,-7],'stage':'0'},{'point':[-3,-4],'stage':'2'}],
                 'points':[[-5,-10],[-4,-7],[-3,-4]],'markers':['url(#arrowStart)',None]}
        self.assertTrue(matches(segment,drawing,points,stages))
        drawing['markers']=[None,None]
        self.assertFalse(matches(segment,drawing,points,stages))
        drawing['markers']=['url(#arrowStart)',None]
        drawing['handles'][1]['stage']='1'
        self.assertFalse(matches(segment,drawing,points,stages))
        drawing['handles'][1]['stage']='2'
        drawing['points'][1]=[-4,-6]
        self.assertFalse(matches(segment,drawing,points,stages))
