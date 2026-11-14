"""Run the real whole-deck controller on an existing dedicated browser tab."""
import asyncio
import sys
from types import SimpleNamespace
from playwright.async_api import async_playwright
import agent
from subject_browser import SubjectController,card_screenshot


async def main():
    async with async_playwright() as pw:
        connection=await pw.chromium.connect_over_cdp('http://127.0.0.1:'+sys.argv[1])
        page=next(p for c in connection.contexts for p in c.pages if 'wow.boomlearning.com/play/' in p.url)
        async def start():pass
        browser=SimpleNamespace(lock=asyncio.Lock(),start=start,connection=connection,subject_page=page)
        ctrl=SubjectController(browser,agent.MODEL,lambda s:print(s,flush=True),agent.PROFILE_DIR.parent/'subject_attempts.sqlite3','Spanish')
        try:
            print(await ctrl.run('Complete the WHOLE deck on the current visible page. Continue until the website shows the entire deck is finished.'),flush=True)
        finally:
            from pathlib import Path
            Path('deck_final.png').write_bytes(await card_screenshot(page))
            print('FINAL VISIBLE TEXT:',await page.locator('body').inner_text(),flush=True)


if __name__=='__main__':asyncio.run(main())
