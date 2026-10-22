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

    async def test_independent_existing_viewer_surfaces_keep_role_source_and_read_only_state(self):
        """Real rendered guards/screens; generated routes, never private production QA."""
        import time
        from unittest.mock import AsyncMock, patch
        from agents.runtime_qa_user_journeys_v40 import PAGE_QA_IDS
        routes={'Home':'Home','Research Any Ticker':'Research',
                'Watchlist Intelligence':'Watchlist','Ask AI':'Ask ATLAS'}
        radios=''.join(f'<label><input type="radio" name="route" {"checked" if label=="Home" else ""}>{label}</label>' for label in routes.values())
        content=('<h2>GENERATED VIEWER ROUTES — NOT PRODUCTION</h2>'+radios
            +'<div data-atlas-qa="customer-navigation-contract" data-atlas-contract-version="ATLAS_CUSTOMER_NAV_R1_1" '
            +'data-atlas-source-sha="'+('a'*40)+'" data-atlas-role-category="customer_viewer" '
            +'data-atlas-customer-routes="Home|Research|Watchlist|Ask ATLAS" data-atlas-active-route="Home"></div>'
            +'<div id="atlas-qa-page-home" data-atlas-page="home" data-atlas-page-ready="true">Generated route ready</div>'
            +'<input id="unsubmitted-question" value="Generated unchanged question">'
            +'<div id="unmodified-watchlist">Generated unchanged account list</div>')
        await self.page.set_content('<iframe title="Generated test app" style="width:100%;height:750px" srcdoc="'+html.escape(content,quote=True)+'"></iframe>')
        c=self.crawler;c.started=time.monotonic();c.expected_deployed_source_sha='a'*40
        c._record=AsyncMock();c._submit_research=AsyncMock(side_effect=AssertionError('No research submission'))
        c._ask=AsyncMock(side_effect=AssertionError('No question submission'))
        c._watchlist_edit_journey=AsyncMock(side_effect=AssertionError('No account edits'))
        shots=[]
        async def capture(page,**kw):
            if kw['interaction']=='post-chart-failure-diagnostic':
                path=self.out/f"GENERATED_ONLY_{kw['viewport']}_{PAGE_QA_IDS[kw['page_name']]}.png"
                await page.screenshot(path=str(path));shots.append((kw['page_name'],kw['viewport']))
                return str(path)
            return 'generated-role-guard'
        c._shot=capture
        async def navigate(page,label):
            frame=page.frames[1]
            await frame.evaluate('''({label,pageid})=>{
                for(const r of document.querySelectorAll('input[type=radio]'))r.checked=r.parentElement.textContent===label;
                const n=document.querySelector('[data-atlas-page-ready]');
                n.id='atlas-qa-page-'+pageid;n.setAttribute('data-atlas-page',pageid);
                document.querySelector('[data-atlas-qa="customer-navigation-contract"]').setAttribute('data-atlas-active-route',label);
            }''',{'label':routes[label],'pageid':PAGE_QA_IDS[label]})
            return True,0,'generated route selection'
        with patch('agents.atlas_visual_crawler_v1._navigate',new=navigate):
            await c._capture_chart_failure_views(self.page)
        self.assertEqual(len(shots),12)
        self.assertEqual({x[0] for x in shots},set(routes))
        self.assertEqual(await self.page.frame_locator('iframe').locator('#unsubmitted-question').input_value(),'Generated unchanged question')
        self.assertEqual(await self.page.frame_locator('iframe').locator('#unmodified-watchlist').inner_text(),'Generated unchanged account list')
        c._submit_research.assert_not_awaited();c._ask.assert_not_awaited();c._watchlist_edit_journey.assert_not_awaited()
        captures=[x for x in c._record.await_args_list if x.kwargs['category']=='FAILURE_DIAGNOSTIC']
        self.assertEqual(len(captures),12)
        self.assertTrue(all(x.kwargs['required'] is False for x in captures))
