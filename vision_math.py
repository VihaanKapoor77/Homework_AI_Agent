"""Grounded screenshot-to-math interpretation; cache pixels and keep uncertainty explicit."""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
from typing import Literal
from pydantic import BaseModel,Field,model_validator
from gemini_client import generate_json

class VisualCalculation(BaseModel):
    operation:str='auto'
    expression:str
    variable:str='x'

class VisualResult(BaseModel):
    status:Literal['candidate','needs_review','unclear']='candidate'
    question:str=''
    diagram_observations:list[str]=Field(default_factory=list)
    method:str=''
    answer:str=''
    answers:list[str]=Field(default_factory=list)
    equation:str=''
    uncertainty:str=''
    observed_entry:str=''
    entry_comparison:Literal['match','mismatch','unknown']='unknown'
    calculations:list[VisualCalculation]=Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def normalize_optional_nulls(cls, data):
        if not isinstance(data,dict):
            return data
        cleaned=data.copy()
        if isinstance(cleaned.get('uncertainty'),bool):
            cleaned['uncertainty']='Model reported uncertainty without an explanation.' if cleaned['uncertainty'] else ''
        defaults={
            'status':'needs_review', 'question':'', 'diagram_observations':[],
            'method':'', 'answer':'', 'answers':[], 'equation':'',
            'uncertainty':'', 'observed_entry':'',
            'entry_comparison':'unknown', 'calculations':[]
        }
        for name, default in defaults.items():
            if name in cleaned and cleaned[name] is None:
                cleaned[name]=default.copy() if isinstance(default,list) else default
        return cleaned

class VisionMath:
    def __init__(self,model='gemini-3.5-flash-lite',timeout=90):
        self.model=model
        self.timeout=timeout
        self.cache={}

    async def ask(self,pixels:bytes,prompt:str)->VisualResult:
        schema='''Return only JSON: {status:"candidate|needs_review",question,diagram_observations:[str],method,answer,answers:[str],equation,uncertainty,observed_entry,entry_comparison:"match|mismatch|unknown",calculations:[{operation,expression,variable}]}. Only include math exactly visible in screenshot, no invented labels. Preserve all signs, fractions and needed roots. If answer is unclear set needs_review and explain. Use mathematical reasoning, not guesses. For verify_entry compare actual screenshot input with intended LaTeX strictly, inspect grouping of fractions/exponents. Never claim website accepted from entry alone.'''
        payload=await generate_json(schema+'\n'+prompt,pixels,self.model,self.timeout)
        return VisualResult.model_validate(payload)

    async def capture(self,page,selector='auto'):
        if selector=='auto':
            # Worked examples may be in an overlay mounted outside <main>.
            try:
                has_dialog=await page.evaluate('''() => !!document.querySelector('[role="dialog"],dialog[open]')''')
            except (AttributeError,TypeError):
                has_dialog=False
            if has_dialog:
                for modal in ('[role="dialog"]','dialog[open]'):
                    target=page.locator(modal)
                    if await target.count()==1:
                        return await target.screenshot(timeout=int(self.timeout*1000)),{'scope':modal}
            for sel in ('main','[role="main"]'):
                locator=page.locator(sel)
                if await locator.count()==1:
                    shot=await locator.screenshot(timeout=int(self.timeout*1000))
                    return shot,{'scope':sel}
            return await page.screenshot(timeout=int(self.timeout*1000)),{'scope':'viewport'}
        if not selector or len(selector)>200:
            raise ValueError('Invalid screenshot scope')
        locator=page.locator(selector)
        if await locator.count()!=1:
            raise ValueError('Screenshot selector must match exactly one visible element')
        return await locator.screenshot(timeout=int(self.timeout*1000)),{'scope':selector}

    async def solve(self,page,request='Solve the visible math problem.',selector='auto',mode='solve',expected_latex='',calculate=None):
        if mode not in ('solve','verify_entry'):
            raise ValueError('Unknown visual task mode')
        if mode=='verify_entry' and not expected_latex:
            raise ValueError('Entry verification requires the expected answer')
        start_url=page.url
        pixels,scope=await self.capture(page,selector)
        prompt=json.dumps({'mode':mode,'request':request,'expected_latex':expected_latex},ensure_ascii=False)
        cache_id=hashlib.sha256(pixels+prompt.encode()+start_url.encode()).hexdigest()
        if cache_id in self.cache:
            return {**self.cache[cache_id],'cache_hit':True}
        response=await self.ask(pixels,prompt)
        if page.url != start_url:
            raise ValueError('Page navigated during screenshot interpretation')
        result=response.model_dump()
        result.update(capture=scope,website_accepted=False,cache_hit=False)
        if response.uncertainty or response.status=='unclear':
            result['status']='needs_review'
        if mode=='verify_entry' and response.entry_comparison!='match':
            result['status']='needs_review'
        if calculate:
            verified=[]
            for task in response.calculations[:6]:
                raw=await calculate(task.operation,task.expression,task.variable)
                try:parsed=json.loads(raw) if isinstance(raw,str) else raw
                except (ValueError,TypeError):parsed={'error':str(raw)}
                verified.append(parsed)
                if parsed.get('error') or parsed.get('complete') is False:
                    result['status']='needs_review'
            result['verified_calculations']=verified
        if not response.answer and not response.answers and mode=='solve':
            result['status']='needs_review'
        self.cache[cache_id]=result
        if len(self.cache)>60:
            self.cache.pop(next(iter(self.cache)))
        return result
