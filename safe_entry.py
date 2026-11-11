"""Fail-closed Playwright entry on a single discovered user-visible target."""
from __future__ import annotations
import asyncio

async def bounded_action(operation, emit=lambda x:None, budget=20):
    try:
        return await asyncio.wait_for(operation(),timeout=budget)
    except asyncio.TimeoutError:
        result='[ENTRY_TIMEOUT] Browser action did not finish; inspect the page before retrying.'
        emit(result)
        return result
    except Exception as exc:
        result=f'[ENTRY_ERROR] {type(exc).__name__}: {str(exc)[:350]}'
        emit(result)
        return result

INFO = r'''el => ({tag:el.tagName.toLowerCase(),type:(el.getAttribute('type')||'').toLowerCase(),
    math:!!(el.matches('.mq-editable-field')||el.closest('.mq-editable-field')),
    editable:el.isContentEditable,disabled:!!el.disabled,readonly:!!el.readOnly,
    visible:!!el.getClientRects().length})'''
VALUE = r'''el => 'value' in el ? el.value : el.innerText'''

async def fill_known_field(browser,selector,value,emit=lambda x:None,budget=20):
    async def run():
        async with browser.lock:
            page=await browser.page()
            locator=page.locator(selector)
            if await locator.count()!=1:
                return '[STALE_FIELD] Expected exactly one visible answer field.'
            props=await locator.evaluate(INFO)
            if props.get('math'):
                return '[MATH_EDITOR] Use the dedicated math editor, not ordinary fill.'
            if not props.get('visible',True) or props.get('disabled') or props.get('readonly'):
                return '[FIELD_NOT_READY] Input is hidden, disabled, or read-only.'
            if props.get('tag','').lower() not in ('input','textarea') and not props.get('editable'):
                return '[NOT_TEXT_FIELD] Target is not an editable text field.'
            if props.get('tag')=='input' and props.get('type') in ('password','file','hidden','submit','button','radio','checkbox'):
                return '[NOT_TEXT_FIELD] Cannot fill that kind of input.'
            await locator.fill(value,timeout=min(120000,int(budget*1000)))
            actual=await locator.evaluate(VALUE)
            if actual!=value:
                return '[ENTRY_MISMATCH] Field did not retain the entered value.'
            return 'Entered text with matching readback; not submitted.'
    return await bounded_action(run,emit,budget)

async def act_on_target(browser,selector,text=None,emit=lambda x:None,budget=20):
    async def run():
        async with browser.lock:
            page=await browser.page()
            target=page.locator(selector)
            if await target.count()!=1:
                return '[STALE_TARGET] Target is missing or ambiguous.'
            if text is None:
                await target.click(timeout=int(budget*1000))
                return 'Clicked target; website outcome not yet confirmed.'
            info=await target.evaluate(INFO)
            if info.get('math'):
                return '[MATH_EDITOR] Use the dedicated math editor.'
            if info.get('disabled') or info.get('readonly'):
                return '[FIELD_NOT_READY] Target is not editable.'
            await target.press_sequentially(text,delay=15,timeout=int(budget*1000))
            return 'Typed text; inspect entry and feedback.'
    return await bounded_action(run,emit,budget)
