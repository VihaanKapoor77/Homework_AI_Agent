"""Opt-in real-model checks; no website interactions or submissions."""
import asyncio
import os
from dotenv import load_dotenv
from subject_solver import SubjectSolver

CASES=[
    ('Spanish: Yo ___ estudiante. Choices: soy / estoy. Return only the chosen word as answer.','soy'),
    ('Spanish: Yo ___ cansado hoy. Choices: soy / estoy. Return only the chosen word as answer.','estoy'),
    ('Spanish: La fiesta ___ en mi casa. Choices: es / está. Return only the chosen word as answer.','es'),
    ('Spanish: El libro ___ en la mesa. Choices: es / está. Return only the chosen word as answer.','está'),
    ('English: What is the standard irregular plural of goose? Return only the word as answer.','geese'),
    ('Science: Which gas do plants take in for photosynthesis? Choices: carbon dioxide / oxygen. Return only the choice as answer.','carbon dioxide'),
    ('Social studies: Which US federal branch makes laws? Choices: legislative / executive / judicial. Return only the choice as answer.','legislative'),
]

async def main():
    load_dotenv()
    solver=SubjectSolver(os.getenv('MODEL','gemini-3.5-flash-lite'))
    passed=0
    for prompt,expected in CASES:
        answer,check=await solver.solve(prompt)
        ok=not answer.uncertainty and not answer.needs_source and check and check.correct and check.target_matches and answer.answer.strip().casefold()==expected.casefold()
        passed+=bool(ok)
        print(('PASS' if ok else 'FAIL')+': '+prompt+' -> '+answer.answer,flush=True)
    print(f'{passed}/{len(CASES)} live model examples passed.',flush=True)
    if passed!=len(CASES):raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
