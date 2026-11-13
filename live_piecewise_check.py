"""Opt-in live check using the study app's existing dedicated profile."""
import asyncio
import json
import sys
import time

import agent
from unified_controller import UnifiedController


async def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    started = time.monotonic()
    try:
        page = await agent.browser.page()
        await page.goto(sys.argv[1], wait_until='domcontentloaded')
        await page.wait_for_selector('svg.delta-graph', timeout=30000)
        if len(sys.argv) > 2 and sys.argv[2] in ('solve','next-solve'):
            controller = UnifiedController(agent.browser, agent.delta, agent.vision_solver,
                agent.solve_math_impl, agent.learn_example_impl, agent.example_notes,
                agent.MODEL, lambda s: print(s, flush=True),
                agent.PROFILE_DIR.parent/'answer_attempts.sqlite3', lookup=agent.math_memory)
            if sys.argv[2]=='next-solve':
                if not await controller.advance_to_next():
                    raise RuntimeError('No unique next-question control')
            count=int(sys.argv[3]) if len(sys.argv)>3 else 1
            print(await controller.run(f'Solve {count} questions'), flush=True)
        else:
            print(json.dumps(await page.locator('svg.delta-graph').evaluate_all(
                "els=>els.map(e=>({html:e.outerHTML}))")), flush=True)
            print(json.dumps(await page.locator('.katex-mathml, math').evaluate_all(
                'els=>els.map(e=>e.outerHTML)')), flush=True)
        print((await page.locator('body').inner_text())[:5000], flush=True)
        await page.screenshot(path='delta_live.png', full_page=True)
        print(f'Elapsed: {time.monotonic()-started:.1f}s', flush=True)
    finally:
        await agent.browser.close()


if __name__ == '__main__':
    asyncio.run(main())
