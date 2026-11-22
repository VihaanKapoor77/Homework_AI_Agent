"""Live inspection and regression for the timed round, using the agent profile."""
import asyncio
import json
import sys
from pathlib import Path
from agent import browser, delta

URL='https://www.deltamath.com/app/student/5643551/35114314/eac45c7373614026750a77bb41f840ef'

async def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    page=await browser.page()
    await page.goto(URL,wait_until='domcontentloaded')
    print('READY',flush=True)
    while True:
        command=await asyncio.to_thread(sys.stdin.readline)
        if not command or command.strip()=='quit':break
        try:
            if command.strip()=='read':
                print(await page.locator('body').inner_text(),flush=True)
                print(await page.locator('button').evaluate_all('(els)=>els.map(e=>({text:e.innerText,html:e.outerHTML}))'),flush=True)
            elif command.strip()=='snapshot':
                print(json.dumps(await delta.inspect(page),ensure_ascii=False),flush=True)
            elif command.startswith('click '):
                await page.get_by_role('button',name=command[6:].strip(),exact=True).click()
            elif command.strip()=='html':
                Path('logs_and_pngs/timed_live.html').write_text(await page.content(),encoding='utf-8')
                print('Saved rendered DOM',flush=True)
            elif command.strip()=='run':
                from unified_controller import UnifiedController
                from math_solver import calculate
                async def solve(op,expression,variable='x'):return calculate(op,expression,variable)
                controller=UnifiedController(browser,delta,None,solve,None,None,'unused',print,
                    Path('logs_and_pngs/timed_live_attempts.sqlite3'))
                print(await controller.run('Solve 10 questions in 100 seconds'),flush=True)
        except Exception as exc:print(type(exc).__name__,str(exc),flush=True)
    await browser.close()

if __name__=='__main__':asyncio.run(main())
