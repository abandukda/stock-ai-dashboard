"""Real Chromium regression for diagnostic render settlement, never production QA."""
import html
import asyncio
import unittest
from pathlib import Path
from playwright.async_api import async_playwright
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, GlobalCrawlFailure

class DiagnosticSettlementBrowser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(headless=True)
        self.page=await self.browser.new_page(viewport={"width":360,"height":800})
        self.crawler=object.__new__(AtlasVisualCrawler)
        self.out=Path("audit_results/diagnostic_render_settlement");self.out.mkdir(parents=True,exist_ok=True)

    async def asyncTearDown(self):
        await self.browser.close();await self.pw.stop()

    async def fixture(self,*,delay=None,wrong_route=False,exception=False):
        marker='<div id="atlas-qa-page-home" data-atlas-page="home" data-atlas-page-ready="false">Pending generated route</div>'
        radios='<label><input type="radio" name="route" '+('' if wrong_route else 'checked')+'>Home</label><label><input type="radio" name="route" '+('checked' if wrong_route else '')+'>Research</label>'
        script='' if delay is None else '<script>setTimeout(()=>{let n=document.querySelector("#atlas-qa-page-home");n.setAttribute("data-atlas-page-ready","true");n.textContent="Completed generated Home route"},'+str(delay)+')</script>'
        error='<div data-testid="stException">Generated application exception</div>' if exception else ''
        content='<h2>GENERATED QA FIXTURE — NO MARKET DATA</h2>'+radios+marker+error+script
        await self.page.set_content('<iframe style="width:100%;height:750px" srcdoc="'+html.escape(content,quote=True)+'"></iframe>')

    async def test_delayed_completed_iframe_route_is_observed_without_reclick(self):
        await self.fixture()
        marker=self.page.frame_locator('iframe').locator('#atlas-qa-page-home')
        self.assertEqual(await marker.get_attribute('data-atlas-page-ready'),'false')
        async def complete_render():
            await asyncio.sleep(.35)
            await marker.evaluate('n=>{n.setAttribute("data-atlas-page-ready","true");n.textContent="Completed generated Home route"}')
        completion=asyncio.create_task(complete_render())
        await self.crawler._wait_diagnostic_route_ready(self.page,"Home",timeout_seconds=3)
        await completion
        self.assertTrue(await self.page.frame_locator('iframe').get_by_role('radio',name='Home',exact=True).is_checked())
        await self.page.screenshot(path=str(self.out/'GENERATED_delayed_route_completed.png'))

    async def test_wrong_route_with_ready_stale_marker_fails_closed(self):
        await self.fixture(delay=1,wrong_route=True)
        with self.assertRaisesRegex(GlobalCrawlFailure,'DIAGNOSTIC_RENDER_INCOMPLETE'):
            await self.crawler._wait_diagnostic_route_ready(self.page,"Home",timeout_seconds=.5)
        await self.page.screenshot(path=str(self.out/'GENERATED_wrong_route_rejected.png'))

    async def test_never_complete_and_application_exception_remain_failures(self):
        await self.fixture()
        with self.assertRaisesRegex(GlobalCrawlFailure,'DIAGNOSTIC_RENDER_INCOMPLETE'):
            await self.crawler._wait_diagnostic_route_ready(self.page,"Home",timeout_seconds=.3)
        await self.fixture(delay=1,exception=True)
        with self.assertRaisesRegex(GlobalCrawlFailure,'DIAGNOSTIC_APPLICATION_EXCEPTION'):
            await self.crawler._wait_diagnostic_route_ready(self.page,"Home",timeout_seconds=1)
        await self.page.screenshot(path=str(self.out/'GENERATED_exception_rejected.png'))
