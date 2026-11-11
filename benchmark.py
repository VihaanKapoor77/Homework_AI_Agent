"""Reproducible offline symbolic-accuracy and latency benchmark (not Gemini/live site)."""
import json
import statistics
import time
from fractions import Fraction
from math_solver import calculate

cases=[]
for a in range(1,11):
    for b in range(-6,6):
        # a*x+b=c; includes rational solutions and negative answers
        c=2*b+7
        cases.append(('linear',f'{a}*x+({b})={c}',{Fraction(c-b,a)}))
for r1 in range(-6,1):
    for r2 in range(1,7):
        cases.append(('quadratic',f'x^2+({-r1-r2})*x+({r1*r2})=0',{Fraction(r1),Fraction(r2)}))
for a in range(1,9):
    for b in range(1,9):
        cases.append(('fraction',f'{a}/{b}+1/3',Fraction(a,b)+Fraction(1,3)))
for value in range(1,15):
    cases.append(('no-real-roots',f'x^2+{value}=0',set()))
cases.append(('domain-exclusion','(x^2-1)/(x-1)=0',{Fraction(-1)}))

failures=[]
durations=[]
for kind,problem,want in cases:
    t=time.perf_counter()
    try:
        result=calculate('evaluate' if kind=='fraction' else 'solve',problem)
        if kind=='fraction':
            actual=Fraction(result['exact'])
        else:
            actual={Fraction(root['exact']) for root in result['solutions']}
            if not result['complete'] or not all(r.get('verified') for r in result['solutions']):
                raise AssertionError('Incomplete/unchecked solution')
        if actual!=want:failures.append({'kind':kind,'problem':problem,'expected':str(want),'actual':str(actual)})
    except Exception as exc:failures.append({'kind':kind,'problem':problem,'error':str(exc)})
    durations.append((time.perf_counter()-t)*1000)

ordered=sorted(durations)
report={
    'scope':'local exact-math solver only; no Gemini, screenshots, or live DeltaMath tested',
    'cases':len(cases),'correct':len(cases)-len(failures),
    'accuracy_percent':round(100*(1-len(failures)/len(cases)),2),
    'median_ms':round(statistics.median(durations),3),
    'p95_ms':round(ordered[int(.95*(len(ordered)-1))],3),
    'total_seconds':round(sum(durations)/1000,3),
    'failures':failures[:20]
}
print(json.dumps(report,indent=2))
