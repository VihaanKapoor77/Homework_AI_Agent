"""Local retrieval memory. Examples are original; no DeltaMath answer-bank dump."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

EXAMPLES = [
 ('linear equation','Solve 3*x+5=20','Subtract 5, then divide by 3.','solve','3*x+5=20'),
 ('quadratic equation','Solve x^2-5*x+6=0','Factor and set each factor equal to zero.','solve','x^2-5*x+6=0'),
 ('rational equation domain','Solve (x^2-1)/(x-1)=0','Keep denominator restrictions; x=1 is excluded.','solve','(x^2-1)/(x-1)=0'),
 ('radical equation','Solve sqrt(x+1)=3','Square both sides, then check the original equation.','solve','sqrt(x+1)=3'),
 ('absolute value equation','Solve abs(x-2)=5','Consider both signs and verify each root.','solve','abs(x-2)=5'),
 ('logarithm base ten','Evaluate log10(1000)','Find the power of ten equal to 1000.','evaluate','log10(1000)'),
 ('fraction arithmetic','Evaluate 1/3+1/6','Use a common denominator; preserve exact fractions.','evaluate','1/3+1/6'),
 ('polynomial factoring','Factor x^2-9','Use the difference of two squares.','factor','x^2-9'),
 ('polynomial expansion','Expand (x+2)^2','Multiply both copies of the binomial.','expand','(x+2)^2'),
 ('perpendicular bisector geometry','Find the perpendicular bisector for (0,0) and (4,2)','Use the midpoint and perpendicular direction.','perpendicular_bisector','0,0,4,2'),
 ('distance coordinate geometry','Distance between (1,2) and (4,6)','Use sqrt((x2-x1)^2+(y2-y1)^2).','evaluate','sqrt((4-1)^2+(6-2)^2)'),
 ('right triangle pythagorean theorem','Hypotenuse with legs 6 and 8','Use sqrt(a^2+b^2).','evaluate','sqrt(6^2+8^2)'),
 ('trigonometry degrees','Evaluate sin(30 degrees)','Convert degrees to radians by multiplying by pi/180.','evaluate','sin(30*pi/180)'),
 ('derivative calculus','Differentiate x^3+2*x','Apply the power rule to each term.','differentiate','x^3+2*x'),
 ('integral calculus','Integrate 2*x','Apply the power rule; include +C in the final answer.','integrate','2*x'),
]

def key(problem):
    # Keep case, signs, numbers and punctuation. E and e are NOT interchangeable.
    return hashlib.sha256(re.sub(r'\s+', ' ', problem).strip().encode()).hexdigest()

def tokens(text):
    return set(re.findall(r'[a-z]+|\d+', text.lower()))

class MathMemory:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('MATH_MEMORY_PATH') or Path.home()/'.assignment-agent'/'math_memory.sqlite3').expanduser()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS examples (
            id TEXT PRIMARY KEY, problem TEXT NOT NULL, topic TEXT NOT NULL,
            method TEXT NOT NULL, operation TEXT NOT NULL, expression TEXT NOT NULL,
            variable TEXT NOT NULL, result TEXT NOT NULL,
            source TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS feedback_lessons (
            id TEXT PRIMARY KEY, problem TEXT NOT NULL, topic TEXT NOT NULL,
            attempted TEXT NOT NULL, feedback TEXT NOT NULL,
            source TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def save(self, problem, topic, method, operation, expression, variable, result, source='observed_problem'):
        for label, value, maximum in [('problem',problem,12000),('topic',topic,200),('method',method,4000)]:
            if not isinstance(value,str) or not value.strip() or len(value)>maximum:
                raise ValueError(f'{label} must be nonempty text up to {maximum} characters')
        if 'error' in result or result.get('complete') is False:
            raise ValueError('Unresolved or failed calculations cannot be saved as solved examples')
        identity=key(problem)
        # Variants are retained; conflicting formulations must not silently overwrite one another.
        record_id=hashlib.sha256(json.dumps([identity,operation,expression,variable],ensure_ascii=False).encode()).hexdigest()
        with self.connect() as conn:
            conn.execute('''INSERT INTO examples(id,problem,topic,method,operation,expression,variable,result,source)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET result=excluded.result,
                method=excluded.method,updated_at=CURRENT_TIMESTAMP''',
                (record_id,problem,topic,method,operation,expression,variable,json.dumps(result),source))
        return {'saved':True,'id':record_id,'verification':'symbolic calculation only; interpretation and website acceptance not verified'}

    def save_feedback(self, problem, topic, attempted, feedback, source='website_feedback'):
        """Persist an explicit incorrect-answer lesson without treating it as a solution."""
        values = [('problem', problem, 12000), ('topic', topic, 200),
                  ('attempted', attempted, 4000), ('feedback', feedback, 12000)]
        for label, value, maximum in values:
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f'{label} must be nonempty text up to {maximum} characters')
        record_id = hashlib.sha256(json.dumps([key(problem), attempted, feedback], ensure_ascii=False).encode()).hexdigest()
        with self.connect() as conn:
            conn.execute('''INSERT INTO feedback_lessons(id,problem,topic,attempted,feedback,source)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET feedback=excluded.feedback,
                attempted=excluded.attempted,updated_at=CURRENT_TIMESTAMP''',
                (record_id, problem, topic, attempted, feedback, source))
        return {'saved': True, 'id': record_id, 'verification': 'feedback lesson only; not a verified answer'}

    def seed(self):
        from math_solver import calculate
        with self.connect() as conn:
            existing={r[0] for r in conn.execute("SELECT problem FROM examples WHERE source='original_example'")}
        for topic,problem,method,operation,expression in EXAMPLES:
            if problem not in existing:
                self.save(problem,topic,method,operation,expression,'x',calculate(operation,expression),'original_example')

    def search(self, problem, topic='', limit=5):
        if not isinstance(problem,str) or not problem.strip() or len(problem)>12000:
            raise ValueError('Problem must contain 1-12000 characters')
        self.seed()
        query=tokens(problem+' '+topic)
        matches=[]
        with self.connect() as conn:
            rows=conn.execute('SELECT * FROM examples').fetchall()
        for row in rows:
            item=dict(row)
            exact=key(item['problem'])==key(problem)
            candidate=tokens(item['problem']+' '+item['topic'])
            overlap=len(query & candidate)
            score=overlap / max(1,len(query | candidate))
            if not exact and (overlap < 2 or score < .08): continue
            item['result']=json.loads(item['result'])
            item.update(match='exact_text' if exact else 'similar_method',score=round(score,3),
                        verification='symbolic calculation only; not a website-verified answer',
                        reuse='Recheck problem, diagram, units and rounding; recompute with current numbers.')
            matches.append(item)
        matches.sort(key=lambda r:(r['match']=='exact_text',r['score']),reverse=True)
        lessons=[]
        with self.connect() as conn:
            rows=conn.execute('SELECT * FROM feedback_lessons').fetchall()
        for row in rows:
            item=dict(row)
            candidate=tokens(item['problem']+' '+item['topic']+' '+item['feedback'])
            overlap=len(query & candidate)
            score=overlap / max(1,len(query | candidate))
            if overlap >= 2 and score >= .08:
                item['match']='learned_feedback'
                item['score']=round(score,3)
                lessons.append(item)
        lessons.sort(key=lambda r:r['score'], reverse=True)
        return {'matches':matches[:max(1,min(limit,10))], 'feedback_lessons':lessons[:max(1,min(limit,10))], 'bank':'local examples and previously saved calculations; not the DeltaMath question bank',
                'next_step':'Use a matching method and recompute. If none fits, search public explanations using a generic topic, then translate to solver syntax. Never copy a nearby answer.'}
