"""Actual browser review of GENERATED personal workspace; no production acceptance."""
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from test_personal_watchlists_ui import app_source
from test_premium_home_render import capture_complete_streamlit


def _generated_source(root):
    source = app_source(root)
    catalog = [{"ticker": "NVDA", "company": "Nvidia · GENERATED REVIEW EVIDENCE", "security_id": "nvda", "certified_customer_evaluation": {
        "ticker": "NVDA", "customer_publication_allowed": True,
        "decision": {"action": "HOLD", "opportunity": 0, "decision_confidence": 80},
        "fields": {"atlas_fair_value": {"value": 100, "certification_status": "CERTIFIED"}},
    }}]
    source = source.replace("catalog=[{'ticker':'NVDA','company':'Nvidia','security_id':'nvda'}]", "catalog=" + repr(catalog))
    source = source.replace("render_personal_watchlists(controller=controller)", '''
# Fixed test-only Bob fixture, never selected through browser identity fields.
bob = service.register('test:bob', plan=PlanTier.PREMIUM)[0]
if not service.repository.list_watchlists(bob.user_id):
    service.create_watchlist(bob.user_id, 'BOB PRIVATE NEVER VISIBLE')
def open_research(ticker):
    st.session_state['generated_research_ticker'] = ticker
st.caption('GENERATED NOT PRODUCTION — synthetic authority tests navigation only')
if st.query_params.get('mode') == 'pending':
    render_personal_watchlists()
else:
    render_personal_watchlists(controller=controller, open_research=open_research)
if st.session_state.get('generated_research_ticker'):
    st.markdown('<span data-generated-research="NVDA">Generated Research callback: NVDA</span>', unsafe_allow_html=True)
st.markdown('<span data-fixture-complete="true"></span>', unsafe_allow_html=True)
''')
    return source


class PremiumPersonalWatchlistsRender(unittest.TestCase):
    def test_owned_workspace_at_three_sizes_and_pending(self):
        target = Path('audit_results/premium_home/personal_watchlists')
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='atlas-generated-watchlist-') as temporary:
            root = Path(temporary)
            fixture = root/'fixture.py'
            fixture.write_text(_generated_source(root/'private'), encoding='utf-8')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, PYTHONPATH=str(Path.cwd()), ATLAS_QA_PROVIDER_CALLS_ALLOWED='0', ATLAS_ALLOW_EXTERNAL_AI='false', ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
            with (target/'fixture_server.log').open('w') as log:
                process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(fixture), '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true', '--browser.gatherUsageStats=false', '--theme.base=dark'], env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic()+30
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            self.fail('Generated watchlist fixture exited')
                        with socket.socket() as probe:
                            if probe.connect_ex(('127.0.0.1', port)) == 0:
                                break
                        time.sleep(.2)
                    else:
                        self.fail('Generated watchlist startup timeout')
                    with sync_playwright() as playwright:
                        browser = playwright.chromium.launch(headless=True)
                        try:
                            for width in (360, 768, 1440):
                                context = browser.new_context(viewport={'width': width, 'height': 1000})
                                def local_only(route):
                                    parsed = urlsplit(route.request.url)
                                    if parsed.hostname == '127.0.0.1' and parsed.port == port:
                                        route.continue_()
                                    else:
                                        route.abort()
                                context.route('**/*', local_only)
                                page = context.new_page()
                                try:
                                    page.goto(f'http://127.0.0.1:{port}')
                                    page.wait_for_selector('[data-fixture-complete="true"]', state='attached')
                                    if width == 360:
                                        name = page.get_by_label('Watchlist name', exact=True)
                                        name.wait_for()
                                        name.fill('Owned research workspace')
                                        page.get_by_role('button', name='Create watchlist', exact=True).click()
                                    heading = page.locator('.atlas-personal-watchlist-head h1')
                                    heading.wait_for(state='visible')
                                    self.assertEqual(heading.inner_text(), 'Personal watchlists')
                                    self.assertEqual(page.locator('[data-testid="stMarkdownPre"]').count(), 0)
                                    owned_list = page.get_by_role('combobox', name=re.compile(r'Choose watchlist$'))
                                    owned_list.wait_for(state='visible')
                                    self.assertIn('Owned research workspace', owned_list.get_attribute('aria-label'))
                                    page.get_by_label('Find a ticker or company', exact=True).fill('nvda')
                                    page.get_by_label('Find a ticker or company', exact=True).press('Enter')
                                    page.get_by_role('button', name='Add ticker', exact=True).click()
                                    research = page.get_by_role('button', name='Open Research — NVDA', exact=True)
                                    research.wait_for()
                                    self.assertTrue(research.is_enabled())
                                    research.click()
                                    page.wait_for_selector('[data-generated-research="NVDA"]', state='attached')
                                    page.reload()
                                    page.get_by_role('button', name='Remove NVDA', exact=True).wait_for()
                                    self.assertEqual(page.locator('[data-testid="stException"]').count(), 0)
                                    self.assertNotIn('BOB PRIVATE NEVER VISIBLE', page.locator('body').inner_text())
                                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width+1)
                                    capture_complete_streamlit(page, target/f'GENERATED_PERSONAL_{width}.png')
                                    page.get_by_role('button', name='Remove NVDA', exact=True).click()
                                    page.get_by_text('No companies saved in this watchlist yet.', exact=False).wait_for()
                                    page.goto(f'http://127.0.0.1:{port}/?mode=pending')
                                    page.get_by_text('Shared-password sessions cannot use personal saved lists.', exact=False).wait_for()
                                    self.assertEqual(page.get_by_role('button', name='Add ticker', exact=True).count(), 0)
                                    self.assertEqual(page.locator('[data-testid="stException"]').count(), 0)
                                    self.assertNotIn('BOB PRIVATE NEVER VISIBLE', page.locator('body').inner_text())
                                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width+1)
                                    capture_complete_streamlit(page, target/f'GENERATED_PENDING_{width}.png')
                                except Exception:
                                    page.screenshot(path=str(target/f'FAILED_{width}.png'), full_page=True)
                                    (target/f'FAILED_{width}_DOM.html').write_text(page.content(), encoding='utf-8')
                                    raise
                                finally:
                                    context.close()
                        finally:
                            browser.close()
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
