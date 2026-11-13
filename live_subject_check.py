"""Inspect or test one authorized subject activity through the app's browser."""
import asyncio
import json
import sys
import re
from playwright.async_api import TimeoutError as PlaywrightTimeoutError,async_playwright
import agent


async def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    browser=agent.browser
    attached=None
    try:
        if '--cdp-port' in sys.argv:
            from types import SimpleNamespace
            port=int(sys.argv[sys.argv.index('--cdp-port')+1])
            attached=await async_playwright().start()
            connection=await attached.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
            pages=[p for context in connection.contexts for p in context.pages if 'wow.boomlearning.com/' in p.url]
            page=pages[-1] if pages else await connection.contexts[0].new_page()
            async def started():pass
            browser=SimpleNamespace(lock=asyncio.Lock(),start=started,connection=connection,subject_page=page)
            if not pages or '--navigate' in sys.argv:await page.goto(sys.argv[1],wait_until='domcontentloaded',timeout=90000)
        else:
            page=await browser.page()
            await page.goto(sys.argv[1],wait_until='domcontentloaded',timeout=90000)
        if '--reload' in sys.argv:await page.reload(wait_until='domcontentloaded',timeout=90000)
        await asyncio.sleep(5)
        if '--wait-login' in sys.argv and '/signin' in page.url:
            print('Please sign in manually in the dedicated Chrome window. Waiting up to 10 minutes.',flush=True)
            for _ in range(300):
                await asyncio.sleep(2)
                if '/hyperplay/' in page.url:break
            await asyncio.sleep(3)
        print('URL:',page.url,flush=True)
        if '--start' in sys.argv:
            identity=page.get_by_role('button',name="Yes, That's me",exact=True)
            if await identity.count()==1:
                await identity.click(timeout=10000)
                await asyncio.sleep(2)
            play=page.locator('button.fastPlay')
            try:
                await play.wait_for(state='visible',timeout=15000)
                await play.click(timeout=30000)
                await asyncio.sleep(5)
            except PlaywrightTimeoutError:
                print('No Play button appeared; inspecting the current screen.',flush=True)
        if '--next' in sys.argv:
            await page.locator('button.btn-submit').filter(has_text='Next').click(timeout=10000)
            await asyncio.sleep(3)
        if '--exercise' in sys.argv:
            # These five lesson cards were inspected in this live test.
            for _ in range(5):
                next_button=page.locator('button.btn-submit').filter(has_text='Next')
                if not await next_button.count():break
                await next_button.click(timeout=10000)
                await asyncio.sleep(1)
        if '--verb' in sys.argv:
            # The vocabulary matching card was already live-tested as Correct.
            if await page.locator('.drag-source:visible').count():
                await page.locator('button.playNextCard:visible').click(timeout=10000)
                await asyncio.sleep(2)
        if '--solve' in sys.argv:
            from subject_browser import SubjectController
            browser.subject_page=page
            controller=SubjectController(browser,agent.MODEL,lambda s:print(s,flush=True),
                agent.PROFILE_DIR.parent/'subject_attempts.sqlite3','Spanish / Translation')
            print('SOLVER RESULT:',await controller.run('Solve and submit one visible Spanish question. Read instruction cards first.'),flush=True)
        print((await page.locator('body').inner_text())[:16000],flush=True)
        print(json.dumps(await page.locator('button, input, [role="button"], [contenteditable], select').evaluate_all('''els => els.filter(el=>el.getBoundingClientRect().width && el.getBoundingClientRect().height).map(el=>({tag:el.tagName,role:el.getAttribute('role'),type:el.getAttribute('type'),text:el.innerText,label:el.getAttribute('aria-label'),cls:el.className})).slice(0,100)'''),ensure_ascii=False),flush=True)
        await page.screenshot(path='subject_live.png')
        print('CUSTOM CONTROLS:',await page.locator('div,span').evaluate_all('''els=>els.filter(el=>el.getBoundingClientRect().width && el.getBoundingClientRect().height && el.innerText && el.innerText.length<100 && (el.getAttribute('tabindex')!==null || getComputedStyle(el).cursor==='pointer')).map(el=>({tag:el.tagName,cls:el.className,text:el.innerText,role:el.getAttribute('role'),tabindex:el.getAttribute('tabindex')})).slice(-100)'''),flush=True)
        print('FRAMES:',[frame.url for frame in page.frames],flush=True)
        print('VISUAL ELEMENTS:',await page.locator('img,canvas,svg,iframe').evaluate_all('''els=>els.filter(el=>el.getBoundingClientRect().width && el.getBoundingClientRect().height).map(el=>({tag:el.tagName,cls:el.className.baseVal||el.className,src:el.getAttribute('src'),role:el.getAttribute('role'),label:el.getAttribute('aria-label')})).slice(-30)'''),flush=True)
        print('PLAY ITEMS:',await page.locator('.playItem').evaluate_all('''els=>els.filter(el=>el.getBoundingClientRect().width && el.getBoundingClientRect().height).map(el=>({classes:[...el.classList].filter(c=>!c.startsWith('wants-')),text:el.innerText,role:el.getAttribute('role'),rect:(()=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()}))'''),flush=True)
        if '--interactive' in sys.argv:
            while True:
                command=(await asyncio.to_thread(input,'Live command (solve/inspect/reviewed-retry/exit): ')).strip()
                if command=='exit':break
                if command=='solve':
                    import importlib
                    import subject_solver,subject_browser
                    importlib.reload(subject_solver);importlib.reload(subject_browser)
                    browser.subject_page=page
                    ctrl=subject_browser.SubjectController(browser,agent.MODEL,lambda s:print(s,flush=True),agent.PROFILE_DIR.parent/'subject_attempts.sqlite3','Spanish')
                    print(await ctrl.run('Solve and submit one visible Spanish card.'),flush=True)
                if command=='reviewed-retry':
                    from subject_browser import READ_CARD,fingerprint
                    from unified_controller import Journal
                    snap=await page.evaluate(READ_CARD,'review')
                    Journal(agent.PROFILE_DIR.parent/'subject_attempts.sqlite3').clear(fingerprint(snap))
                    print('Cleared the reviewed current-card attempt only.',flush=True)
                print((await page.locator('body').inner_text())[-10000:],flush=True)
                await page.screenshot(path='subject_live.png')
    finally:
        if attached:await attached.stop()
        else:await browser.close()


if __name__=='__main__':asyncio.run(main())
