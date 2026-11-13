"""Read rendered SVG axes and plot transformed points through normal mouse input."""
import re
import math
import asyncio
from fractions import Fraction

READ_GRAPH = r'''svg => {
 const ticks = axis => [...svg.querySelectorAll('g.'+axis+'.axis .tick')].map(t=>{
   const value=Number(t.textContent.trim()); const m=t.getScreenCTM();
   return {value,p:axis==='x'?m.e:m.f,text:t.textContent.trim()};
 }).filter(t=>t.text && Number.isFinite(t.value));
 const fit = ts => { const a=ts[0],b=ts.find(t=>t.value!==a.value);
   if(!a||!b)throw Error('Unreadable graph ticks');
   const step=(b.p-a.p)/(b.value-a.value),zero=a.p-step*a.value;
   if(!Number.isFinite(step)||Math.abs(step)<2||ts.some(t=>Math.abs(t.p-zero-step*t.value)>1))throw Error('Inconsistent graph axes');
   return {zero,step,min:Math.min(...ts.map(t=>t.value)),max:Math.max(...ts.map(t=>t.value))}; };
 const x=fit(ticks('x')),y=fit(ticks('y'));
 const point=c=>{const p=new DOMPoint(Number(c.getAttribute('cx')),Number(c.getAttribute('cy'))).matrixTransform(c.getScreenCTM());return [(p.x-x.zero)/x.step,(p.y-y.zero)/y.step];};
 const sources=[...svg.querySelectorAll('path.func')].flatMap(p=>[...p.parentElement.children].filter(c=>c.tagName.toLowerCase()==='circle' && c.hasAttribute('cx') && !c.hasAttribute('myid') && !c.closest('defs') && Number(c.getAttribute('r'))>0).map(point));
 const plotted=[...svg.querySelectorAll('circle.delta-point[aria-label]')].map(point);
 const shapes=[...svg.querySelectorAll('path.func')].filter(p=>['lightpink','lightblue'].includes(p.getAttribute('fill'))).map(p=>({color:p.getAttribute('fill'),points:[...p.parentElement.children].filter(c=>c.tagName.toLowerCase()==='circle'&&!c.hasAttribute('myid')).map(point)}));
 const reflectors=[...svg.querySelectorAll('path.func[stroke="steelblue"],line[stroke="steelblue"]')].map(p=>{
   const length=p.getTotalLength();return [0,.25,.5,.75,1].map(t=>{
     const v=p.getPointAtLength(length*t),q=new DOMPoint(v.x,v.y).matrixTransform(p.getScreenCTM());return [(q.x-x.zero)/x.step,(q.y-y.zero)/y.step];
   });});
 return {x,y,sources,shapes,reflectors,plotted,label:svg.getAttribute('aria-label'),tools:svg.querySelectorAll('[aria-label="Point plotter tool"]').length};
}'''

def transformed_points(text, sources):
    """Exact translation for rendered source vertices; unsupported tasks return None."""
    match=re.search(r'Translate the figure\s+(\d+)\s+units?\s+(left|right)\s+and\s+(\d+)\s+units?\s+(up|down)',text,re.I)
    if not match:return None
    dx=int(match[1])*(-1 if match[2].lower()=='left' else 1)
    dy=int(match[3])*(-1 if match[4].lower()=='down' else 1)
    points=[]
    for x,y in sources:
        if not all(math.isfinite(v) and abs(v-round(v))<1e-6 for v in (x,y)):
            raise ValueError('Nonintegral or unreadable source vertex')
        p=(round(x)+dx,round(y)+dy)
        if p not in points:points.append(p)
    if not 3<=len(points)<=12:raise ValueError('Could not identify all source vertices')
    return points

async def graph_plan(page,text):
    graphs=page.locator('svg.delta-graph').filter(has=page.locator('[aria-label="Point plotter tool"]'))
    if await graphs.count()!=1:return None
    data=await graphs.evaluate(READ_GRAPH)
    points=transformed_points(text,data['sources'])
    if re.search(r'Reflect the figure over the line',text,re.I):
        if len(data['reflectors'])!=1:raise ValueError('Need one rendered reflection line')
        points=reflected_points(data['sources'],data['reflectors'][0])
    if points is None:return None
    return points

def reflected_points(sources,line):
    a,b=line[0],line[-1]
    dx,dy=b[0]-a[0],b[1]-a[1]
    norm=dx*dx+dy*dy
    if norm<1e-6 or any(abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))>1e-3 for p in line):
        raise ValueError('Reflection guide is not a straight line')
    points=[]
    for x,y in sources:
        projection=((x-a[0])*dx+(y-a[1])*dy)/norm
        p=(round(2*(a[0]+projection*dx)-x,6),round(2*(a[1]+projection*dy)-y,6))
        if p not in points:points.append(p)
    if not 3<=len(points)<=12:raise ValueError('Unreadable reflected source vertices')
    return points

async def plot_points(page,points):
    graph=page.locator('svg.delta-graph').filter(has=page.locator('[aria-label="Point plotter tool"]'))
    if await graph.count()!=1:raise ValueError('No unique observed point plotter')
    await graph.scroll_into_view_if_needed()
    data=await graph.evaluate(READ_GRAPH)
    if not 1<=len(points)<=12 or len(set(map(tuple,points)))!=len(points):raise ValueError('Invalid point set')
    for x,y in points:
        if not data['x']['min']<=x<=data['x']['max'] or not data['y']['min']<=y<=data['y']['max']:
            raise ValueError('Point falls outside observed graph')
    def normalized(values):return {(round(x,6),round(y,6)) for x,y in values}
    expected=normalized(points)
    existing=normalized(data['plotted'])
    if existing-expected:raise ValueError('Graph contains unexpected points; review before changing it')
    for x,y in points:
        if (round(x,6),round(y,6)) in existing:continue
        data=await graph.evaluate(READ_GRAPH)
        await page.mouse.click(data['x']['zero']+x*data['x']['step'],data['y']['zero']+y*data['y']['step'])
        await asyncio.sleep(.15)
    await page.mouse.move(10,10)
    data=await graph.evaluate(READ_GRAPH)
    if normalized(data['plotted'])!=expected:raise ValueError('Plotted coordinates did not read back correctly')

def reflection_pairs(shapes):
    def vertices(color):
        found=[s for s in shapes if s['color']==color]
        if len(found)!=1:raise ValueError('Need one pink and one blue figure')
        return list(dict.fromkeys((round(x,6),round(y,6)) for x,y in found[0]['points']))
    source,target=vertices('lightpink'),vertices('lightblue')
    if len(source)!=len(target) or not 3<=len(source)<=12:raise ValueError('Unreadable reflection figures')
    candidates={}
    for p in source:
        for q in target:
            nx,ny=q[0]-p[0],q[1]-p[1]
            norm=nx*nx+ny*ny
            if norm<1e-8:continue
            c=(nx*(p[0]+q[0])+ny*(p[1]+q[1]))/2
            pairs=[]
            for a in source:
                t=2*(nx*a[0]+ny*a[1]-c)/norm
                b=(round(a[0]-t*nx,6),round(a[1]-t*ny,6))
                if b not in target:break
                pairs.append((a,b))
            if len(pairs)==len(source):candidates[tuple(pairs)]=pairs
    if len(candidates)!=1:raise ValueError('Reflection correspondence is ambiguous')
    return next(iter(candidates.values()))

async def reflection_slopes(page):
    data=await page.locator('svg.delta-graph').evaluate(READ_GRAPH)
    pairs=reflection_pairs(data['shapes'])
    a,b=next((a,b) for a,b in pairs if a!=b)
    dx,dy=Fraction(str(b[0]-a[0])),Fraction(str(b[1]-a[1]))
    def slope(rise,run):return str(rise/run) if run else 'undefined'
    return [slope(dy,dx),slope(-dx,dy)]

async def reflection_equation(page):
    data=await page.locator('svg.delta-graph').evaluate(READ_GRAPH)
    pairs=reflection_pairs(data['shapes'])
    a,b=next((a,b) for a,b in pairs if a!=b)
    dx,dy=Fraction(str(b[0]-a[0])),Fraction(str(b[1]-a[1]))
    mx,my=Fraction(str((a[0]+b[0])/2)),Fraction(str((a[1]+b[1])/2))
    if not dy:return 'x='+str(mx)
    m=-dx/dy
    intercept=my-m*mx
    def fmt(n):return str(n.numerator) if n.denominator==1 else r'\frac{'+str(n.numerator)+'}{'+str(n.denominator)+'}'
    term='' if not m else ('x' if m==1 else '-x' if m==-1 else fmt(m)+'x')
    constant=('+' if intercept>0 and term else '')+fmt(intercept) if intercept or not term else ''
    return 'y='+term+constant

async def guided_reflection(page):
    text=await page.locator('body').inner_text()
    connecting='Click and drag to draw lines connecting all corresponding points' in text
    midpoints='Plot the midpoints of all the dotted lines.' in text
    line='Draw a line that goes through all of the yellow midpoints.' in text
    if not connecting and not midpoints and not line:return None
    graph=page.locator('svg.delta-graph')
    if await graph.count()!=1:raise ValueError('Need one guided reflection graph')
    await graph.scroll_into_view_if_needed()
    # Axis labels are selectable SVG text; a cross-axis drag can otherwise become
    # a browser text selection instead of reaching the graph's mouse-up handler.
    await graph.evaluate("el=>{el.style.userSelect='none';for(const t of el.querySelectorAll('text'))t.style.userSelect='none';}")
    data=await graph.evaluate(READ_GRAPH)
    pairs=reflection_pairs(data['shapes'])
    if line:
        mids=list(dict.fromkeys(((a[0]+b[0])/2,(a[1]+b[1])/2) for a,b in pairs))
        if len(mids)<2:raise ValueError('Need two distinct midpoints')
        a,b=max(((a,b) for a in mids for b in mids),key=lambda pair:sum((u-v)**2 for u,v in zip(*pair)))
        await page.mouse.move(data['x']['zero']+a[0]*data['x']['step'],data['y']['zero']+a[1]*data['y']['step'])
        await page.mouse.down()
        await page.mouse.move(data['x']['zero']+b[0]*data['x']['step'],data['y']['zero']+b[1]*data['y']['step'],steps=15)
        await page.mouse.up()
        await asyncio.sleep(.5)
        return 'Drew the reflection line through the verified midpoints.'
    if midpoints:
        for a,b in pairs:
            data=await graph.evaluate(READ_GRAPH)
            x,y=(a[0]+b[0])/2,(a[1]+b[1])/2
            await page.mouse.click(data['x']['zero']+x*data['x']['step'],data['y']['zero']+y*data['y']['step'])
            await asyncio.sleep(.25)
        return 'Plotted the exact midpoints. Inspect the next guided step.'
    for a,b in pairs:
        data=await graph.evaluate(READ_GRAPH)
        def pixel(p):return (data['x']['zero']+p[0]*data['x']['step'],data['y']['zero']+p[1]*data['y']['step'])
        await page.mouse.move(*pixel(a))
        await asyncio.sleep(.15)
        await page.mouse.down()
        await asyncio.sleep(.15)
        await page.mouse.move(*pixel(b),steps=30)
        await asyncio.sleep(.15)
        await page.mouse.up()
        await asyncio.sleep(.5)
    return 'Connected corresponding vertices using a verified reflection. Inspect the next guided step.'

