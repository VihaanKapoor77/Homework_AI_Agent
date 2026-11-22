"""Exact polynomial factoring and conservative MathQuill polynomial readback."""
import re
import sympy as s


def factor_question(snapshot):
    if 'Factor out GCF (Variable Only)' not in snapshot.get('question_text',''):return None
    fields=snapshot.get('fields',[])
    if len(fields)!=1 or fields[0].get('kind')!='mathquill':return None
    formulas={m.get('latex') for m in snapshot.get('math',[]) if m.get('latex')}
    if len(formulas)!=1:return None
    source=next(iter(formulas)).replace(' ','')
    source=re.sub(r'\^\{(\d+)\}',r'^\1',source)
    term=r'\d*(?:[a-z](?:\^\d{1,2})?)+'
    if len(source)>200 or not re.fullmatch(rf'[+-]?{term}(?:[+-]{term})+',source):return None
    parts=re.findall(r'[+-]?[^+-]+',source)
    if len(parts)>10:return None
    expression=s.Integer(0)
    for part in parts:
        sign=-1 if part.startswith('-') else 1
        part=part.lstrip('+-')
        coefficient=re.match(r'\d*',part)[0]
        product=s.Integer(sign*int(coefficient or '1'))
        if abs(product)>10000:return None
        for variable,power in re.findall(r'([a-z])(?:\^(\d+))?',part[len(coefficient):]):
            exponent=int(power or '1')
            if exponent>20:return None
            product*=s.Symbol(variable)**exponent
        expression+=product
    factored=s.factor(expression)
    if s.expand(factored-expression)!=0:return None
    return s.latex(factored)


READ_POLYNOMIAL_EDITOR=r'''el => {
 const root=el.querySelector('.mq-root-block');
 if(!root)return null;
 const read=e=>{
   if(e.classList.contains('mq-cursor'))return '';
   if(e.classList.contains('mq-ghost')||e.classList.contains('mq-empty'))throw Error('Incomplete entry');
   if(e.classList.contains('mq-supsub')){
     if(e.children.length!==1||!e.firstElementChild.classList.contains('mq-sup'))throw Error('Unknown script');
     const exponent=read(e.firstElementChild);
     if(!/^\d+$/.test(exponent))throw Error('Non-integer exponent');
     return '^{'+exponent+'}';
   }
   if(e.classList.contains('mq-bracket-container')){
     if(e.querySelector('.mq-ghost'))throw Error('Unmatched bracket');
     const children=[...e.children];
     if(children.length!==3||!children[0].classList.contains('mq-paren')||!children[2].classList.contains('mq-paren'))throw Error('Unknown bracket');
     return '('+read(children[1])+')';
   }
   if(e.children.length)return [...e.children].map(read).join('');
   const text=e.textContent.replace(/\u2212/g,'-').replace(/\s/g,'');
   if(!/^[a-z0-9+\-]*$/.test(text))throw Error('Unsupported symbol');
   return text;
 };
 try{return read(root);}catch{return null;}
}'''


def normalized_polynomial(value):
    value=value.replace(r'\left','').replace(r'\right','').replace(' ','')
    return re.sub(r'\^\{(\d+)\}',r'^\1',value)
