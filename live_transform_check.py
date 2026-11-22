"""Supervised live transformation regression using an existing agent browser."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from playwright.async_api import async_playwright
import os
from dotenv import load_dotenv
from deltamath_tools import DeltaMathTools
from math_solver import calculate
from unified_controller import UnifiedController

async def main():
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    load_dotenv()
    delta=DeltaMathTools()
    async with async_playwright() as pw:
        connection=await pw.chromium.connect_over_cdp('http://127.0.0.1:'+sys.argv[1])
        page=next(p for p in connection.contexts[0].pages if 'deltamath.com/app/student/' in p.url)
        await page.bring_to_front()
        if '--navigate' in sys.argv:
            await page.goto(sys.argv[2],wait_until='domcontentloaded')
            await page.get_by_label('select the first transformation',exact=True).wait_for(timeout=30000)
        snapshot=await delta.inspect(page)
        print('CURRENT '+json.dumps({k:snapshot[k] for k in ('url','question_text','fields','skills')}),flush=True)
        if '--controls' in sys.argv:
            samples=[]
            for position in ('first','second'):
                select=page.get_by_label('select the '+position+' transformation',exact=True)
                kinds=await select.locator('option').all_text_contents()
                for kind in (k for k in kinds if k.strip()):
                    await select.select_option(label=kind)
                    snap=await delta.inspect(page)
                    samples.append({'position':position,'kind':kind,'fields':snap['fields']})
            Path('logs_and_pngs/transform_controls_'+page.url.rsplit('/',1)[-1]+'.json').write_text(json.dumps(samples,indent=2),encoding='utf-8')
            print('CONTROLS '+json.dumps(samples),flush=True)
        if '--solve' in sys.argv:
            async def current_page():return page
            async def solve(op,expression,variable='x'):return calculate(op,expression,variable)
            profile=Path(os.getenv('BROWSER_PROFILE_DIR') or Path.home()/'.assignment-agent'/'chrome')
            controller=UnifiedController(SimpleNamespace(lock=asyncio.Lock(),page=current_page),delta,
                None,solve,None,None,os.getenv('MODEL','gemini-3.5-flash-lite'),
                lambda s:print(s,flush=True),profile.parent/'answer_attempts.sqlite3')
            result=await controller.run('Solve 4 questions' if '--four' in sys.argv else 'Solve exactly one question')
            print('RESULT '+result,flush=True)
            print('FEEDBACK '+(await page.locator('body').inner_text())[-3000:],flush=True)
        await pw.stop()

if __name__=='__main__':asyncio.run(main())
