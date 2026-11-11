"""Optional second opinion; no browser access or unverified answer submission."""
from __future__ import annotations
from gemini_client import generate_json

async def second_opinion(problem,failed_attempt,calculate,research,model,timeout):
    prompt=('Solve the following math problem independently. Return JSON with keys '
            '"answer", "method", "uncertainty", "equation", "calculations". '
            'Preserve exact fractions and all solutions; do not invent missing diagram values. '
            'Report uncertainty if problem lacks needed data.\n'
            f'Problem: {problem[:8000]}\nFailed prior attempt: {failed_attempt[:2000]}')
    result=await generate_json(prompt,None,model,timeout)
    if result.get('uncertainty'):
        result['status']='needs_review'
    else:result['status']='candidate'
    return result
