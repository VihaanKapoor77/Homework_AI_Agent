"""Strict, local point transformations for rapid coordinate-choice questions."""
import re
from fractions import Fraction


def plain_math(text):
    text=text.replace(r'^{\circ}',' degrees').replace(r'\circ',' degrees')
    text=text.replace('\u2212','-').replace(r'\left','').replace(r'\right','')
    text=re.sub(r'left parenthesis\s*,?', '(', text, flags=re.I)
    text=re.sub(r',?\s*right parenthesis', ')', text, flags=re.I)
    text=re.sub(r'\bminus\s*,?\s*', '-', text, flags=re.I)
    text=re.sub(r'\bcomma\b', ',', text, flags=re.I)
    text=re.sub(r'\bequals\b', '=', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()


NUMBER=r'-?\d+(?:\.\d+)?'
PAIR=rf'\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)'


def coordinate(text):
    match=re.fullmatch(PAIR,plain_math(text))
    return tuple(map(Fraction,match.groups())) if match else None


def solve_point(text):
    text=plain_math(text)
    match=re.fullmatch(r'Reflection (?:over|across) (?:the )?(?:line )?'
        rf'(y\s*=\s*-?\s*x|[xy][ -]axis) of (?:the )?point\s*{PAIR}[.?!]?',text,re.I)
    if match:
        axis=re.sub(r'\s+','',match[1].lower()).replace('xaxis','x-axis').replace('yaxis','y-axis')
        x,y=map(Fraction,match.groups()[1:])
        return {'y=x':(y,x),'y=-x':(-y,-x),'x-axis':(x,-y),'y-axis':(-x,y)}[axis]
    match=re.fullmatch(r'Rotation (?:of )?(90|180|270)\s*(?:°|degrees?)\s*'
        r'(counter[ -]?clockwise|clockwise) (?:about|around) (?:the )?origin '
        rf'of (?:the )?point\s*{PAIR}[.?!]?',text,re.I)
    if match:
        angle=int(match[1])*(1 if match[2].lower().startswith('counter') else -1)%360
        x,y=map(Fraction,match.groups()[2:])
        return {90:(-y,x),180:(-x,-y),270:(y,-x)}[angle]
    return None


def point_choice(snapshot):
    answer=solve_point(snapshot.get('question_text',''))
    if answer is None:return None
    fields=snapshot.get('fields',[])
    choices=fields if fields and all(f.get('kind')=='radio_option' for f in fields) else snapshot.get('buttons',[]) if not fields else []
    matches=[c for c in choices if not c.get('disabled') and coordinate(c.get('label',c.get('text','')))==answer]
    return matches[0] if len(matches)==1 else None
