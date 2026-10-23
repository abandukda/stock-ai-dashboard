"""Actual synthetic snapshot browser renders; never production acceptance."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def test_immutable_zero_observation_report_card_at_three_sizes():
    from tests.test_report_card_immutable_visibility import snapshot
    target = Path('audit_results/premium_home/report_card_immutable')
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='atlas-synthetic-report-card-') as temporary:
        root = Path(temporary)
        path, digest, tip = snapshot(root)
        fixture = root / 'fixture.py'
        fixture.write_text('''from pathlib import Path
import streamlit as st
from ui.internal_report_card import render_internal_report_card
st.set_page_config(layout='wide')
st.caption('SYNTHETIC IMMUTABLE SNAPSHOT — NOT PRODUCTION OR GENUINE SIGNALS')
render_internal_report_card(Path(%r), authorized=True, snapshot_sha256=%r, snapshot_tip=%r)
st.markdown('<span data-fixture-complete="true"></span>', unsafe_allow_html=True)
''' % (str(path), digest, tip))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, (str(Path.cwd()), os.environ.get('PYTHONPATH','')))),
                   STREAMLIT_GLOBAL_DEVELOPMENT_MODE='false', ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',
                   ATLAS_ALLOW_EXTERNAL_AI='false', ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with (target/'fixture_server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(fixture),
                '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
                '--browser.gatherUsageStats=false', '--theme.base=dark'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    assert process.poll() is None
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1',port))==0: break
                    time.sleep(.2)
                else: raise AssertionError('Synthetic Report Card startup timeout')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    try:
                        for width in (360,768,1440):
                            context=browser.new_context(viewport={'width':width,'height':1000})
                            external=[]
                            def local_only(route):
                                parsed=urlsplit(route.request.url)
                                if parsed.hostname=='127.0.0.1' and parsed.port==port: route.continue_()
                                else: external.append(route.request.url); route.abort()
                            context.route('**/*',local_only)
                            page=context.new_page()
                            page.goto(f'http://127.0.0.1:{port}')
                            page.wait_for_selector('[data-fixture-complete="true"]',state='attached')
                            assert page.get_by_text('Performance is pending',exact=True).is_visible()
                            assert page.locator('[data-atlas-qa="report-card-overview"]').get_attribute('data-atlas-observation-count')=='0'
                            assert page.locator('[data-testid="stException"]').count()==0
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            page.screenshot(path=str(target/f'GENERATED_NOT_PRODUCTION_immutable_{width}.png'),full_page=True)
                            assert not external
                            context.close()
                    finally: browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
