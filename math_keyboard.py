"""MathQuill keyboard fallback. Never type into an editor that failed to clear."""
from __future__ import annotations
import asyncio
import re

READ = r'''el => {
 const MQ=window.MathQuill&&typeof window.MathQuill.getInterface==='function'?window.MathQuill.getInterface(2):null;
 const editor=typeof MQ==='function'?MQ(el):null;
 return editor&&typeof editor.latex==='function'?editor.latex():null;
}'''

async def enter_keyboard(field,latex,timeout_ms=120000):
    if not isinstance(latex,str) or not latex or len(latex)>2000:
        raise ValueError('Answer cannot be empty or too long')
    await field.click(timeout=timeout_ms)
    await field.press('ControlOrMeta+A',timeout=timeout_ms)
    await field.press('Backspace',timeout=timeout_ms)
    # Some custom math editors ignore Ctrl+A. Never append to an uncleared field.
    existing=await field.evaluate(READ)
    if existing is None:
        existing=await field.evaluate('el => ((el.querySelector(".mq-root-block") || el).textContent || "").trim()')
    if existing and existing.replace('\u200b','').replace('\ufeff','').strip():
        raise ValueError('Math editor did not clear; refusing to append duplicate digits')
    # Common structured LaTeX; use MathQuill keystrokes rather than raw LaTeX into a hidden textarea.
    # Complex forms requiring geometry templates are intentionally left for visual/manual entry.
    def tokens(value):
        i=0
        while i<len(value):
            if value.startswith(r'\frac{',i):
                i+=6
                end=value.find('}',i)
                if end<0 or value[end+1:end+2]!='{':raise ValueError('Malformed fraction')
                numerator=value[i:end];den_end=value.find('}',end+2)
                if den_end<0 or any(ch in numerator+value[end+2:den_end] for ch in '{}\\'):
                    raise ValueError('Complex fraction needs MathQuill API')
                yield ('fraction',numerator,value[end+2:den_end]);i=den_end+1
            elif value.startswith(r'\pi',i):
                yield ('write','pi');i+=3
            elif value[i]=='\\':
                raise ValueError('Unsupported LaTeX in keyboard fallback; use MathQuill API')
            else:
                yield ('write',value[i]);i+=1
    for token in tokens(latex):
        if token[0]=='fraction':
            await field.press('/',timeout=timeout_ms)
            await field.press_sequentially(token[1],delay=5,timeout=timeout_ms)
            await field.press('ArrowDown',timeout=timeout_ms)
            await field.press_sequentially(token[2],delay=5,timeout=timeout_ms)
            await field.press('ArrowRight',timeout=timeout_ms)
        else:
            await field.press_sequentially(token[1],delay=5,timeout=timeout_ms)
    return {'entered':True,'method':'keyboard','verify_visually':True}
