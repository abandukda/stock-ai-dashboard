"""Actual Streamlit rendering, generated fixture; separate from live acceptance."""
from io import BytesIO
from PIL import Image
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from playwright.sync_api import sync_playwright

def capture_complete_streamlit(page,path):
    # Capture the actual inner scrolling surface, preserving observed offsets.
    # Hide only Streamlit chrome during evidence capture; never customer content.
    page.add_style_tag(content='[data-testid="stHeader"], [data-testid="stToolbar"] {display:none!important}')
    geometry=page.evaluate("""() => {
      const nodes=[document.scrollingElement,...document.querySelectorAll('*')].filter(e=>e && e.clientHeight>0 && e.scrollHeight>=e.clientHeight);
      const node=nodes.sort((a,b)=>(b.scrollHeight-b.clientHeight)-(a.scrollHeight-a.clientHeight))[0];
      node.setAttribute('data-review-scroll','true');
      return {height:node.scrollHeight,step:node.clientHeight};
    }""")
    if geometry['height']>20000: raise AssertionError('Unexpected fixture page height')
    # A short inner content node is not the screenshot's coordinate system.
    # Preserve the full viewport instead of cropping it at that node's height.
    viewport_height = page.evaluate('window.innerHeight')
    if geometry['height'] <= viewport_height:
        page.screenshot(path=str(path), full_page=True)
        page.evaluate("()=>{const n=document.querySelector('[data-review-scroll]');n.scrollTop=0;n.removeAttribute('data-review-scroll')}")
        return
    canvas=None
    for top in range(0,geometry['height'],geometry['step']):
        actual=page.evaluate("top=>{const n=document.querySelector('[data-review-scroll]');n.scrollTop=top;return n.scrollTop}",top)
        page.wait_for_timeout(80)
        frame=Image.open(BytesIO(page.screenshot())).convert('RGB')
        if canvas is None: canvas=Image.new('RGB',(frame.width,geometry['height']))
        remaining=geometry['height']-actual
        canvas.paste(frame.crop((0,0,frame.width,min(frame.height,remaining))),(0,actual))
    canvas.save(path)
    page.evaluate("()=>{const n=document.querySelector('[data-review-scroll]');n.scrollTop=0;n.removeAttribute('data-review-scroll')}")


class PremiumHomeRender(unittest.TestCase):
    def test_render_all_three_viewports(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        target=Path('audit_results/premium_home');target.mkdir(parents=True,exist_ok=True)
        env=dict(os.environ,PYTHONPATH=os.pathsep.join(filter(None,(str(Path.cwd()),os.environ.get('PYTHONPATH','')))),ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',ATLAS_ALLOW_EXTERNAL_AI='false',ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with (target/'fixture_server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','streamlit','run','scripts/premium_home_review_fixture.py','--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true','--browser.gatherUsageStats=false','--theme.base=dark'],env=env,stdout=log,stderr=subprocess.STDOUT)
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
                            capture_complete_streamlit(page,target/f'GENERATED_HOME_{width}.png')
                            self.assertEqual(page.locator('[data-atlas-qa="home-actionable-card"]').count(),3)
                            self.assertEqual(page.locator('.atlas-home-featured-case').count(),1)
                            self.assertEqual(page.locator('.atlas-reference-command').evaluate("e=>getComputedStyle(e).display"),'grid')
                            self.assertTrue(page.locator('[data-atlas-qa="home-reference-style"]').count())
                            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                            featured_actions=page.locator('[class*="st-key-home_top_idea_position_"]').get_by_role('button',name='View Research →',exact=True)
                            self.assertEqual(featured_actions.count(),3)
                            for button in featured_actions.all():
                                self.assertTrue(button.is_visible())
                                box=button.bounding_box();self.assertIsNotNone(box)
                                self.assertGreaterEqual(box['x'],0);self.assertLessEqual(box['x']+box['width'],width+1)
                            self.assertTrue(page.get_by_text('Public activation OFF',exact=False).count())
                            capture_complete_streamlit(page,target/f'GENERATED_HOME_{width}.png')
                            page.get_by_text('View all 4 BUY NOW opportunities',exact=True).click()
                            search=page.get_by_role('textbox',name='Find an opportunity',exact=True)
                            search.fill('fixture_a');search.press('Enter')
                            page.get_by_text('Showing 1 of 4 published opportunities',exact=False).wait_for()
                            capture_complete_streamlit(page,target/f'GENERATED_HOME_SEARCH_{width}.png')
                            self.assertTrue(page.locator('[class~="st-key-compact_cta_home_all_certified_FIXTURE_A"]').get_by_role('button').is_visible())
                            search.fill('no-such-published-company');search.press('Enter')
                            page.get_by_text('No published opportunities match your search.',exact=False).wait_for()
                            self.assertEqual(page.locator('[class~="st-key-compact_cta_home_all_certified_FIXTURE_A"]').count(),0)
                            search.fill('');search.press('Enter')
                            page.get_by_text('Showing 4 of 4 published opportunities',exact=False).wait_for()
                            owned=page.locator('[class~="st-key-compact_cta_home_governed_quick_CODA"]')
                            owned.get_by_role('button',name='View Research →',exact=True).click()
                            page.wait_for_selector('[data-fixture-selected-ticker="CODA"]',state='attached',timeout=30000)
                            page.close()
                    finally: browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
