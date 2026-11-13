import unittest
import os
from unittest.mock import patch
from deltamath_tools import DeltaMathTools
from graph_entry import transformed_points, graph_plan, plot_points, READ_GRAPH, reflection_pairs, reflected_points
from playwright.async_api import async_playwright

class TransformationTests(unittest.TestCase):
    def test_horizontal_vertical_and_diagonal_reflections(self):
        source=[(1,4),(3,4),(9,8)]
        self.assertEqual(reflected_points(source,[(-10,2),(10,2)]),[(1,0),(3,0),(9,-4)])
        self.assertEqual(reflected_points(source,[(2,-10),(2,10)]),[(3,4),(1,4),(-5,8)])
        self.assertEqual(reflected_points(source,[(-10,-10),(10,10)]),[(4,1),(4,3),(8,9)])
        with self.assertRaises(ValueError):reflected_points(source,[(-10,2),(0,3),(10,2)])
    def test_reflection_matches_by_geometry_not_vertex_order(self):
        pairs=reflection_pairs([{'color':'lightpink','points':[(-7,-9),(-5,-4),(-8,-3)]},
            {'color':'lightblue','points':[(0,1),(5,3),(-1,4)]}])
        self.assertEqual(pairs,[((-7,-9),(5,3)),((-5,-4),(0,1)),((-8,-3),(-1,4))])
    def test_live_translation_all_vertices_deduplicated(self):
        self.assertEqual(transformed_points('Translate the figure 3 units left and 6 units down.',[(3,4),(4,2),(9,3),(9,7),(8,6),(3,4)]),[(0,-2),(1,-4),(6,-3),(6,1),(5,0)])
    def test_right_up(self):
        self.assertEqual(transformed_points('Translate the figure 2 units right and 1 unit up.',[(-2,-1),(0,0),(1,2)]),[(0,0),(2,1),(3,3)])
    def test_unreadable_points_fail(self):
        with self.assertRaises(ValueError):transformed_points('Translate the figure 3 units left and 6 units down.',[(1.2,2),(1,2),(3,4)])
    def test_other_task_not_assumed_translation(self):
        self.assertIsNone(transformed_points('Reflect over the x-axis',[(1,2)]))

@unittest.skipUnless(os.getenv('RUN_BROWSER_TESTS')=='1','Local Chromium tests opt-in')
class GraphBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_math_clear_ignores_stale_accessibility_announcement(self):
        from math_keyboard import enter_keyboard
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,executable_path=os.getenv('TEST_CHROME_PATH'))
            page=await browser.new_page()
            await page.set_content('''<span id="field" tabindex="0"><span class="sr-only">3 selected</span><span class="mq-root-block">3</span></span>
            <script>document.querySelector('#field').addEventListener('keydown',e=>{
              if(e.key==='Backspace'){e.preventDefault();document.querySelector('.mq-root-block').textContent='';}
              else if(e.key.length===1&&!e.ctrlKey&&!e.metaKey)document.querySelector('.mq-root-block').textContent+=e.key;
            });</script>''')
            await enter_keyboard(page.locator('#field'),'5')
            self.assertEqual(await page.locator('.mq-root-block').inner_text(),'5')
            await browser.close()

    async def test_scaled_scrolled_graph_readback_and_idempotent_resume(self):
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,executable_path=os.getenv('TEST_CHROME_PATH'))
            page=await browser.new_page()
            await page.set_content('''<div style="height:900px"></div><svg class="delta-graph" viewBox="0 0 240 240" style="width:480px;height:480px">
            <g transform="translate(20,20)"><rect width="200" height="200" fill="white"/>
            <g class="x axis"><g class="tick" transform="translate(0,100)"><text>-10</text></g><g class="tick" transform="translate(200,100)"><text>10</text></g></g>
            <g class="y axis"><g class="tick" transform="translate(100,0)"><text>10</text></g><g class="tick" transform="translate(100,200)"><text>-10</text></g></g>
            <g><path class="func" fill="lightpink" d="M130,60L140,80L190,70"/><circle cx="130" cy="60" r="2"/><circle cx="140" cy="80" r="2"/><circle cx="190" cy="70" r="2"/></g>
            <circle aria-label="Point plotter tool" r="0"/></g></svg>
            <script>document.querySelector('svg').addEventListener('click',e=>{
              const root=e.currentTarget.firstElementChild,p=new DOMPoint(e.clientX,e.clientY).matrixTransform(root.getScreenCTM().inverse());
              const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
              c.setAttribute('cx',p.x);c.setAttribute('cy',p.y);c.setAttribute('r',3);c.setAttribute('class','delta-point');c.setAttribute('myid','user');c.setAttribute('aria-label','Plotted point');root.append(c);
              const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('class','func');root.append(path);
            });</script>''')
            text='Translate the figure 3 units left and 6 units down.'
            delta=DeltaMathTools()
            with patch('deltamath_tools.is_deltamath',lambda _:True):
                original=(await delta.inspect(page))['signature']
            points=await graph_plan(page,text)
            self.assertEqual(points,[(0,-2),(1,-4),(6,-3)])
            await plot_points(page,points)
            await plot_points(page,points)
            self.assertEqual(await page.locator('.delta-point').count(),3)
            self.assertEqual(await graph_plan(page,text),points)
            with patch('deltamath_tools.is_deltamath',lambda _:True):
                self.assertEqual((await delta.inspect(page))['signature'],original)
                await page.locator('path[fill="lightpink"]').evaluate("el=>el.setAttribute('d','M130,60L140,80L180,90')")
                self.assertNotEqual((await delta.inspect(page))['signature'],original)
            with self.assertRaises(ValueError):await plot_points(page,[(0,0)])
            await browser.close()
