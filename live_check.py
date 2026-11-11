"""Run one authorized live question using the application's current controller."""
import asyncio
import sys
import time
import agent
from unified_controller import Plan, UnifiedController


async def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    assert Plan(uncertainty=False).uncertainty == ''
    print('Current boolean-uncertainty fix loaded.',flush=True)
    started=time.perf_counter()
    try:
        page=await agent.browser.page()
        await page.goto(sys.argv[1],wait_until='domcontentloaded',timeout=90000)
        if '--feedback' in sys.argv:
            await asyncio.sleep(3)
            print((await page.locator('body').inner_text())[:10000],flush=True)
            return
        if '--inspect' in sys.argv:
            await page.wait_for_selector('.mq-editable-field',timeout=30000)
            print(await page.locator('.mq-editable-field').first.evaluate('''el => {
                const rows=[]; for(let p=el;p && rows.length<7;p=p.parentElement)
                    rows.push({tag:p.tagName,id:p.id,cls:p.className,text:p.innerText.slice(0,800)});
                return rows;
            }'''),flush=True)
            return
        # Allow manual sign-in without asking for or reading credentials.
        if await page.locator('input[type=password]').count() or '/login' in page.url:
            print('LOGIN_REQUIRED: sign in manually in the Chrome window; waiting up to 3 minutes.',flush=True)
            for _ in range(90):
                await asyncio.sleep(2)
                if '/app/student/' in page.url and not await page.locator('input[type=password]').count():
                    break
            else:
                print('Login not completed; no answers submitted.',flush=True)
                return
        # The SPA can briefly show its landing/login shell after DOMContentLoaded.
        # Start the live test only once the actual assignment controls render.
        await page.get_by_role('button',name='Submit Answer',exact=True).wait_for(state='visible',timeout=30000)
        controller=UnifiedController(agent.browser,agent.delta,agent.vision_solver,
            agent.solve_math_impl,agent.learn_example_impl,agent.example_notes,
            agent.MODEL,lambda s:print(s,flush=True),
            agent.PROFILE_DIR.parent/'answer_attempts.sqlite3',fast_mode=False,lookup=agent.math_memory)
        if '--probe-confirmation' in sys.argv:
            await page.get_by_role('button',name='Submit Answer',exact=True).click(timeout=30000)
            await asyncio.sleep(1)
            print('CONFIRMATION TEXT: '+(await page.locator('body').inner_text())[-5000:],flush=True)
            print(await page.get_by_role('button',name='Yes',exact=True).evaluate_all('''els=>els.map(el=>{const a=[];for(let p=el;p && a.length<5;p=p.parentElement)a.push({tag:p.tagName,role:p.getAttribute('role'),cls:p.className,text:p.innerText.slice(0,1500)});return a})'''),flush=True)
            return
        result=await asyncio.wait_for(controller.run('Solve and submit exactly one question on this page.'),timeout=240)
        print(result,flush=True)
        print('VISIBLE RESULT: '+(await page.locator('body').inner_text())[-7000:],flush=True)
        print('YES CONTROLS: '+str(await page.get_by_role('button',name='Yes',exact=True).evaluate_all('''els=>els.map(el=>{const a=[];for(let p=el;p && a.length<5;p=p.parentElement)a.push({tag:p.tagName,role:p.getAttribute('role'),cls:p.className,text:p.innerText.slice(0,1500)});return a})''')),flush=True)
        if result.startswith('Not submitted:'):
            snapshot=await agent.delta.inspect(page)
            print('ENTRY DIAGNOSTIC: '+__import__('json').dumps({k:snapshot.get(k) for k in ('question_text','math','images','fields','buttons')},ensure_ascii=True),flush=True)
        print(f'Live elapsed seconds: {time.perf_counter()-started:.2f}',flush=True)
    finally:
        await agent.browser.close()


if __name__=='__main__':
    asyncio.run(main())
