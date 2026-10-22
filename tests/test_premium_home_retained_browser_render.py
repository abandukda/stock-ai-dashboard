"""Actual provider-free browser capture of the unavailable-market Home branch."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from playwright.sync_api import sync_playwright, expect
from test_premium_home_render import capture_complete_streamlit


class RetainedHomeBrowser(unittest.TestCase):
    def test_retained_home_three_sizes_and_owned_research_control(self):
        target = Path('audit_results/premium_home')
        target.mkdir(parents=True, exist_ok=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        fixture = '''
import streamlit as st
from ui.home_guidance_vnext import render_home_guidance_vnext
st.set_page_config(layout='wide')
st.warning('GENERATED FIXTURE — NOT MARKET DATA OR PRODUCTION VERIFICATION')
cards=[{'ticker':'TEST'+chr(65+i),'company':'Generated test company','guidance':'BUY_NOW',
'production_rank':i+1,'display_price':101+i,'atlas_fair_value':121+i,
'decision_as_of':'2026-10-04T16:21:00Z','decision_confidence':85} for i in range(11)]
render_home_guidance_vnext({'cards':cards,'home_featured_cards':cards,'scan_timestamp':'2026-10-04T16:21:00Z',
'home_runtime_contract':{'runtime_ready':True,'inventory_authority':{'publishable_buy_now_count':11}}},emit_interactive=lambda:None)
st.markdown('<span data-fixture-complete="true">Fixture complete</span>',unsafe_allow_html=True)
selected = str(st.session_state.get('active_research_ticker',''))
st.markdown('<span data-fixture-selected-ticker="'+selected+'">Selected Research ticker: '+selected+'</span>',unsafe_allow_html=True)
'''
        env = dict(os.environ, PYTHONPATH=str(Path.cwd()), ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',
                   ATLAS_ALLOW_EXTERNAL_AI='false', ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with tempfile.TemporaryDirectory() as temporary, (target/'retained_fixture_server.log').open('w') as log:
            app = Path(temporary)/'retained_home.py'
            app.write_text(fixture)
            process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(app),
                '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
                '--browser.gatherUsageStats=false', '--theme.base=dark'], env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic()+30
                while time.monotonic()<deadline:
                    if process.poll() is not None: self.fail('Retained Home fixture exited')
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1',port))==0: break
                    time.sleep(.2)
                else: self.fail('Retained Home fixture startup timeout')
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    try:
                        for width in (360, 768, 1440):
                            page = browser.new_page(viewport={'width':width,'height':1000})
                            try:
                                page.goto(f'http://127.0.0.1:{port}')
                                page.wait_for_selector('[data-fixture-complete="true"]', timeout=30000)
                                self.assertEqual(page.locator('[data-testid="stException"]').count(),0)
                                note = page.locator('[data-atlas-qa="home-published-inventory-note"]')
                                self.assertIn('11 published BUY NOW opportunities', note.inner_text())
                                self.assertIn('Not a live refresh', note.inner_text())
                                expect(page.locator('[data-atlas-qa="home-actionable-card"]')).to_have_count(3, timeout=15000)
                                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                                capture_complete_streamlit(page,target/f'GENERATED_RETAINED_HOME_{width}.png')
                                page.locator('.st-key-home_top_idea_position_1').get_by_role('button',name='View Research →',exact=True).click()
                                selected = page.locator('[data-fixture-selected-ticker="TESTA"]')
                                selected.wait_for(state='visible', timeout=15000)
                                self.assertEqual(selected.inner_text(), 'Selected Research ticker: TESTA')
                            except Exception:
                                page.screenshot(path=str(target/f'FAILED_RETAINED_HOME_{width}.png'), full_page=True)
                                (target/f'FAILED_RETAINED_HOME_{width}_DOM.html').write_text(page.content())
                                raise
                            finally: page.close()
                    finally: browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
