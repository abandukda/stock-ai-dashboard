"""Actual Streamlit rendering, generated fixture; separate from live acceptance."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from playwright.sync_api import sync_playwright

class PremiumHomeRender(unittest.TestCase):
    def test_render_all_three_viewports(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        target=Path('audit_results/premium_home');target.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ,PYTHONPATH=str(Path.cwd()),ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',ATLAS_ALLOW_EXTERNAL_AI='false',ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with (target/'fixture_server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/premium_home_review_fixture.py','--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true','--browser.gatherUsageStats=false'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    if process.poll() is not None: self.fail('Fixture process exited')
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1',port))==0: break
                    time.sleep(.2)
                else: self.fail('Fixture startup timed out')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    try:
                        for width in (360,768,1440):
                            page=browser.new_page(viewport={'width':width,'height':1000})
                            page.goto(f'http://127.0.0.1:{port}')
                            page.wait_for_selector('[data-fixture-complete="true"]',timeout=30000)
                            page.screenshot(path=str(target/f'GENERATED_HOME_{width}.png'),full_page=True)
                            self.assertEqual(page.locator('[data-atlas-qa="home-actionable-card"]').count(),3)
                            self.assertEqual(page.locator('.atlas-home-featured-case').count(),1)
                            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                            self.assertEqual(page.get_by_text('View Research →',exact=True).count(),3)
                            for button in page.get_by_text('View Research →',exact=True).all():
                                box=button.bounding_box();self.assertIsNotNone(box)
                                self.assertGreaterEqual(box['x'],0);self.assertLessEqual(box['x']+box['width'],width+1)
                            self.assertTrue(page.get_by_text('Public activation OFF',exact=False).count())
                            page.screenshot(path=str(target/f'GENERATED_HOME_{width}.png'),full_page=True)
                            page.close()
                    finally: browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
