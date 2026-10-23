"""Actual Chromium individual Home journey; generated identity/evidence only."""
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect
from tests.test_personal_home_runtime import personal_home_script
from tests.test_premium_customer_composition_render import _watchlist_creation_controls
from tests.test_premium_home_render import capture_complete_streamlit


def test_individual_home_research_and_private_account_switch_at_three_sizes():
    target = Path('audit_results/premium_home/personal_home')
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='atlas-personal-home-') as temporary:
        root = Path(temporary)
        source = personal_home_script(root/'private', root/'cache')
        source = source.replace('import _atlas_composition_server_fixture as server', '''
from types import ModuleType
if '_atlas_composition_server_fixture' not in sys.modules:
 fixture=ModuleType('_atlas_composition_server_fixture')
 fixture.logged_in=False;fixture.subject='alice';fixture.revoked=False;fixture.expired=False
 sys.modules[fixture.__name__]=fixture
import _atlas_composition_server_fixture as server
''')
        source = source.replace("now=datetime(2026,10,23,tzinfo=timezone.utc)", '''
if st.button('GENERATED reset Alice'):
 server.logged_in=False;server.subject='alice';server.revoked=False;server.expired=False
 st.rerun()
if st.button('GENERATED select Bob'):
 server.subject='bob'
 st.rerun()
now=datetime(2026,10,23,tzinfo=timezone.utc)''')
        fixture = root/'fixture.py'
        fixture.write_text(source)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ, STREAMLIT_GLOBAL_DEVELOPMENT_MODE='false',
                   PYTHONPATH=str(Path.cwd()), ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',
                   ATLAS_ALLOW_EXTERNAL_AI='false', ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with (target/'GENERATED_server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(fixture),
                '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
                '--browser.gatherUsageStats=false', '--theme.base=dark'], env=env,
                stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic()+30
                while time.monotonic()<deadline:
                    assert process.poll() is None, 'generated app exited'
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1', port)) == 0:
                            break
                    time.sleep(.2)
                else:
                    raise AssertionError('generated app startup timeout')
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    try:
                        for width in (360, 768, 1440):
                            context = browser.new_context(viewport={'width': width, 'height': 1000})
                            denied = []
                            def local_only(route):
                                url = urlsplit(route.request.url)
                                if url.hostname == '127.0.0.1' and url.port == port:
                                    route.continue_()
                                else:
                                    denied.append(route.request.url); route.abort()
                            context.route('**/*', local_only)
                            page = context.new_page()
                            page.goto(f'http://127.0.0.1:{port}')
                            page.get_by_role('button', name='GENERATED reset Alice', exact=True).click()
                            page.get_by_role('button', name='Sign in to ATLAS', exact=True).click()
                            name = _watchlist_creation_controls(page)
                            name.fill(f'Alice private {width}')
                            page.get_by_role('button', name='Create watchlist', exact=True).click()
                            if width != 360:
                                page.get_by_role('combobox', name=re.compile(r'Choose watchlist$')).click()
                                page.get_by_role('option', name=f'Alice private {width}', exact=True).click()
                            page.locator('.atlas-personal-watchlist-name').filter(has_text=f'Alice private {width}').wait_for()
                            page.get_by_test_id('stRadio').get_by_text('Home', exact=True).click()
                            page.locator('[data-extracted-composition="complete"][data-result="HOME_RENDERED"]').wait_for(state='attached')
                            assert page.locator('[data-atlas-qa="home-actionable-card"]').count() == 1
                            assert page.get_by_role('button', name='Ask ATLAS', exact=True).count() == 0
                            assert page.get_by_text('PRIVATE_OTHER_ACCOUNT', exact=False).count() == 0
                            assert page.locator('[data-testid="stException"]').count() == 0
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                            capture_complete_streamlit(page, target/f'GENERATED_PERSONAL_HOME_{width}.png')
                            button = page.get_by_role('button', name='View Research →', exact=True).first
                            expect(button).to_be_visible()
                            box = button.bounding_box()
                            assert box and box['x'] >= 0 and box['x'] + box['width'] <= width + 1
                            button.click()
                            page.locator('[data-atlas-qa="research-production-authority"][data-atlas-ticker="NVDA"]').wait_for(state='attached')
                            expect(page.get_by_label('Ticker', exact=True)).to_have_value('NVDA')
                            assert page.locator('[data-testid="stException"]').count() == 0
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                            capture_complete_streamlit(page, target/f'GENERATED_PERSONAL_HOME_TO_NVDA_{width}.png')
                            page.get_by_role('button', name='GENERATED select Bob', exact=True).click()
                            page.locator('[data-extracted-composition="complete"][data-result="EMPTY"]').wait_for(state='attached')
                            expect(page.get_by_role('radio', name='Watchlist', exact=True)).to_be_checked()
                            assert page.locator('.atlas-personal-watchlist-name').count() == 0
                            assert page.get_by_text(f'Alice private {width}', exact=False).count() == 0
                            assert page.locator('[data-atlas-qa="research-production-authority"]').count() == 0
                            assert page.locator('[data-testid="stException"]').count() == 0
                            capture_complete_streamlit(page, target/f'GENERATED_BOB_PRIVATE_EMPTY_{width}.png')
                            page.get_by_role('button', name='Sign out', exact=True).click()
                            page.get_by_role('button', name='Sign in to ATLAS', exact=True).wait_for()
                            assert denied == [], 'No external identity/provider/model/browser requests allowed'
                            context.close()
                    finally:
                        browser.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
