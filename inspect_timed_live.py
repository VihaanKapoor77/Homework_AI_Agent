import asyncio,json,sys
from pathlib import Path
from playwright.async_api import async_playwright
from deltamath_tools import DeltaMathTools

async def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    async with async_playwright() as pw:
        browser=await pw.chromium.connect_over_cdp('http://127.0.0.1:'+sys.argv[1])
        page=next(p for p in browser.contexts[0].pages if 'deltamath.com/' in p.url)
        verification_page='--verify-url' in sys.argv
        if '--home' in sys.argv:
            await page.get_by_role('button',name='Back to Home',exact=True).click()
            await asyncio.sleep(2)
        if verification_page:
            page=await browser.contexts[0].new_page()
            await page.goto(sys.argv[sys.argv.index('--verify-url')+1],wait_until='domcontentloaded')
            await page.get_by_text('Score:',exact=False).first.wait_for(timeout=30000)
        if '--next' in sys.argv:
            await page.get_by_role('button',name='Next Problem',exact=True).click()
            await asyncio.sleep(.3)
        if '--stop' in sys.argv:
            await page.get_by_role('button',name='Stop',exact=True).click()
        if '--run' in sys.argv:
            from timed_round import run_timed
            from unified_controller import Journal
            print(await run_timed(page,Journal('logs_and_pngs/timed_live_attempts.sqlite3'),print,True),flush=True)
        if '--start' in sys.argv:
            await page.get_by_role('button',name='Start',exact=True).click()
            await asyncio.sleep(.3)
        from timed_round import READ_TIMED
        snap=await page.evaluate(READ_TIMED)
        if snap is None:snap=await DeltaMathTools().inspect(page)
        print(json.dumps(snap,ensure_ascii=True),flush=True)
        Path('logs_and_pngs/timed_live.html').write_text(await page.content(),encoding='utf-8')
        if verification_page:await page.close()
        if '--close' in sys.argv:
            session=await browser.new_browser_cdp_session()
            await session.send('Browser.close')

asyncio.run(main())
