"""Attach to the running app browser for supervised live DeltaMath checks."""
import asyncio
import sys
from types import SimpleNamespace
from playwright.async_api import async_playwright
import agent
from unified_controller import UnifiedController


async def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    async with async_playwright() as pw:
        if sys.argv[1]=='app':
            await agent.browser.start()
            connection = agent.browser.connection
        else:
            connection = await pw.chromium.connect_over_cdp('http://127.0.0.1:'+sys.argv[1])
        pages = [p for p in connection.contexts[0].pages if 'deltamath.com/' in p.url]
        page = pages[-1] if pages else await connection.contexts[0].new_page()
        await page.bring_to_front()
        if '--keep' not in sys.argv:
            await page.goto(sys.argv[2], wait_until='domcontentloaded', timeout=90000)
        await asyncio.sleep(5)
        async def current_page(): return page
        browser = SimpleNamespace(lock=asyncio.Lock(), page=current_page)
        controller = UnifiedController(browser, agent.delta, agent.vision_solver,
            agent.solve_math_impl, agent.learn_example_impl, agent.example_notes,
            agent.MODEL, lambda s: print(s, flush=True),
            agent.PROFILE_DIR.parent/'answer_attempts.sqlite3', lookup=agent.math_memory)
        while True:
            print('URL:',page.url,flush=True)
            print((await page.locator('body').inner_text())[-18000:],flush=True)
            try:await page.screenshot(path='delta_live.png',timeout=5000)
            except Exception as exc:print('Inspection screenshot unavailable:',type(exc).__name__,flush=True)
            command=(await asyncio.to_thread(input,'Command (solve/next/inspect/exit): ')).strip()
            if command=='exit':break
            if command=='solve' or command.startswith('batch '):
                import importlib, graph_entry, unified_controller, math_keyboard, deltamath_tools, gemini_client
                importlib.reload(math_keyboard)
                importlib.reload(deltamath_tools)
                importlib.reload(gemini_client)
                importlib.reload(graph_entry)
                importlib.reload(unified_controller)
                agent.delta.__class__=deltamath_tools.DeltaMathTools
                controller.__class__=unified_controller.UnifiedController
                request='Solve and submit exactly one question on this page.' if command=='solve' else 'Solve '+command.split()[1]+' questions and submit.'
                try:print(await controller.run(request),flush=True)
                except Exception as exc:print('STOPPED:',repr(exc),flush=True)
            elif command=='next':print('ADVANCED:',await controller.advance_to_next(),flush=True)
            elif command=='dom':
                print(await page.locator('svg,canvas').evaluate_all('els=>els.map(el=>({tag:el.tagName,id:el.id,cls:el.getAttribute("class"),html:el.outerHTML.slice(0,26000)}))'),flush=True)


if __name__=='__main__':asyncio.run(main())
