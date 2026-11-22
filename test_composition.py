import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace
from unified_controller import UnifiedController
from composition_math import apply_step,solve_composition,composition_field_values


def snapshot(target=None):
    source=[(-3,-2),(-6,-2),(-6,-5),(-3,-6),(-2,-4)]
    target=target or [(-2,6),(-2,9),(-5,9),(-6,6),(-4,5)]
    alt=' '.join(f'left parenthesis, {x}, comma, {y}, right parenthesis' for x,y in source+target)
    return {'question_text':'Determine a series of transformations',
            'images':[{'alt':alt}], 'fields':[{'label':'select the first transformation'},
            {'label':'select the second transformation'}]}


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.controller=object.__new__(UnifiedController)

    def test_all_five_vertices_map_in_order(self):
        plan=self.controller.composition_plan(snapshot(),'solve')
        self.assertEqual(plan.composition,['rotation','270','translation','up','3'])

    def test_one_wrong_vertex_rejects_candidate(self):
        self.assertIsNone(self.controller.composition_plan(
            snapshot([(-2,6),(-2,9),(-5,9),(-6,6),(-4,4)]),'solve'))

    def test_no_submit_request_is_preserved(self):
        self.assertFalse(self.controller.composition_plan(snapshot(),'solve without submitting').submit)

    def test_live_reflection_and_dilation(self):
        source=[(1,-2),(4,-1),(5,-6),(4,-5),(2,-5)]
        target=[(-2,-4),(-8,-2),(-10,-12),(-8,-10),(-4,-10)]
        self.assertEqual(solve_composition(source,target),[['reflection','y-axis'],['dilation','2']])

    def test_combinations_preserve_every_correspondence(self):
        source=[(2,4),(6,2),(8,8),(4,6)]
        operations=[['rotation','90'],['rotation','180'],['rotation','270'],
                    ['reflection','x-axis'],['reflection','y-axis'],
                    ['dilation','2'],['dilation','1/2'],['dilation','3'],
                    ['translation','up','3'],['translation','left','4'],
                    ['translation','down','2'],['translation','right','5']]
        for first in operations:
            for second in operations:
                with self.subTest(first=first,second=second):
                    target=[apply_step(apply_step(p,first),second) for p in source]
                    steps=solve_composition(source,target)
                    self.assertIsNotNone(steps)
                    self.assertEqual([apply_step(apply_step(p,steps[0]),steps[1]) for p in source],target)


def form_fields(steps,dropdown_rotation):
    def select(options,label='',context=''):
        return dict(kind='select',label=label,context=context,options=[dict(label=a,value=b) for a,b in options])
    fields=[]
    for position,step in enumerate(steps):
        fields.append(select([(k,k) for k in ('rotation','reflection','translation','dilation')],
            'select the '+('first' if position==0 else 'second')+' transformation'))
        if step[0]=='rotation':
            if dropdown_rotation:
                fields.append(select([('90° clockwise','cw-90'),('90° counterclockwise','ccw-90'),
                    ('180° clockwise','cw-180'),('180° counterclockwise','ccw-180')],
                    'select type of rotation about the origin'))
            else:
                fields.append(dict(kind='text',label='enter number of degrees rotated counterclockwise about the origin'))
        elif step[0]=='reflection':fields.append(select([(k,k) for k in ('x-axis','y-axis')]))
        elif step[0]=='translation':
            fields.append(select([(k,k) for k in ('up','down','left','right')]))
            fields.append(dict(kind='text',label='enter number of units translated',context='unit(s)'))
        else:fields.append(dict(kind='text',label='',context='centered at the origin with a scale factor of'))
    return fields


class FormMappingTests(unittest.TestCase):
    def test_all_parameters_in_both_positions_and_both_layouts(self):
        operations=[['rotation',x] for x in ('90','180','270')]+[
            ['reflection',x] for x in ('x-axis','y-axis')]+[
            ['translation',x,'3'] for x in ('up','down','left','right')]+[
            ['dilation',x] for x in ('2','1/2','3')]
        for dropdown in (False,True):
            for first in operations:
                for second in operations:
                    with self.subTest(dropdown=dropdown,first=first,second=second):
                        steps=[first,second]
                        fields=form_fields(steps,dropdown)
                        values=composition_field_values(fields,steps)
                        offset=0
                        for step in steps:
                            if dropdown and step[0]=='rotation':
                                expected={'90':'90° counterclockwise','180':'180° clockwise','270':'90° clockwise'}[step[1]]
                                self.assertEqual(values[offset+1],expected)
                            else:self.assertEqual(values[offset:offset+len(step)],step)
                            offset+=len(step)

    def test_wrong_rotation_center_rejected(self):
        steps=[['rotation','270'],['translation','left','3']]
        fields=form_fields(steps,True)
        fields[1]['label']='rotation about (1,1)'
        with self.assertRaisesRegex(ValueError,'center'):composition_field_values(fields,steps)

    def test_missing_correct_rotation_option_rejected(self):
        steps=[['rotation','270'],['translation','left','3']]
        fields=form_fields(steps,True)
        fields[1]['options']=[{'label':'90° counterclockwise','value':'ccw-90'}]
        with self.assertRaisesRegex(ValueError,'No visible rotation'):composition_field_values(fields,steps)


class DynamicEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_parameter_changes_do_not_change_problem_identity(self):
        controller=object.__new__(UnifiedController)
        initial=snapshot()
        initial['url']='https://www.deltamath.com/app/student/test'
        plan=controller.composition_plan(initial,'solve')
        current={**initial,'snapshot_token':'fresh','math':[{'latex':r'^{\circ}'}]}
        current['fields']=[
            {'id':'0','label':'select the first transformation','value':'rotation'},
            {'id':'1','label':'enter number of degrees rotated counterclockwise about the origin','value':'270'},
            {'id':'2','label':'select the second transformation','value':'translation'},
            {'id':'3','label':'','options':[{'label':x} for x in ('up','down','left','right')],'value':'up'},
            {'id':'4','label':'enter number of units translated','value':'3'}]
        controller.delta=SimpleNamespace(inspect=AsyncMock(return_value=current),enter=AsyncMock())
        result=await controller.enter_composition(object(),initial,plan)
        self.assertEqual([f['value'] for f in result['fields']],plan.composition)
        self.assertEqual(controller.delta.enter.await_count,5)
