import asyncio
import sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.connect_over_cdp('http://127.0.0.1:'+sys.argv[1])
        page=[p for p in browser.contexts[0].pages if 'deltamath.com/app/' in p.url][-1]
        if len(sys.argv)>2 and sys.argv[2]=='hit':
            from graph_entry import READ_GRAPH,reflection_pairs
            graph=page.locator('svg.delta-graph')
            data=await graph.evaluate(READ_GRAPH)
            for pair in reflection_pairs(data['shapes']):
                for x,y in pair:
                    pos=[data['x']['zero']+x*data['x']['step'],data['y']['zero']+y*data['y']['step']]
                    print((x,y),pos,await page.evaluate('(p)=>document.elementFromPoint(...p)?.outerHTML.slice(0,700)',pos))
            return
        if len(sys.argv)>2 and sys.argv[2]=='reload':
            await page.reload(wait_until='domcontentloaded')
            await asyncio.sleep(3)
            print((await page.locator('body').inner_text())[-5000:])
            return
        if len(sys.argv)>2 and sys.argv[2]=='links':
            print(await page.locator('a').evaluate_all('els=>els.map(e=>({text:e.innerText,href:e.getAttribute("href")}))'))
            return
        if len(sys.argv)>2 and sys.argv[2]=='fields':
            print(await page.locator('input,select,.mq-editable-field,button').evaluate_all('els=>els.filter(e=>e.getClientRects().length).map(e=>({tag:e.tagName,cls:e.className,label:e.getAttribute("aria-label"),text:e.innerText,html:e.outerHTML.slice(0,1200),parent:e.parentElement.innerText.slice(0,350)}))'))
            return
        if len(sys.argv)>3 and sys.argv[2]=='open':
            await page.get_by_text(sys.argv[3],exact=True).filter(visible=True).click()
            await asyncio.sleep(2)
            print((await page.locator('body').inner_text())[-14000:])
            await page.screenshot(path='delta_live.png',full_page=True)
            return
        print(await page.locator('svg.delta-graph').evaluate_all('''els=>els.map(el=>({
          id:el.id,label:el.getAttribute('aria-label'),
          axes:[...el.querySelectorAll('g')].filter(g=>/axis/.test(g.getAttribute('class')||'')).map(g=>({cls:g.getAttribute('class'),transform:g.getAttribute('transform'),ticks:[...g.querySelectorAll('.tick')].slice(0,3).map(t=>({text:t.textContent,transform:t.getAttribute('transform')}))})),
          controls:[...el.querySelectorAll('[tabindex],circle,polygon')].map(e=>e.outerHTML),
          tail:el.outerHTML.slice(-6000)
        }))'''))

asyncio.run(main())
