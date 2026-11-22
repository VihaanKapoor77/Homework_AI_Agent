"""Drive the observed DeltaMath timed UI using exact math and visible score changes."""
import asyncio
import hashlib
import re
import time
from point_transform import coordinate, solve_point
from playwright.async_api import Error as PlaywrightError

READ_TIMED=r'''() => {
  const root=document.querySelector('main');
  if(!root || !root.innerText.includes('Timed Problem')) return null;
  const visible=e=>!!e.getClientRects().length;
  const clean=e=>{
    const c=e.cloneNode(true);
    c.querySelectorAll('.sr-only').forEach(n=>n.remove());
    c.querySelectorAll('.katex').forEach(n=>{
      const a=n.querySelector('annotation[encoding="application/x-tex"]');
      if(a)n.replaceWith(document.createTextNode(a.textContent));
    });
    return c.textContent.replace(/\s+/g,' ').trim();
  };
  const question=[...root.querySelectorAll('.timed-question-area > div')]
    .filter(e=>visible(e)&&!e.classList.contains('sr-only'));
  const choices=[...root.querySelectorAll('.timed-choices-area button')].filter(visible)
    .map((e,i)=>{e.setAttribute('data-timed-choice',String(i));return {text:clean(e),disabled:e.disabled,index:i};});
  return {url:location.href,text:root.innerText,question:question.length===1?clean(question[0]):'',choices,
    controls:[...root.querySelectorAll('button')].filter(visible).map(e=>e.innerText.trim())};
}'''


def progress(state):
    match=re.search(r'\bScore:\s*(\d+)\s*/\s*(\d+)',state['text'])
    return tuple(map(int,match.groups())) if match else None


def result_summary(state):
    score=progress(state)
    elapsed=re.search(r'Current Time:\s*([\d.]+)',state['text'])
    grade=re.search(r'Grade:\s*(\d+)%',state['text'])
    return (f'Timed round complete: website score {score[0]}/{score[1]}.'
            +(f' Website time: {elapsed[1]} seconds.' if elapsed else '')
            +(f' Grade: {grade[1]}%.' if grade else ''))


async def run_timed(page,journal,emit,authorized):
    # DeltaMath can redirect after DOMContentLoaded. Wait for the app to mount,
    # without using the changing timer as a stability condition.
    state=None
    for attempt in range(30):
        try:
            state=await page.evaluate(READ_TIMED)
            if state:break
            loading=await page.locator('body').inner_text(timeout=1000)
            if loading.strip() and 'Loading' not in loading and attempt>=2:break
        except PlaywrightError as exc:
            if not any(s in str(exc).lower() for s in ('execution context','navigation','context was destroyed')):raise
        await asyncio.sleep(.1)
    if not state or 'Rotation and Reflection Rules' not in state['text']:return None
    if not authorized:return 'Timed round not started: submission was not requested.'
    await page.bring_to_front()
    score=progress(state)
    if not score:return 'Timed round stopped: no readable website score.'
    if score[0]==score[1]:return result_summary(state)
    if 'Start' in state['controls']:
        start=page.get_by_role('button',name='Start',exact=True)
        if await start.count()!=1:return 'Timed round stopped: Start control is ambiguous.'
        emit('Starting timed rotation/reflection round; solving locally without model calls.')
        await start.click(timeout=2000)
    deadline=time.monotonic()+100
    pending=None
    while time.monotonic()<deadline:
        state=await page.evaluate(READ_TIMED)
        if not state:return 'Timed round stopped: page changed.'
        current=progress(state)
        if not current:return 'Timed round stopped: score unreadable.'
        if pending:
            if current[0]==score[0]+1:
                journal.set(pending,'accepted')
                emit(f'Timed round: website score {current[0]}/{current[1]}.')
                pending=None
                score=current
            elif current!=score:
                return 'Timed round stopped: unexpected score change; review the website.'
            else:
                await asyncio.sleep(.05)
                continue
        if current[0]==current[1]:
            return result_summary(state)
        score=current
        if not state['question'] or not state['choices'] or all(c['disabled'] for c in state['choices']):
            await asyncio.sleep(.05)
            continue
        answer=solve_point(state['question'])
        matches=[c for c in state['choices'] if not c['disabled'] and coordinate(c['text'])==answer] if answer is not None else []
        if len(matches)!=1:return 'Timed round stopped: unsupported or ambiguous question: '+state['question']
        signature='timed:'+hashlib.sha256(repr((state['url'],current,state['question'])).encode()).hexdigest()
        if journal.get(signature)=='submission_pending':return 'Timed round stopped: previous uncertain click recorded; review website feedback.'
        # Re-read immediately before clicking; a timer tick is not a new question.
        fresh=await page.evaluate(READ_TIMED)
        if fresh['question']!=state['question'] or progress(fresh)!=current:continue
        chosen=matches[0]
        if fresh['choices']!=state['choices']:continue
        journal.set(signature,'submission_pending')
        try:
            await page.locator('[data-timed-choice="'+str(chosen['index'])+'"]').click(timeout=3000,force=True)
        except Exception:
            return 'Timed round stopped: answer click outcome uncertain; inspect website before retrying.'
        pending=signature
        await asyncio.sleep(.05)
    return 'Timed round stopped after 100 seconds; completion is not confirmed. Review the website score.'
