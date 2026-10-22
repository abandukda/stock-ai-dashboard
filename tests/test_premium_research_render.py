"""Full active Research renderer: generated evidence, no live acceptance claim."""
import os
from pathlib import Path
import socket, subprocess, sys, time, unittest
from playwright.sync_api import sync_playwright
from test_premium_home_render import capture_complete_streamlit


class PremiumResearchRender(unittest.TestCase):
    def test_four_ticker_views_at_three_sizes(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        target=Path('audit_results/premium_research');target.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ,PYTHONPATH=str(Path.cwd()),ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',ATLAS_ALLOW_EXTERNAL_AI='false',ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with (target/'fixture_server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/premium_research_review_fixture.py','--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true','--browser.gatherUsageStats=false','--theme.base=dark'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    if process.poll() is not None: self.fail('Research fixture exited')
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1',port))==0: break
                    time.sleep(.2)
                else: self.fail('Research fixture startup timeout')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    try:
                        for ticker in ('NVDA','MSFT','META','ANET'):
                            for width in (360,768,1440):
                                page=browser.new_page(viewport={'width':width,'height':1000})
                                page.goto(f'http://127.0.0.1:{port}/?ticker={ticker}')
                                page.wait_for_selector('[data-fixture-complete="true"]',timeout=30000)
                                self.assertEqual(page.locator('[data-testid="stException"]').count(),0)
                                self.assertTrue(page.locator('[data-atlas-qa="research-executive-digest"]').is_visible())
                                self.assertEqual(page.locator('[data-atlas-qa="research-v2-annotated-chart"]').get_attribute('data-atlas-ticker'),ticker)
                                self.assertTrue(page.locator('.y4title').count())
                                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                                capture_complete_streamlit(page,target/f'GENERATED_{ticker}_{width}_SIMPLE.png')
                                page.get_by_role('tab',name='Detailed View',exact=True).click()
                                self.assertEqual(page.locator('[data-atlas-qa="research-comprehensive-analysis"] article').count(),6)
                                self.assertTrue(page.locator('[data-atlas-qa="research-comprehensive-analysis"]').is_visible())
                                capture_complete_streamlit(page,target/f'GENERATED_{ticker}_{width}_DETAILED.png')
                                page.close()
                    finally: browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
