"""Actual pending-state Streamlit renders; generated evidence, not production QA."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from playwright.sync_api import sync_playwright


class WorkspaceWatchlistBoundaryRender(unittest.TestCase):
    def test_shared_roles_never_render_private_symbols_or_edit_controls(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        output = Path('audit_results/watchlist_boundary')
        output.mkdir(parents=True, exist_ok=True)
        fixture_source = '''import streamlit as st
from ui.watchlist_vnext import render_watchlist_vnext
st.set_page_config(page_title="GENERATED WATCHLIST SECURITY QA", layout="wide")
role = st.query_params.get("fixture_role", "viewer")
st.session_state["authenticated"] = role != "unauthenticated"
st.session_state["role"] = role if role != "unauthenticated" else "admin"
st.session_state["user_role"] = st.session_state["role"]
st.markdown("### GENERATED WATCHLIST SECURITY QA — NOT PRODUCTION")
def forbidden(*args):
    raise AssertionError("Shared session crossed a private callback")
render_watchlist_vnext(None, ["PRIVATE_ALICE_SYMBOL"], open_research=forbidden,
    add_symbol=forbidden, remove_symbol=forbidden)
st.markdown('<span data-watchlist-fixture-complete="true"></span>', unsafe_allow_html=True)
'''
        env = {key: value for key, value in os.environ.items()
               if not key.endswith(('API_KEY', 'SECRET_KEY', 'ACCESS_TOKEN'))}
        env.update(PYTHONPATH=str(Path.cwd()) + os.pathsep + os.getenv('PYTHONPATH', ''),
                   ATLAS_QA_PROVIDER_CALLS_ALLOWED='0', ATLAS_ALLOW_EXTERNAL_AI='false',
                   ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with tempfile.TemporaryDirectory() as folder, (output / 'fixture_server.log').open('w') as log:
            fixture = Path(folder) / 'watchlist_boundary_fixture.py'
            fixture.write_text(fixture_source)
            process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(fixture),
                '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
                '--browser.gatherUsageStats=false', '--global.developmentMode=false', '--theme.base=dark'], env=env,
                stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        self.fail('Watchlist fixture exited before readiness')
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1', port)) == 0:
                            break
                    time.sleep(.2)
                else:
                    self.fail('Watchlist fixture startup timed out')
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    try:
                        base = f'http://127.0.0.1:{port}'
                        for width in (360, 768, 1440):
                            for role in ('viewer', 'beta', 'unauthenticated'):
                                with self.subTest(width=width, role=role):
                                    page = browser.new_page(viewport={'width': width, 'height': 850})
                                    page.route('**/*', lambda route: route.continue_()
                                               if route.request.url.startswith(base + '/') else route.abort())
                                    page.goto(base + '/?fixture_role=' + role)
                                    page.wait_for_selector('[data-watchlist-fixture-complete="true"]', state='attached')
                                    self.assertEqual(page.locator('[data-atlas-qa="watchlist-access-pending"]').count(), 1)
                                    self.assertEqual(page.locator('[data-atlas-qa="watchlist-certified-authority"]').count(), 0)
                                    self.assertEqual(page.get_by_label('Add ticker', exact=True).count(), 0)
                                    self.assertEqual(page.get_by_role('button', name='Add', exact=True).count(), 0)
                                    self.assertNotIn('PRIVATE_ALICE_SYMBOL', page.locator('body').inner_text())
                                    self.assertTrue(page.get_by_text('Shared-password sessions cannot read or edit', exact=False).is_visible())
                                    self.assertEqual(page.locator('[data-testid="stException"]').count(), 0)
                                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width + 1)
                                    page.screenshot(path=str(output / f'GENERATED_WATCHLIST_DENIED_{role}_{width}.png'), full_page=True)
                                    page.close()
                    finally:
                        browser.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    unittest.main()
