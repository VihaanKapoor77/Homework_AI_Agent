"""Conservative subject-card adapter. DeltaMath never enters this controller."""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
import uuid
from urllib.parse import urlsplit
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from subject_solver import SubjectSolver,request_url
from unified_controller import Journal
from spanish_rules import category_control


READ_CARD=r'''token => {
 const visible=el=>{const r=el.getBoundingClientRect();
   if(!r.width || !r.height || r.bottom<=0 || r.right<=0 || r.top>=innerHeight || r.left>=innerWidth || getComputedStyle(el).visibility==='hidden')return false;
   const top=document.elementFromPoint(Math.max(0,Math.min(innerWidth-1,r.x+r.width/2)),Math.max(0,Math.min(innerHeight-1,r.y+r.height/2)));
   return !!top && (top===el || el.contains(top));};
 const controls=[...document.querySelectorAll('button,[role="button"],input:not([type="hidden"]),textarea,select,[contenteditable="true"],.drag-source,.drag-zone')]
 .filter(visible).filter(el=>!el.matches('.screenKey')).slice(0,120).map((el,i)=>{
   const id=token+'-'+i;el.setAttribute('data-subject-agent',id);
   const r=el.getBoundingClientRect();
   return {id,kind:el.matches('.drag-source')?'drag_source':el.matches('.drag-zone')?'drag_target':el.tagName==='SELECT'?'select':
      el.matches('textarea,input:not([type="button"]):not([type="submit"]),[contenteditable="true"]')?'text':'button',
      type:el.getAttribute('type')||'',
      label:el.getAttribute('aria-label') || (el.labels?[...el.labels].map(x=>x.innerText).join(' '):'') || el.innerText || el.getAttribute('placeholder') || el.value || '',
      rect:{x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)},
      answer_choice:el.matches('.ol_answer[role="button"]'),
      disabled:!!el.disabled || el.getAttribute('aria-disabled')==='true',
      options:el.tagName==='SELECT'?[...el.options].map(o=>o.label):[]};
 });
 const images=[...document.querySelectorAll('img')].filter(visible).map(el=>({src:el.currentSrc||el.src,alt:el.alt}));
 const backgrounds=[...document.querySelectorAll('div')].filter(visible).map(el=>getComputedStyle(el).backgroundImage).filter(x=>x && x!=='none');
 return {url:location.href,text:(document.body.innerText||'').slice(0,18000),controls,images,backgrounds};
}'''


def fingerprint(card):
    controls=[{k:v for k,v in c.items() if k not in ('id','rect')} for c in card['controls']]
    return hashlib.sha256(json.dumps([card['url'],card['text'],controls,card.get('images'),card.get('backgrounds')],sort_keys=True).encode()).hexdigest()


def boom_activity(url):
    parsed=urlsplit(url)
    return parsed.scheme=='https' and parsed.hostname=='wow.boomlearning.com' and parsed.path.startswith(('/hyperplay/','/play/'))


def can_act(request):
    if re.search(r"\b(?:do not|don't|don’t|never)\s+(?:click|submit|enter|answer)|\b(?:explain only|translate|translation|suggest only)\b",request,re.I):return False
    return bool(re.search(r'\b(?:solve|answer|complete|do|submit|enter|click)\b',request,re.I))


class SubjectController:
    def __init__(self,browser,model,emit,journal_path,subject='Auto'):
        self.browser=browser
        self.solver=SubjectSolver(model)
        self.emit=emit
        self.journal=Journal(journal_path)
        self.subject=subject
        self.last_url=None

    async def run(self,request):
        for _ in range(5):
            result=await self._run_once(request)
            if result!='__instruction_advanced__':return result
            # After the first navigation, inspect the current card without
            # reloading the original activity link.
            request=re.sub(r'https://[^\s<>"\']+','',request)+' Current visible card.'
        return 'Read five instruction cards. Ask again to continue from the current card.'

    async def _run_once(self,request):
        url=request_url(request)
        active=getattr(self.browser,'subject_page',None)
        use_page=bool(url or (active is not None and not active.is_closed() and
            re.search(r'\b(?:visible|current (?:page|card|question)|next (?:one|card|question)|this (?:card|page|activity)|continue)\b|^\s*(?:solve|answer|do|complete|translate)\s+(?:it|this|another)\b',request,re.I)))
        prompt='Subject: '+self.subject+'\n'+request
        if not use_page:
            answer,check=await self.solver.solve(prompt)
            return self.solver.report(answer,check)
        async with self.browser.lock:
            await self.browser.start()
            if active is None or active.is_closed():
                active=await self.browser.connection.contexts[0].new_page()
                self.browser.subject_page=active
            page=active
            if url and page.url!=url:
                await page.goto(url,wait_until='domcontentloaded',timeout=90000)
            await page.wait_for_load_state('domcontentloaded')
            # Let client-side redirects and card rendering settle before observing.
            await asyncio.sleep(2)
            self.last_url=page.url
            if '/signin' in page.url or '/login' in page.url or await page.locator('input[type="password"]:visible').count():
                return 'Sign in manually in the dedicated Chrome window, open your activity, then ask again. No answer was entered.'
            if boom_activity(page.url):
                identity=page.get_by_role('button',name="Yes, That's me",exact=True)
                if await identity.count()==1:
                    await identity.click(timeout=10000)
                if urlsplit(page.url).path.startswith('/hyperplay/'):
                    try:
                        await page.locator('button.fastPlay,button.btn-submit').filter(visible=True).first.wait_for(state='visible',timeout=15000)
                    except PlaywrightTimeoutError:
                        return 'The Boom activity has not loaded. Finish any sign-in prompt and try again; no answer was entered.'
                play=page.locator('button.fastPlay')
                if await play.count()==1 and await play.is_visible():
                    await play.click(timeout=10000)
                    await asyncio.sleep(3)
            card=await page.evaluate(READ_CARD,uuid.uuid4().hex)
            if 'Waiting for connection to server' in card['text']:
                return 'Boom is disconnected from its server. No answer was entered; reconnect or reload the activity before retrying.'
            signature=fingerprint(card)
            if self.journal.get(signature):
                return 'Previous subject-card attempt recorded. Check website feedback before retrying; no automatic repeat.'
            self.emit('Reading the card, translating when needed, and checking the answer independently.')
            answer,check=await self.solver.solve(prompt,card,await page.screenshot(timeout=30000))
            report=self.solver.report(answer,check)
            if not check or not check.correct or not check.target_matches or answer.uncertainty or answer.needs_source:
                return report
            if not can_act(request) or answer.action=='report':return report+'\n\nSuggestion only; no website answer entered.'
            if not boom_activity(page.url):
                return report+'\n\nSuggestion only: automatic answering is supported on Boom activity cards with readable controls.'
            if any(c['kind'] in ('text','select') for c in card['controls']) and any(c.get('answer_choice') for c in card['controls']) and answer.action!='form':
                return 'Not entered: this card requires both a field value and a category choice in one complete form plan.'
            if answer.action=='match':
                return await self.match_card(page,card,signature,answer,report)
            if answer.action=='form':
                return await self.fill_card(page,card,signature,answer,report)
            matches=[c for c in card['controls'] if c['id']==answer.target_id and not c['disabled']]
            if len(matches)!=1:return report+'\n\nNot entered: no unique observed answer control.'
            control=matches[0]
            if any(c['kind']=='text' for c in card['controls']) and control['kind']=='button':
                return 'Not entered: this card needs a text answer as well as a choice. Both must be planned together.'
            instruction=answer.action=='instruction' and control['kind']=='button' and control['label'].strip()=='Next'
            if not instruction and re.search(r'\b(?:sign in|log in|login|logout|delete|buy|purchase|skip|next|home|help|submit|check|done)\b',control['label'],re.I):
                return 'Not entered: selected control is not an answer choice.'
            if answer.action=='instruction' and not instruction:return 'Stopped: no verified Next control for this instruction card.'
            if control['type'] in ('password','file','email','checkbox','radio'):
                return 'Not entered: this control type needs a dedicated adapter.'
            # Detect card changes during model calls, without changing target IDs.
            fresh=await page.evaluate(READ_CARD,'check')
            if fingerprint(fresh)!=signature:return 'Not entered: the card changed during verification. Ask again for the current card.'
            index=card['controls'].index(control)
            target=page.locator('[data-subject-agent="'+fresh['controls'][index]['id']+'"]')
            if await target.count()!=1 or not await target.is_visible() or not await target.is_enabled():
                return 'Not entered: the answer control is no longer available.'
            if instruction:
                self.emit('Reading an instruction card: '+answer.answer)
                await target.click(timeout=10000)
                await asyncio.sleep(2)
                return '__instruction_advanced__'
            # Mark before any interaction: a click, fill or selection may auto-grade.
            self.journal.set(signature,'submission_pending')
            if control['kind']=='button':
                await target.click(timeout=10000)
            else:
                if not answer.value.strip():return 'Not entered: empty answer value; inspect the card before retrying.'
                if control['kind']=='select':
                    if answer.value not in control['options']:return 'Not entered: the requested option was not observed.'
                    await target.select_option(label=answer.value,timeout=10000)
                    if await target.locator('option:checked').inner_text()!=answer.value:
                        return 'Stopped: selected option did not read back correctly.'
                else:
                    await target.fill(answer.value,timeout=10000)
                    value=await target.evaluate('el=>el.isContentEditable?el.innerText:el.value')
                    if value!=answer.value:return 'Stopped: entered answer did not read back correctly.'
                if (await page.locator('body').inner_text())[:18000]!=card['text']:
                    return report+'\n\nThe card changed after entry; stopped before clicking another control. Check website feedback.'
                if not await self.submit_observed(page):
                    return report+'\n\nAnswer entered; no unique Submit/Check button found. Check the card manually.'
            return await self.wait_feedback(page,signature,report)

    async def submit_observed(self,page):
        card=await page.evaluate(READ_CARD,uuid.uuid4().hex)
        buttons=[c for c in card['controls'] if c['kind']=='button' and not c['disabled'] and
            re.fullmatch(r'(?:submit|check|check answer|submit answer|done)',c['label'].strip(),re.I)]
        if len(buttons)!=1:return False
        await page.locator('[data-subject-agent="'+buttons[0]['id']+'"]').click(timeout=10000)
        return True

    async def wait_feedback(self,page,signature,report):
        for _ in range(20):
            await asyncio.sleep(.25)
            bad=page.get_by_text(re.compile(r'^(?:incorrect[.!]?|try again[.!]?|not quite[.!]?)$',re.I)).filter(visible=True)
            good=page.get_by_text(re.compile(r'^(?:correct[.!]?|great job[.!]?|well done[.!]?)$',re.I)).filter(visible=True)
            if await bad.count():return 'Website reported incorrect. Stopped without retrying.\n\n'+report
            if await good.count():
                self.journal.set(signature,'accepted')
                return 'Website acceptance observed: 1 subject question completed.\n\n'+report
        return 'Answer interaction completed; website correctness was not confirmed. Stopped without retrying.\n\n'+report

    async def match_card(self,page,card,signature,answer,report):
        sources={c['id']:c for c in card['controls'] if c['kind']=='drag_source'}
        targets={c['id']:c for c in card['controls'] if c['kind']=='drag_target'}
        pairs=answer.matches
        if not 1<=len(pairs)<=20 or len(pairs)!=len(sources) or len(pairs)!=len(targets) or \
            {p.source_id for p in pairs}!=set(sources) or {p.target_id for p in pairs}!=set(targets):
            return 'Not entered: matching must cover each observed source and target exactly once.'
        fresh=await page.evaluate(READ_CARD,uuid.uuid4().hex)
        if fingerprint(fresh)!=signature:return 'Not entered: the matching card changed during verification.'
        mapping={old['id']:new['id'] for old,new in zip(card['controls'],fresh['controls'])}
        self.journal.set(signature,'submission_pending')
        for pair in pairs:
            self.emit('Matching '+sources[pair.source_id]['label'].strip()+' → '+targets[pair.target_id]['label'].strip())
            source=page.locator('[data-subject-agent="'+mapping[pair.source_id]+'"]')
            target=page.locator('[data-subject-agent="'+mapping[pair.target_id]+'"]')
            if await source.count()!=1 or await target.count()!=1:
                return 'Stopped before submission: a matching control changed.'
            await source.drag_to(target,timeout=10000)
        self.emit('Checking the completed matching layout before submitting.')
        check=await self.solver.verify_entry(answer,card,await page.screenshot(timeout=30000))
        if not check.correct or not check.target_matches:
            return 'Not submitted: matching placement verification failed. '+check.reason
        if not await self.submit_observed(page):return 'Not submitted: no unique visible Submit control.'
        return await self.wait_feedback(page,signature,report)

    async def fill_card(self,page,card,signature,answer,report):
        controls={c['id']:c for c in card['controls']}
        entries=answer.entries
        ids=[entry.target_id for entry in entries]
        required={c['id'] for c in card['controls'] if c['kind'] in ('text','select') and not c['disabled']}
        choice_ids={c['id'] for c in card['controls'] if c.get('answer_choice') and not c['disabled']}
        if not entries or len(entries)>20 or len(set(ids))!=len(ids) or not required.issubset(ids):
            return 'Not entered: the plan must cover every answer field exactly once and all required choices.'
        if required and choice_ids and not choice_ids.intersection(ids):
            return 'Not entered: the required category choice is missing.'
        if required and len(choice_ids) in (5,6) and 'spanish' in self.subject.lower() and not answer.acronym:
            return 'Not entered: specify DOCTOR or PLACE and the full category name.'
        for entry in entries:
            control=controls.get(entry.target_id)
            if not control or control['disabled'] or control['kind'] not in ('text','select','button'):
                return 'Not entered: an answer control is unavailable.'
            if control['type'] in ('password','email','file','checkbox','radio') or re.search(
                r'\b(?:sign|login|logout|delete|buy|purchase|skip|next|previous|home|help|submit|check|done|save|give up|settings|information|sound|overview)\b',control['label'],re.I):
                return 'Not entered: the form plan includes a non-answer control.'
            if control['kind']!='button' and not entry.value.strip():return 'Not entered: a required field is empty.'
            if control['kind']=='select' and entry.value not in control['options']:return 'Not entered: unobserved option.'
        if answer.acronym:
            try:expected=category_control(card['controls'],answer.acronym,answer.category)
            except ValueError as exc:return 'Not entered: '+str(exc)
            selected=[e.target_id for e in entries if controls[e.target_id]['kind']=='button']
            if selected!=[expected]:
                return 'Not entered: the selected tile does not match '+answer.category+' in '+answer.acronym+'.'
        fresh=await page.evaluate(READ_CARD,uuid.uuid4().hex)
        if fingerprint(fresh)!=signature:return 'Not entered: the card changed during verification.'
        mapping={old['id']:new['id'] for old,new in zip(card['controls'],fresh['controls'])}
        self.journal.set(signature,'submission_pending')
        # All field values go in before any category choice can trigger grading.
        ordered=sorted(entries,key=lambda e:controls[e.target_id]['kind']=='button')
        for entry in ordered:
            control=controls[entry.target_id]
            target=page.locator('[data-subject-agent="'+mapping[entry.target_id]+'"]')
            if await target.count()!=1 or not await target.is_visible():return 'Stopped: a form control changed.'
            if control['kind']=='text':
                self.emit('Entering verb/answer: '+entry.value)
                await target.fill(entry.value,timeout=10000)
                if await target.evaluate('el=>el.isContentEditable?el.innerText:el.value')!=entry.value:
                    return 'Not submitted: answer did not read back correctly.'
            elif control['kind']=='select':await target.select_option(label=entry.value,timeout=10000)
            else:
                self.emit('Selecting the verified category: '+answer.answer)
                await target.click(timeout=10000)
        check=await self.solver.verify_entry(answer,card,await page.screenshot(timeout=30000))
        if not check.correct or not check.target_matches:
            return 'Not submitted: full-card verification failed. '+check.reason
        if not await self.submit_observed(page):return 'Answer entered and checked; no unique Submit control.'
        return await self.wait_feedback(page,signature,report)
