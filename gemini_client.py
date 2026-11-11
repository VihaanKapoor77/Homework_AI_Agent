"""Small async multimodal Gemini client, no LangChain/Browser-Use dependency."""
from __future__ import annotations
import asyncio
import base64
import json
import os
import re
import httpx
from gemini_budget import reserve,REPORT

class ModelError(RuntimeError):pass

def _json(text):
    text=text.strip()
    text=re.sub(r'^```(?:json)?\s*|\s*```$', '',text,flags=re.I)
    try:return json.loads(text)
    except json.JSONDecodeError:
        block=re.search(r'\{[\s\S]*\}',text)
        if block:return json.loads(block.group())
        raise ModelError('Model returned no readable JSON plan; inspect its output')

async def generate_json(prompt:str,image:bytes|None=None,model:str|None=None,timeout:float=90):
    key=os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if not key:raise ModelError('Set GOOGLE_API_KEY in .env; no credentials were supplied')
    model=model or os.getenv('MODEL','gemini-3.5-flash-lite')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',model):raise ModelError('Invalid Gemini model ID')
    parts=[{'text':prompt}]
    if image is not None:
        parts.append({'inline_data':{'mime_type':'image/png','data':base64.b64encode(image).decode()}})
    payload={'contents':[{'role':'user','parts':parts}],
      'generationConfig':{'temperature':0,'responseMimeType':'application/json'}}
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(3):
            await reserve()
            try:r=await client.post(url,headers={'x-goog-api-key':key},json=payload)
            except (httpx.TimeoutException,httpx.NetworkError) as exc:
                if attempt==2:raise ModelError(f'Gemini network error: {exc}') from exc
                await asyncio.sleep(2+attempt*3);continue
            if r.status_code in (500,502,503,504):
                if attempt==2:
                    raise ModelError('Gemini temporarily unavailable after 3 attempts. No answer was submitted; retry when service recovers.')
                REPORT(f'Gemini temporarily unavailable ({r.status_code}); retrying in {2+attempt*3}s.')
                await asyncio.sleep(2+attempt*3)
                continue
            if r.status_code==429:
                if attempt==2:raise ModelError('Gemini quota/rate limit exhausted (429). Check your plan or retry later.')
                delay=float(r.headers.get('retry-after',0) or 0)
                for info in (r.json().get('error',{}).get('details',[]) if r.headers.get('content-type','').startswith('application/json') else []):
                    value=info.get('retryDelay','') if isinstance(info,dict) else ''
                    if isinstance(value,str) and value.endswith('s'):
                        try:delay=max(delay,float(value[:-1]))
                        except ValueError:pass
                delay=max(5,min(65,delay or 15))
                await asyncio.sleep(delay)
                continue
            if r.status_code>=400:
                raise ModelError(f'Gemini HTTP {r.status_code}: {r.text[:350]}')
            data=r.json()
            candidates=data.get('candidates') or []
            if not candidates:raise ModelError(f'Gemini returned no candidates: {str(data)[:250]}')
            outputs=candidates[0].get('content',{}).get('parts',[])
            texts=[p.get('text','') for p in outputs if 'text' in p]
            if not texts:raise ModelError('Gemini did not return text. It may have declined this request.')
            return _json(''.join(texts))
    raise ModelError('Gemini request unsuccessful')
