"""Exact two-step transformations of corresponding, rendered vertex coordinates."""
from fractions import Fraction
from math import isqrt
import re


def composition_field_values(fields,steps):
    """Map exact operations to the actual controls, including rotation dropdowns."""
    values=[value for step in steps for value in step]
    if len(fields)!=len(values):raise ValueError('Transformation field count does not match the two steps.')
    offset=0
    for position,step in enumerate(steps):
        kind=step[0]
        type_field=fields[offset]
        expected_label='select the '+('first' if position==0 else 'second')+' transformation'
        if type_field.get('label')!=expected_label:raise ValueError('Transformation controls are not in the expected order.')
        parameter=fields[offset+1]
        label=parameter.get('label','').lower()
        context=re.sub(r'\s+',' ',parameter.get('context','')).lower()
        options=parameter.get('options',[])
        if kind=='rotation' and parameter.get('kind')=='select':
            if 'about the origin' not in label+' '+context:raise ValueError('Unknown rotation center.')
            matches=[]
            for option in options:
                text=option['label'].lower().replace('counter-clockwise','counterclockwise').replace('counter clockwise','counterclockwise')
                angle=re.search(r'\b(90|180|270)\b',text)
                if not angle or 'clockwise' not in text:continue
                degrees=int(angle[1])*(1 if 'counterclockwise' in text else -1)%360
                if degrees==int(step[1])%360:matches.append(option['label'])
            if not matches:raise ValueError('No visible rotation option matches the verified angle and direction.')
            values[offset+1]=matches[0]
        elif kind=='rotation':
            if not ('counterclockwise' in label+' '+context and 'origin' in label+' '+context):
                raise ValueError('Unrecognized numeric rotation direction or center.')
        elif kind=='reflection':
            if step[1] not in {o['label'] for o in options}:raise ValueError('Verified reflection axis is not available.')
        elif kind=='translation':
            distance=fields[offset+2]
            if step[1] not in {o['label'] for o in options} or not re.search(r'unit',distance.get('label','')+' '+distance.get('context',''),re.I):
                raise ValueError('Unrecognized translation direction or distance controls.')
        elif kind=='dilation':
            if not ('origin' in context and 'scale factor' in context):raise ValueError('Unrecognized dilation center or scale factor.')
        else:raise ValueError('Unsupported transformation type.')
        offset+=len(step)
    return values


def apply_step(point,step):
    x,y=map(Fraction,point)
    kind=step[0]
    if kind=='rotation':
        return {'90':(-y,x),'180':(-x,-y),'270':(y,-x)}[step[1]]
    if kind=='reflection':return (x,-y) if step[1]=='x-axis' else (-x,y)
    if kind=='dilation':return x*Fraction(step[1]),y*Fraction(step[1])
    direction,amount=step[1],Fraction(step[2])
    dx,dy={'up':(0,amount),'down':(0,-amount),'left':(-amount,0),'right':(amount,0)}[direction]
    return x+dx,y+dy


def solve_composition(source,target):
    if len(source)!=len(target) or len(set(source))<3:return None
    # Reject collinear/degenerate inputs: they cannot determine a plane mapping.
    ax,ay=source[0]
    if not any((x-ax)*(v-ay)!=(y-ay)*(u-ax) for x,y in source[1:] for u,v in source[1:]):return None
    linear=[['rotation',d] for d in ('90','180','270')]+[['reflection',a] for a in ('x-axis','y-axis')]
    a,b=source[:2];c,d=target[:2]
    norm=(b[0]-a[0])**2+(b[1]-a[1])**2
    if not norm:return None
    ratio=Fraction((d[0]-c[0])**2+(d[1]-c[1])**2,norm)
    n,q=isqrt(ratio.numerator),isqrt(ratio.denominator)
    if n*n==ratio.numerator and q*q==ratio.denominator and n and n!=q:
        linear.append(['dilation',str(Fraction(n,q))])
        linear.extend([['dilation','2'],['dilation',str(Fraction(n,2*q))]])
    translations=[]
    for step in [None]+linear:
        p=apply_step(source[0],step) if step else source[0]
        dx,dy=target[0][0]-p[0],target[0][1]-p[1]
        for delta,positive,negative in ((dx,'right','left'),(dy,'up','down')):
            if delta:
                candidate=['translation',positive if delta>0 else negative,str(abs(delta))]
                if candidate not in translations:translations.append(candidate)
                half=['translation',candidate[1],str(Fraction(abs(delta),2))]
                if half not in translations:translations.append(half)
    operations=linear+translations
    for first in operations:
        for second in operations:
            if all(apply_step(apply_step(a,first),second)==tuple(b) for a,b in zip(source,target)):
                return [first,second]
    return None
