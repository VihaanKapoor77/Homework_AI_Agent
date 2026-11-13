"""Exact linear piecewise graphs from rendered MathML, entered with mouse input."""
import asyncio
import ast
import math
import re
from dataclasses import dataclass

from graph_entry import READ_GRAPH
from math_solver import SYMBOLS, parse_expression


READ_ROWS = r'''() => {
 const read = e => {
   const tag=e.localName;
   if(['mphantom','mspace','mtext'].includes(tag))return '';
   if(['mi','mn','mo'].includes(tag))return e.textContent;
   if(tag==='mfrac')return '('+read(e.children[0])+')/('+read(e.children[1])+')';
   if(['mtd','mstyle','mrow'].includes(tag))return [...e.children].map(read).join('');
   throw Error('Unsupported piecewise math markup: '+tag);
 };
 const tables=[...document.querySelectorAll('math mtable')].filter(e=>e.closest('.katex')?.getClientRects().length);
 if(tables.length!==1)throw Error('Need one rendered piecewise function');
 return [...tables[0].children].map(row=>{
   if(row.children.length!==2)throw Error('Unreadable piecewise row');
   return [...row.children].map(read);
 });
}'''

READ_LINES = r'''(svg, axes) => {
 const xy=(e,x,y)=>{const p=new DOMPoint(x,y).matrixTransform(e.getScreenCTM());
   return [(p.x-axes.x.zero)/axes.x.step,(p.y-axes.y.zero)/axes.y.step];};
 return [...svg.querySelectorAll('line[myid],path[myid]')].filter(e=>e.getAttribute('stroke')!=='transparent').map(e=>{
   const id=e.getAttribute('myid'),len=e.getTotalLength();
   return {id, ends:e.getAttribute('ends'),
     markers:[e.getAttribute('marker-start'),e.getAttribute('marker-end')],
     points:[0,.25,.5,.75,1].map(t=>{const p=e.getPointAtLength(t*len);return xy(e,p.x,p.y);}),
     handles:[...svg.querySelectorAll('circle.clear-point')].filter(c=>c.getAttribute('myid')===id).map(c=>({
       point:xy(c,Number(c.getAttribute('cx')),Number(c.getAttribute('cy'))),stage:c.getAttribute('stage')}))};
 });
}'''


@dataclass(frozen=True)
class Segment:
    slope: object
    intercept: object
    left: int | None
    right: int | None
    left_closed: bool
    right_closed: bool

    def y(self, x):
        return self.slope*x+self.intercept


def parse_rows(rows):
    if not 2 <= len(rows) <= 5:
        raise ValueError('Need two to five readable piecewise rows')
    segments=[]
    for expression, condition in rows:
        expression=expression.replace('\u2212','-').replace('\u00d7','*')
        expression=re.sub(r'\)(?=x)', ')*', expression)
        if len(expression)>120 or not re.fullmatch(r'[0-9x+*/().\s-]+',expression) or '**' in expression:
            raise ValueError('Only linear piecewise expressions are supported')
        tree=ast.parse(re.sub(r'(?<=\d)\s*x', '*x', expression).strip(),mode='eval')
        if any(isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div) and
               any(isinstance(child,ast.Name) for child in ast.walk(node.right))
               for node in ast.walk(tree)):
            raise ValueError('Variable denominators are not linear graph pieces')
        expr=parse_expression(expression)
        x=SYMBOLS['x']
        m=expr.diff(x)
        b=expr.subs(x,0)
        if not m.is_Rational or not b.is_Rational or (expr-m*x-b).simplify()!=0:
            raise ValueError('Piecewise expression is not an exact linear function')
        condition=re.sub(r'\s+','',condition).replace('\u2212','-').replace('\u2264','<=').replace('\u2265','>=')
        one=re.fullmatch(r'x(<=|>=|<|>)(-?\d+)',condition)
        interval=re.fullmatch(r'(-?\d+)(<=|<)x(<=|<)(-?\d+)',condition)
        if one:
            op,value=one[1],int(one[2])
            left,right=(None,value) if op.startswith('<') else (value,None)
            lc,rc=(False,'=' in op) if left is None else ('=' in op,False)
        elif interval:
            left,right=int(interval[1]),int(interval[4])
            lc,rc=interval[2]=='<=',interval[3]=='<='
            if left>=right:raise ValueError('Empty piecewise interval')
        else:raise ValueError('Unsupported piecewise domain: '+condition)
        segments.append(Segment(m,b,left,right,lc,rc))
    ordered=sorted(segments,key=lambda s:-math.inf if s.left is None else s.left)
    for a,b in zip(ordered,ordered[1:]):
        if a.right is None or b.left is None or a.right>b.left or (a.right==b.left and a.right_closed and b.left_closed):
            raise ValueError('Overlapping piecewise domains')
    return segments


def drawing_points(segment, axes):
    def valid(x):
        y=segment.y(x)
        return y.is_Integer and axes['x']['min']<=x<=axes['x']['max'] and axes['y']['min']<=y<=axes['y']['max']
    if segment.left is not None and segment.right is not None:
        xs=[segment.left,segment.right]
    else:
        endpoint=segment.left if segment.left is not None else segment.right
        direction=1 if segment.right is None else -1
        candidates=[endpoint+direction*i for i in range(1,41) if valid(endpoint+direction*i)]
        if not candidates:raise ValueError('No second exact lattice point visible for this ray')
        xs=sorted([endpoint,candidates[0]])
    if not all(valid(x) for x in xs):
        raise ValueError('Piecewise endpoints must be visible integer grid points')
    stages=['0' if segment.left is None else ('1' if segment.left_closed else '2'),
            '0' if segment.right is None else ('1' if segment.right_closed else '2')]
    return [(x,int(segment.y(x))) for x in xs],stages


def matches(segment, drawing, points, stages):
    if len(drawing['handles'])!=2:return False
    handles=sorted(drawing['handles'],key=lambda h:h['point'][0])
    for handle,expected,stage in zip(handles,points,stages):
        if handle['stage']!=stage or any(abs(a-b)>1e-5 for a,b in zip(handle['point'],expected)):
            return False
    for x,y in drawing['points']:
        if abs(float(segment.y(x))-y)>1e-4:return False
    for i,stage in enumerate(stages):
        arrow='arrow' in (drawing['markers'][i] or '').lower()
        if arrow != (stage=='0'):return False
    return True


async def plan_piecewise(page):
    rows=await page.evaluate(READ_ROWS)
    return parse_rows(rows)


async def enter_piecewise(page, segments):
    graph=page.locator('svg.delta-graph:visible')
    if await graph.count()!=1:raise ValueError('Need one visible piecewise graph')
    await graph.scroll_into_view_if_needed()
    await graph.evaluate("e=>{e.style.userSelect='none';for(const t of e.querySelectorAll('text'))t.style.userSelect='none';}")
    axes=await graph.evaluate(READ_GRAPH)
    plans=[drawing_points(s,axes) for s in segments]
    if await graph.evaluate(READ_LINES,axes):
        raise ValueError('Graph already has lines; review or clear them before a new attempt')
    for segment,(points,stages) in zip(segments,plans):
        axes=await graph.evaluate(READ_GRAPH)
        def pixel(p):return axes['x']['zero']+p[0]*axes['x']['step'],axes['y']['zero']+p[1]*axes['y']['step']
        before=await graph.evaluate(READ_LINES,axes)
        await page.mouse.move(*pixel(points[0]))
        await page.mouse.down()
        try:await page.mouse.move(*pixel(points[1]),steps=15)
        finally:await page.mouse.up()
        await asyncio.sleep(.15)
        after=await graph.evaluate(READ_LINES,axes)
        added=[d for d in after if d['id'] not in {d['id'] for d in before}]
        if len(added)!=1:raise ValueError('Dragging did not create exactly one graph segment')
        identity=added[0]['id']
        for point,stage in zip(points,stages):
            # Observed UI cycle: filled -> open -> arrow -> filled.
            for _ in range({'1':0,'2':1,'0':2}[stage]):
                await page.mouse.click(*pixel(point))
                await asyncio.sleep(.08)
        drawings=await graph.evaluate(READ_LINES,axes)
        current=next((d for d in drawings if d['id']==identity),None)
        if not current or not matches(segment,current,points,stages):
            raise ValueError('Graph line or endpoint readback failed; no submission')
    await page.mouse.move(10,10)
    drawings=await graph.evaluate(READ_LINES,axes)
    if len(drawings)!=len(segments) or any(
            not matches(s,d,p,t) for s,d,(p,t) in zip(segments,drawings,plans)):
        raise ValueError('Complete piecewise graph verification failed')
