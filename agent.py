"""DeltaMath study agent: one Playwright controller + local math + Gemini vision.
No legacy LangGraph/browser-use loop, no repeated login requirement, no hidden APIs.
"""
from __future__ import annotations
import asyncio
import atexit
import contextlib
import contextvars
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
load_dotenv()
import gradio as gr
from filelock import FileLock
from pydantic import BaseModel,ConfigDict,Field,model_validator,create_model
from playwright.async_api import async_playwright,TimeoutError as PlaywrightTimeoutError,Error as PlaywrightError
from settings import ACTION_MS,NAVIGATION_MS,STARTUP_SECONDS,REQUEST_SECONDS,LLM_SECONDS
from task_runtime import BrowserTimedOut,recover_once,ScheduleStore
from deltamath_tools import DeltaMathTools,is_deltamath
from delta_workflow import ExampleNotes,click_discovered,EXAMPLE
from vision_math import VisionMath
from unified_controller import UnifiedController,Journal
from gemini_client import generate_json
from gemini_budget import RATE
from adaptive_math import MathMemory
from subject_solver import subject_route
from subject_browser import SubjectController

MODEL=os.getenv('MODEL','gemini-3.5-flash-lite')
PROFILE_DIR=Path(os.getenv('BROWSER_PROFILE_DIR') or (Path.home()/'.assignment-agent'/'chrome')).expanduser().resolve()
EVENTS=contextvars.ContextVar('events',default=None)
ENTRY_FAILURES=contextvars.ContextVar('entry_failures',default=None)


def emit(message:str):
    queue=EVENTS.get()
    if queue is not None:queue.put_nowait(str(message))

# Surface request pacing and transient-service recovery in the chat progress log.
import gemini_budget
import gemini_client
gemini_budget.REPORT=emit
gemini_client.REPORT=emit

def error(code,message):return f'[{code}] {message}'

def find_chrome():
    candidate=os.getenv('CHROME_PATH','').strip()
    choices=[candidate,shutil.which('chrome'),shutil.which('google-chrome'),shutil.which('chromium'),
         '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    if os.name=='nt':
        choices += [str(Path(os.getenv(root,'C:/'))/'Google/Chrome/Application/chrome.exe')
                    for root in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA')]
    return next((str(x) for x in choices if x and Path(x).is_file()),None)

class SharedBrowser:
    def __init__(self):
        self.lock=asyncio.Lock()
        self.state_lock=asyncio.Lock()
        self.process=None
        self.profile_lock=None
        self.pw=None
        self.connection=None
        self.subject_page=None
        self.active_subject=False
    async def start(self):
        async with self.state_lock:
            if self.connection and self.connection.is_connected():return
            await self._stop()
            chrome=find_chrome()
            if not chrome:raise RuntimeError('Chrome not found. Set CHROME_PATH to chrome.exe in .env.')
            PROFILE_DIR.mkdir(parents=True,exist_ok=True)
            self.profile_lock=FileLock(str(PROFILE_DIR)+'.lock',thread_local=False)
            self.profile_lock.acquire(timeout=0)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            args=[chrome,f'--remote-debugging-port={port}','--remote-debugging-address=127.0.0.1',
                  f'--user-data-dir={PROFILE_DIR}','--no-first-run','--no-default-browser-check','about:blank']
            if os.getenv('HEADLESS','false').lower()=='true':args.append('--headless=new')
            try:
                self.process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                endpoint=f'http://127.0.0.1:{port}'
                import urllib.request
                def ready():
                    try:
                        with urllib.request.urlopen(endpoint+'/json/version',timeout=.5) as response:
                            return response.status==200
                    except Exception:return False
                started=time.monotonic()
                while time.monotonic()-started<STARTUP_SECONDS:
                    if await asyncio.to_thread(ready):break
                    if self.process.poll() is not None:raise RuntimeError('Dedicated Chrome exited during startup')
                    await asyncio.sleep(.2)
                else:raise TimeoutError('Dedicated Chrome startup timed out')
                self.pw=await async_playwright().start()
                self.connection=await self.pw.chromium.connect_over_cdp(endpoint,timeout=NAVIGATION_MS)
                for context in self.connection.contexts:
                    context.set_default_timeout(ACTION_MS)
                    context.set_default_navigation_timeout(NAVIGATION_MS)
                emit('Connected to reusable Chrome profile; manual sign-in is only needed if the session expired.')
            except BaseException:
                await self._stop()
                raise
    async def page(self):
        await self.start()
        ctx=self.connection.contexts[0]
        pages=[page for page in ctx.pages if not page.is_closed()]
        for page in reversed(pages):
            if is_deltamath(page.url):return page
        for page in reversed(pages):
            try:
                if await asyncio.wait_for(page.evaluate('document.hasFocus()'),timeout=1):return page
            except Exception:pass
        return pages[-1] if pages else await ctx.new_page()
    async def _stop(self):
        if self.connection and self.connection.is_connected():
            with contextlib.suppress(Exception):
                session=await self.connection.new_browser_cdp_session()
                await session.send('Browser.close')
        if self.pw:
            with contextlib.suppress(Exception):await self.pw.stop()
        self.connection=self.pw=None
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:await asyncio.to_thread(self.process.wait,3)
                except subprocess.TimeoutExpired:
                    self.process.kill();await asyncio.to_thread(self.process.wait,3)
            self.process=None
        if self.profile_lock:
            self.profile_lock.release();self.profile_lock=None
    async def close(self):
        async with self.state_lock:await self._stop()
    def cleanup(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        if self.profile_lock:
            with contextlib.suppress(Exception):self.profile_lock.release()

browser=SharedBrowser()
atexit.register(browser.cleanup)
delta=DeltaMathTools(os.getenv('DELTAMATH_QUESTION_SELECTOR','auto'))
vision_solver=VisionMath(os.getenv('MATH_VISION_MODEL',MODEL),LLM_SECONDS)
example_notes=ExampleNotes(PROFILE_DIR.parent/'observed_examples.sqlite3')
math_memory=MathMemory()
TASK_LOCK=asyncio.Lock()

async def rate_limit_retry_after():
    # Rate limit only actual Gemini requests, not UI chat requests.
    return 0

async def solve_math_impl(operation,expression,variable='x'):
    """Bounded subprocess, so infinite symbolic work cannot block the UI."""
    emit('Checking exact math with local SymPy.')
    worker=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('math_solver.py')),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(worker.communicate(json.dumps({'operation':operation,'expression':expression,'variable':variable}).encode()),timeout=10)
        data=json.loads(stdout.decode()) if stdout else {'error':stderr.decode()[:300]}
        return json.dumps(data)
    except asyncio.TimeoutError:
        return json.dumps({'error':'Symbolic calculation exceeded 10 seconds','complete':False})
    finally:
        if worker.returncode is None:
            worker.kill();await worker.wait()

async def learn_example_impl(topic,acquire_lock=True):
    async def run():
        page=await browser.page()
        snap=await delta.inspect(page)
        await click_discovered(page,snap,EXAMPLE)
        emit('Reading the visible worked example and learning its method.')
        result=await vision_solver.solve(page,'Explain this visible worked example for '+topic+
             '. Do not confuse it with the active question.',calculate=solve_math_impl)
        if result.get('status')=='candidate' and result.get('method'):
            example_notes.save(topic,{k:result.get(k) for k in ('question','method','answer','diagram_observations')})
        return json.dumps({**result,'next':'Close the example and return to the active question.'})
    try:
        if acquire_lock:
            async with browser.lock:return await run()
        return await run()
    except Exception as exc:return error('EXAMPLE_ERROR',str(exc)[:500])

async def reopen_browser(preferred_url=None):
    async with browser.lock:
        await browser.close()
        delta.latest=None
        vision_solver.cache.clear()
        page=await browser.page()
        if preferred_url and preferred_url.startswith('https://') and is_deltamath(preferred_url):
            await page.goto(preferred_url,wait_until='domcontentloaded',timeout=NAVIGATION_MS)

async def second_math_impl(problem,failed_attempt=''):
    from math_specialist import second_opinion
    return json.dumps(await second_opinion(problem,failed_attempt,solve_math_impl,
                    None,os.getenv('MATH_MODEL',MODEL),LLM_SECONDS))

# Compatibility with the original typed tool schemas; runtime uses UnifiedController.
class ActionResult(BaseModel):
    error:str|None=None
    extracted_content:str|None=None

class DeltaReadParams(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request:str=Field(default='read')
    @model_validator(mode='before')
    @classmethod
    def clean(cls,value):
        if isinstance(value,dict):
            value=dict(value);value.pop('_placeholder',None)
        return value
class MathParams(BaseModel):
    operation:str
    expression:str
    variable:str='x'
class VisionParams(BaseModel):
    mode:str='solve'
    expected_latex:str=''
    request:str='Solve visible math problem.'
    selector:str='auto'
class _CompatRegistry:
    def __init__(self):
        from types import SimpleNamespace
        self.registry=SimpleNamespace(actions={})
    def create_action_model(self):
        fields={name:(spec.param_model|None,None) for name,spec in self.registry.actions.items()}
        return create_model('LegacyActionModel',__config__=ConfigDict(extra='forbid'),**fields)
class _CompatTools:
    def __init__(self):self.registry=_CompatRegistry()
    def register(self,name,params,fn):
        from types import SimpleNamespace
        self.registry.registry.actions[name]=SimpleNamespace(param_model=params,function=fn)
browser_tools=_CompatTools()
async def _math_action(params):
    res=await solve_math_impl(params.operation,params.expression,params.variable)
    result=json.loads(res)
    return ActionResult(error=res if result.get('error') else None,extracted_content=None if result.get('error') else res)
async def _read_action(params):
    try:
        async with browser.lock:result=await delta.inspect(await browser.page())
        return ActionResult(extracted_content=json.dumps(result,default=str))
    except Exception as exc:return ActionResult(error=str(exc))
async def _feedback_action(params):
    try:
        async with browser.lock:result=await delta.feedback(await browser.page())
        return ActionResult(extracted_content=json.dumps(result))
    except Exception as exc:return ActionResult(error=str(exc))
async def _vision_action(params):
    try:
        async with browser.lock:
            result=await vision_solver.solve(await browser.page(),params.request,params.selector,params.mode,params.expected_latex,solve_math_impl)
        return ActionResult(extracted_content=json.dumps(result))
    except Exception as exc:return ActionResult(error=str(exc))
for name,typ,fn in [('browser_math',MathParams,_math_action),('browser_delta_read',DeltaReadParams,_read_action),
                    ('browser_delta_feedback',DeltaReadParams,_feedback_action),
                    ('browser_solve_math_from_screenshot',VisionParams,_vision_action)]:
    browser_tools.register(name,typ,fn)
from types import SimpleNamespace
TOOLS=[SimpleNamespace(name='solve_math_from_screenshot')]
def build_graph():
    raise RuntimeError('The legacy LangGraph loop was removed to eliminate repeated tool calls. Use UnifiedController instead.')

async def chat(message,history,request: gr.Request,subject='Auto'):
    history=list(history or [])
    history.append({'role':'user','content':message})
    if await rate_limit_retry_after():
        history.append({'role':'assistant','content':'Rate limited. Retry later.'})
        yield history
        return
    history.append({'role':'assistant','content':'Inspecting current question…'})
    yield [dict(x) for x in history]
    queue=asyncio.Queue()
    started=time.monotonic()
    async def worker():
        token=EVENTS.set(queue)
        try:
            route=subject_route(message,subject,browser.active_subject)
            browser.active_subject=route=='subject'
            if route=='subject':
                controller=SubjectController(browser,MODEL,emit,
                    PROFILE_DIR.parent/'subject_attempts.sqlite3',subject)
            else:
                controller=UnifiedController(browser,delta,vision_solver,solve_math_impl,learn_example_impl,
                            example_notes,MODEL,emit,PROFILE_DIR.parent/'answer_attempts.sqlite3',fast_mode=False,lookup=math_memory)
            async def invoke(resuming):
                prompt=message
                if resuming:
                    prompt=re.sub(r'https://[^\s<>\"\']+', '', prompt)
                    prompt+=' Recovery after timeout: inspect current feedback; never resubmit a pending attempt.'
                try:return await asyncio.wait_for(controller.run(prompt),timeout=REQUEST_SECONDS)
                except (PlaywrightTimeoutError,TimeoutError) as exc:raise BrowserTimedOut(str(exc)) from exc
            async def restart():
                await reopen_browser(controller.last_url)
            if TASK_LOCK.locked():emit('Waiting for the current task to release the browser.')
            async with TASK_LOCK:
                # Subject clicks can auto-grade. Never restart and replay an
                # uncertain interaction on a different site.
                if route=='subject':return await invoke(False)
                return await recover_once(invoke,restart,emit)
        finally:EVENTS.reset(token)
    task=asyncio.create_task(worker())
    steps=[]
    last_update=time.monotonic()
    try:
        while not task.done() or not queue.empty():
            try:
                text=await asyncio.wait_for(queue.get(),timeout=.2)
                steps.append(text)
                last_update=time.monotonic()
                history[-1]['content']='**Steps**\n'+'\n'.join('- '+x for x in steps[-12:])+'\n\nWorking…'
                yield [dict(x) for x in history]
            except asyncio.TimeoutError:
                if time.monotonic()-last_update>=5 and not task.done():
                    last_update=time.monotonic()
                    history[-1]['content']=('**Steps**\n'+'\n'.join('- '+x for x in steps[-12:])+'\n\n' if steps else '')+f'Working — {time.monotonic()-started:.0f}s elapsed. Waiting for the current operation to finish.'
                    yield [dict(x) for x in history]
        result=await task
        elapsed_label='Paused after' if 'whole-assignment completion is NOT confirmed' in str(result) else 'Finished in'
        history[-1]['content']=('**Steps**\n'+'\n'.join('- '+x for x in steps[-12:])+'\n\n' if steps else '')+str(result)+f'\n\n{elapsed_label} {time.monotonic()-started:.1f}s.'
    except Exception as exc:
        history[-1]['content']=error('AGENT_ERROR',f'{type(exc).__name__}: {exc}')
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(Exception,asyncio.CancelledError):await task
    yield [dict(x) for x in history]

schedule_store=ScheduleStore(PROFILE_DIR.parent/'scheduled_tasks.sqlite3')
schedule_worker=None
scheduler_start_lock=asyncio.Lock()
async def schedule_loop():
    while True:
        if not TASK_LOCK.locked():
            job=await asyncio.to_thread(schedule_store.claim)
            if job:
                try:
                    final=[]
                    async for update in chat(job['task'],[],None):final=update
                    result=str(final[-1]['content']) if final else 'No output'
                    status='failed' if result.startswith(('[AGENT_ERROR]','[RATE_LIMITED]')) else 'finished'
                    await asyncio.to_thread(schedule_store.finish,job['id'],status,result)
                except asyncio.CancelledError:
                    await asyncio.to_thread(schedule_store.finish,job['id'],'interrupted','Stopped without confirmation')
                    raise
                except Exception as exc:
                    await asyncio.to_thread(schedule_store.finish,job['id'],'failed',str(exc)[:500])
        await asyncio.sleep(2)
async def start_scheduler():
    global schedule_worker
    async with scheduler_start_lock:
        if schedule_worker is None or schedule_worker.done():
            await asyncio.to_thread(schedule_store.interrupt_running)
            schedule_worker=asyncio.create_task(schedule_loop())
    return 'Scheduler active while this application remains running.'
async def add_schedule(when,zone,task):
    try:
        identity=await asyncio.to_thread(schedule_store.add,when,zone,task)
        await start_scheduler()
        return f'Scheduled {identity} for {when} ({zone}). Keep the computer and app running.'
    except Exception as exc:return str(exc)
async def list_schedules():
    return json.dumps(await asyncio.to_thread(schedule_store.listing),indent=2)
async def cancel_schedule(identity):return await asyncio.to_thread(schedule_store.cancel,identity)
async def allow_reviewed_retry():
    if TASK_LOCK.locked():return 'Stop the running task before allowing retry.'
    async with browser.lock:
        if browser.active_subject and browser.subject_page is not None and not browser.subject_page.is_closed():
            from subject_browser import READ_CARD,fingerprint
            current=await browser.subject_page.evaluate(READ_CARD,uuid.uuid4().hex)
            Journal(PROFILE_DIR.parent/'subject_attempts.sqlite3').clear(fingerprint(current))
            return 'Retry allowed for the current subject card after your review of website feedback.'
        current=await delta.inspect(await browser.page())
        Journal(PROFILE_DIR.parent/'answer_attempts.sqlite3').clear(current['signature'])
    return 'Retry allowed for this question. Verify current feedback first.'

with gr.Blocks(title='Study Agent') as demo:
    gr.Markdown('# Study Agent\nDeltaMath exact math checks, Spanish translation, English, social studies and science help. Subject answers receive an independent second check. Boom cards with readable answer controls can be answered one at a time; other sites receive suggestions.')
    bot=gr.Chatbot(height=520)
    subject=gr.Dropdown(choices=['Auto','Math / DeltaMath','Spanish / Translation','English','Social studies','Science','General'],value='Auto',label='Subject')
    entry=gr.Textbox(label='Message',placeholder='Paste an activity link, ask a subject question, or type Translate: followed by text.')
    send_button=gr.Button('Send',variant='primary')
    send=gr.on([entry.submit,send_button.click],chat,[entry,bot,subject],bot,concurrency_limit=1)
    send.then(lambda:'',outputs=entry)
    gr.Button('Stop').click(fn=None,cancels=[send])
    retry_box=gr.Textbox(label='Retry status',interactive=False)
    gr.Button('Allow retry after checking website feedback').click(allow_reviewed_retry,outputs=retry_box)
    with gr.Accordion('Schedule a task',open=False):
        when=gr.Textbox(label='Date and time',placeholder='2026-11-15 16:00')
        zone=gr.Dropdown(choices=['America/New_York','EST (fixed UTC-5)','UTC'],value='America/New_York',label='Time zone')
        scheduled_task=gr.Textbox(label='Task and DeltaMath URL')
        result_box=gr.Textbox(label='Schedule status',interactive=False)
        gr.Button('Schedule').click(add_schedule,[when,zone,scheduled_task],result_box)
        output=gr.Textbox(label='Tasks and results',lines=8,interactive=False)
        gr.Button('Refresh schedules').click(list_schedules,outputs=output)
        cancel_id=gr.Textbox(label='Task ID to cancel')
        gr.Button('Cancel pending task').click(cancel_schedule,cancel_id,result_box)
    demo.load(start_scheduler,outputs=result_box)
    gr.Markdown('Chrome profile is reused. If sign-in has expired, sign in manually in the visible Chrome window; the agent never needs your password.')

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--login':
        from urllib.parse import urlsplit
        url=sys.argv[2] if len(sys.argv)>2 else os.getenv('LOGIN_URL','')
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            raise SystemExit('Supply a valid HTTPS login URL, without credentials in the URL.')
        chrome=find_chrome()
        if not chrome:raise SystemExit('Could not find Chrome; set CHROME_PATH in .env.')
        PROFILE_DIR.mkdir(parents=True,exist_ok=True)
        with FileLock(str(PROFILE_DIR)+'.lock',timeout=0):
            print('Sign in manually. Close this dedicated Chrome window when finished.')
            subprocess.run([chrome,f'--user-data-dir={PROFILE_DIR}','--no-first-run',url],check=True)
    else:
        demo.queue(default_concurrency_limit=1).launch(server_name='127.0.0.1',share=False)

if __name__=='__main__':main()
