"""Fast, bounded, exact local math worker. Only approved AST forms are evaluated.
Run standalone with JSON stdin or import calculate(). Never eval Python source.
"""
from __future__ import annotations
import ast
import json
import re
import sys
import sympy as s

SYMBOLS = {k:s.Symbol(k, real=True) for k in ('x','y','z','t','a','b','c','m','n')}
CONSTANTS = {'pi':s.pi,'E':s.E}
FUNCS = {
 'sqrt':s.sqrt, 'abs':s.Abs, 'sin':s.sin, 'cos':s.cos, 'tan':s.tan,
 'asin':s.asin, 'acos':s.acos, 'atan':s.atan, 'ln':s.log,
 'log10':lambda x:s.log(x,10), 'exp':s.exp,
}
MAX_LENGTH=1500

def parse_expression(text: str):
    if not isinstance(text,str) or not text.strip() or len(text)>MAX_LENGTH:
        raise ValueError('Unsupported syntax: expression must have 1-1500 characters')
    if '=' in text:
        raise ValueError('Unsupported syntax: use calculate(operation="solve") for an equation')
    # Normalize presentation only; the AST allowlist remains the evaluator.
    text=text.strip().replace('−','-').replace('×','*').replace('·','*')
    text=text.replace('²','^2').replace('³','^3')
    text=re.sub(r'\^\{([+-]?\d+)\}',r'^\1',text)
    # Numeric coefficients such as 3x, including whitespace, are multiplication.
    text=re.sub(r'(?<=\d)\s*([xyztabcmn])(?![A-Za-z0-9_])',r'*\1',text)
    try: root=ast.parse(text.replace('^','**'), mode='eval')
    except SyntaxError as exc: raise ValueError('Unsupported syntax: invalid expression') from exc
    def walk(node,depth=0):
        if depth>35: raise ValueError('Unsupported syntax: expression nested too deeply')
        if isinstance(node,ast.Expression): return walk(node.body,depth+1)
        if isinstance(node,ast.Constant):
            if isinstance(node.value,bool) or not isinstance(node.value,(float,int)):
                raise ValueError('Unsupported syntax: only real numeric constants')
            if abs(node.value)>1_000_000_000: raise ValueError('Unsupported syntax: numeric literal too large')
            return s.Rational(str(node.value))
        if isinstance(node,ast.Name):
            if node.id in SYMBOLS:return SYMBOLS[node.id]
            if node.id in CONSTANTS:return CONSTANTS[node.id]
            raise ValueError(f'Unsupported syntax: unknown variable {node.id!r}')
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            v=walk(node.operand,depth+1)
            return v if isinstance(node.op,ast.UAdd) else -v
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow)):
            left=walk(node.left,depth+1)
            right=walk(node.right,depth+1)
            if isinstance(node.op,ast.Pow):
                if not right.is_number or not right.is_finite or abs(float(right.evalf(10)))>100:
                    raise ValueError('Unsupported syntax: exponent must be numeric and small')
                return left**right
            if isinstance(node.op,ast.Div):
                if right==0: raise ValueError('Division by zero')
                return left/right
            if isinstance(node.op,ast.Add):return left+right
            if isinstance(node.op,ast.Sub):return left-right
            return left*right
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords and len(node.args)==1 and node.func.id in FUNCS:
            return FUNCS[node.func.id](walk(node.args[0],depth+1))
        raise ValueError('Unsupported syntax: only arithmetic and approved math functions')
    result=walk(root)
    if result.has(s.zoo,s.oo,-s.oo,s.nan) or result in (s.zoo,s.oo,-s.oo,s.nan):
        raise ValueError('Undefined expression')
    return result

def _num(v):
    return str(s.simplify(v))

def _solved_equation(expression,variable):
    if expression.count('=')!=1:
        raise ValueError('Solve requires one equation using =')
    left,right=map(parse_expression,expression.split('='))
    x=SYMBOLS.get(variable)
    if x is None:raise ValueError('Unsupported variable: choose x, y, z, t, a, b, c, m or n')
    expr=left-right
    if (left.free_symbols | right.free_symbols)-{x}:
        raise ValueError('Equation contains variables other than the requested variable')
    # Never lose denominator restrictions when simplifying rational equations.
    domain=s.S.Reals
    for side in (left,right):
        den=s.denom(side)
        if den!=1:
            domain=domain-s.solveset(den,x,domain=s.S.Reals)
    roots=s.solveset(expr,x,domain=domain)
    if not isinstance(roots,s.FiniteSet) and roots!=s.EmptySet:
        return {'operation':'solve','expression':expression,'result':str(roots),'solutions':[], 'complete':False}
    found=[]
    for value in sorted(list(roots),key=s.default_sort_key):
        try:
            checked=(s.simplify(left.subs(x,value)-right.subs(x,value))==0)
        except Exception:
            checked=False
        if checked:
            found.append({'exact':_num(value),'latex':s.latex(value),'verified':True})
    # Complete means the symbolic solver returned a finite set, not website acceptance.
    return {'operation':'solve','expression':expression,'result':'{'+', '.join(r['exact'] for r in found)+'}' if found else 'EmptySet','solutions':found,'complete':True,'source':'sympy'}

def _bisector(expression):
    coords=[parse_expression(v.strip()) for v in expression.split(',')]
    if len(coords)!=4 or any(not c.is_real or c.free_symbols for c in coords):
        raise ValueError('Perpendicular bisector expects four real numeric coordinates')
    x1,y1,x2,y2=coords
    dx=x2-x1;dy=y2-y1
    if dx==dy==0:raise ValueError('Coincident points have no unique perpendicular bisector')
    mx=s.simplify((x1+x2)/2);my=s.simplify((y1+y2)/2)
    if dy==0:
        return {'operation':'perpendicular_bisector','lhs':'x','rhs':_num(mx),'midpoint':[_num(mx),_num(my)],'latex':f'x={s.latex(mx)}','complete':True}
    if dx==0:
        return {'operation':'perpendicular_bisector','lhs':'y','rhs':_num(my),'midpoint':[_num(mx),_num(my)],'latex':f'y={s.latex(my)}','complete':True}
    slope=-dx/dy
    rhs=s.expand(slope*(SYMBOLS['x']-mx)+my)
    return {'operation':'perpendicular_bisector','lhs':'y','rhs':str(rhs),'midpoint':[_num(mx),_num(my)],'latex':f'y={s.latex(rhs)}','complete':True}

def calculate(operation:str,expression:str,variable:str='x'):
    op=operation.lower().strip()
    if op=='auto':op='solve' if '=' in expression else 'simplify'
    if op=='perpendicular_bisector': return _bisector(expression)
    if op=='solve':return _solved_equation(expression,variable)
    expr=parse_expression(expression)
    x=SYMBOLS.get(variable)
    if x is None:raise ValueError('Unsupported variable')
    if op=='evaluate':
        if expr.free_symbols:raise ValueError('Evaluation requires an expression with no variables')
        val=s.simplify(expr)
    elif op=='simplify':val=s.simplify(expr)
    elif op=='factor':val=s.factor(expr)
    elif op=='expand':val=s.expand(expr)
    elif op=='differentiate':val=s.diff(expr,x)
    elif op=='integrate':val=s.integrate(expr,x)
    elif op=='directed_segment':
        raise ValueError('Unsupported syntax: use a coordinate geometry expression')
    else:raise ValueError('Unsupported operation: '+operation)
    return {'operation':op,'expression':expression,'result':str(val),'exact':_num(val),'latex':s.latex(val),'complete':True,'source':'sympy'}

if __name__=='__main__':
    try:
        params=json.loads(sys.stdin.read(20000))
        print(json.dumps(calculate(params['operation'],params['expression'],params.get('variable','x'))))
    except (ValueError,TypeError,KeyError,SyntaxError,NotImplementedError) as exc:
        print(json.dumps({'error':str(exc),'complete':False}))
