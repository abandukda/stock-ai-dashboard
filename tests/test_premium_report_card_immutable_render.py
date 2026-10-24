"""Actual synthetic snapshot browser renders; never production acceptance."""
import os
import asyncio
import hashlib
import re
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
import pytest


@pytest.mark.parametrize('binding_route', [False, True])
def test_immutable_zero_observation_report_card_at_three_sizes(binding_route):
    from tests.test_report_card_immutable_visibility import snapshot
    target = Path('audit_results/premium_home/report_card_immutable')
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='atlas-synthetic-report-card-') as temporary:
        root = Path(temporary)
        path, digest, tip = snapshot(root)
        route_environment = {}
        if binding_route:
            from tests.test_report_card_snapshot_binding import synthetic_binding, environment
            source_root = root / 'route-source'
            source_root.mkdir()
            value = synthetic_binding(source_root)
            route_environment = environment(value)
        fixture = root / 'fixture.py'
        fixture.write_text('''from pathlib import Path
import streamlit as st
from ui.internal_report_card import render_internal_report_card
st.set_page_config(layout='wide')
st.caption('SYNTHETIC IMMUTABLE SNAPSHOT — NOT PRODUCTION OR GENUINE SIGNALS')
render_internal_report_card(Path(%r), authorized=True, snapshot_sha256=%r, snapshot_tip=%r)
st.markdown('<span data-fixture-complete="true"></span>', unsafe_allow_html=True)
''' % (str(path), digest, tip))
        if binding_route:
            fixture.write_text(fixture.read_text().replace(
                'from ui.internal_report_card import render_internal_report_card',
                'from ui.internal_report_card import render_internal_report_card_route').replace(
                'render_internal_report_card(Path(%r), authorized=True, snapshot_sha256=%r, snapshot_tip=%r)' % (str(path), digest, tip),
                'render_internal_report_card_route(None, authorized=True)'))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, (str(Path.cwd()), os.environ.get('PYTHONPATH','')))),
                   STREAMLIT_GLOBAL_DEVELOPMENT_MODE='false', ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',
                   ATLAS_ALLOW_EXTERNAL_AI='false', ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        env.update(route_environment)
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
                            page.screenshot(path=str(target/f'GENERATED_NOT_PRODUCTION_immutable_route_{binding_route}_{width}.png'),full_page=True)
                            assert not external
                            context.close()
                    finally: browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)


def test_original_cohort_selector_excludes_group_and_reopens_after_detail():
    """Actual compact Streamlit UI; twenty synthetic records, zero observations."""
    from tests.test_internal_report_card_dashboard import ledger, NOW
    from playwright.async_api import async_playwright
    from scripts.crawl_report_card_durable_ui import (
        original_cohort_signal_panels, wait_for_report_card_detail_state,
        wait_for_report_card_overview_settled,
    )
    target = Path('audit_results/premium_home/report_card_original_cohort')
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='atlas-generated-cohort-') as temporary:
        root = Path(temporary)
        item = ledger(root / 'generated-primary' / 'ledger.sqlite3')
        for index in range(18):
            identity, ticker = f'GENERATED-{index}', 'TEST' + chr(65 + index)
            item.append('SIGNAL', identity, dict(signal_id=identity,
                semantic_identity=identity, ticker=ticker, canonical_recommendation='BUY_NOW',
                first_seen_at=NOW.isoformat(), reference_price=None,
                withholding_status='CUSTOMER_PUBLISHABLE', candidate_digest='GENERATED',
                publication_digest='GENERATED', evaluation_snapshot_id='GENERATED',
                evidence_ids=['GENERATED_ONLY_NOT_FINANCIAL_EVIDENCE']), created_at=NOW)
        path = item.backup(root / 'generated-consolidated', now=NOW)
        digest, tip = hashlib.sha256(path.read_bytes()).hexdigest(), item.verify()
        fixture = root / 'fixture.py'
        fixture.write_text('''from pathlib import Path
import streamlit as st
from ui.internal_report_card import render_internal_report_card
st.set_page_config(layout='wide')
st.caption('TWENTY SYNTHETIC SIGNALS — NOT PRODUCTION OR FINANCIAL EVIDENCE')
render_internal_report_card(Path(%r), authorized=True, snapshot_sha256=%r, snapshot_tip=%r)
st.markdown('<span data-fixture-complete="true"></span>', unsafe_allow_html=True)
''' % (str(path), digest, tip))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None,
            (str(Path.cwd()), os.environ.get('PYTHONPATH', '')))),
            STREAMLIT_GLOBAL_DEVELOPMENT_MODE='false', ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',
            ATLAS_ALLOW_EXTERNAL_AI='false', ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
        with (target/'fixture_server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', str(fixture),
                '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
                '--browser.gatherUsageStats=false', '--theme.base=dark'],
                env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                async def browser_case():
                    async with async_playwright() as pw:
                        browser = await pw.chromium.launch(headless=True)
                        try:
                            for width in (360, 768, 1440):
                                context = await browser.new_context(viewport={'width':width,'height':1000})
                                external = []
                                async def local_only(route):
                                    parsed = urlsplit(route.request.url)
                                    if parsed.hostname == '127.0.0.1' and parsed.port == port:
                                        await route.continue_()
                                    else:
                                        external.append(route.request.url); await route.abort()
                                await context.route('**/*', local_only)
                                page = await context.new_page()
                                await page.goto(f'http://127.0.0.1:{port}')
                                await page.locator('[data-fixture-complete="true"]').wait_for(state='attached')
                                marker = page.locator('[data-atlas-qa="report-card-overview"]')
                                assert await marker.get_attribute('data-atlas-signal-count') == '20'
                                assert await marker.get_attribute('data-atlas-observation-count') == '0'
                                async def choose(label, option):
                                    await page.locator('[data-testid="stSelectbox"]').filter(
                                        has=page.get_by_text(label, exact=True)).get_by_role('combobox').click()
                                    await page.get_by_role('option', name=option, exact=True).click()
                                for horizon in (252, 5, 1):
                                    await choose('Comparison horizon', f'{horizon} trading sessions')
                                    await page.wait_for_function("""h => {
                                        const d = document.querySelector('[data-atlas-qa="report-card-benchmark-evidence"]')?.dataset;
                                        return d?.atlasBenchmarkStatus === 'PENDING' && d?.atlasBenchmarkHorizon === String(h);
                                    }""", arg=horizon)
                                    assert await page.locator('[data-testid="stPlotlyChart"]').count() == 0
                                await choose('History order', 'Ticker Z–A')
                                directory = page.locator('[data-atlas-qa="report-card-signal-directory"]')
                                await page.wait_for_function("""() => document.querySelector(
                                    '[data-atlas-qa="report-card-signal-directory"] tbody tr')?.dataset.atlasSignalId === 'GENERATED-17'""")
                                search = page.locator('[data-testid="stTextInput"]').filter(
                                    has=page.get_by_text('Search original signals', exact=True)).get_by_role('textbox')
                                await search.fill('not-a-signal')
                                await search.press('Enter')
                                await page.wait_for_function("""() => document.querySelector(
                                    '[data-atlas-qa="report-card-signal-directory"]')?.dataset.atlasSignalCount === '0'""")
                                await page.get_by_role('button', name='Open selected signal →', exact=True).wait_for(state='detached')
                                assert await page.get_by_role('button', name='Open selected signal →', exact=True).count() == 0
                                await search.fill('GENERATED-17')
                                await search.press('Enter')
                                await page.wait_for_function("""() => document.querySelector(
                                    '[data-atlas-qa="report-card-signal-directory"]')?.dataset.atlasSignalCount === '1'""")
                                assert await directory.locator('tbody tr').get_attribute('data-atlas-signal-id') == 'GENERATED-17'
                                await page.get_by_role('button', name='Open selected signal →', exact=True).click()
                                await wait_for_report_card_detail_state(page, str(width), 'GENERATED-17')
                                await page.get_by_role('button', name='← Back to Report Card', exact=True).click()
                                await wait_for_report_card_overview_settled(page, str(width))
                                await choose('Observation filter', 'Recorded')
                                await page.wait_for_function("""() => document.querySelector(
                                    '[data-atlas-qa="report-card-signal-directory"]')?.dataset.atlasSignalCount === '0'""")
                                await choose('Observation filter', 'All')
                                await choose('History order', 'Ledger order')
                                await page.wait_for_function("""() => document.querySelector(
                                    '[data-atlas-qa="report-card-signal-directory"]')?.dataset.atlasSignalCount === '20'""")
                                # Reproduce the actual defect: ancestor text also matches the old selector.
                                old = page.locator('[data-testid="stExpander"]').filter(
                                    has_text=re.compile(r' · [A-Z_]+ · \d+ observations'))
                                assert await old.count() == 21
                                panels = await original_cohort_signal_panels(page, str(width))
                                assert await panels.count() == 20
                                labels = [await panels.nth(i).locator('summary').inner_text() for i in range(20)]
                                assert all(' · BUY_NOW · 0 observations' in label for label in labels)
                                assert len(set(labels)) == 20
                                identities = []
                                for index in range(20):
                                    text = await panels.nth(index).text_content()
                                    identity = re.search(r'Signal ID:\s*([^\s]+)', text)
                                    assert identity is not None
                                    identities.append(identity.group(1))
                                assert set(identities) == {'AAA', 'BBB'} | {f'GENERATED-{i}' for i in range(18)}
                                assert len(identities) == len(set(identities)) == 20
                                last = panels.nth(19)
                                await last.locator('summary').click()
                                button = last.get_by_role('button', name='View Signal Digest →', exact=True)
                                await button.wait_for(state='visible')
                                await button.click()
                                await wait_for_report_card_detail_state(page, str(width), 'GENERATED-17')
                                await page.get_by_role('button', name='← Back to Report Card', exact=True).click()
                                await wait_for_report_card_overview_settled(page, str(width))
                                group = page.locator('[data-testid="stExpander"]').filter(
                                    has=page.get_by_text('Recommendation details', exact=True))
                                if await group.locator('details').first.get_attribute('open') is not None:
                                    await group.locator('summary').first.click()
                                assert await group.locator('details').first.get_attribute('open') is None
                                panels = await original_cohort_signal_panels(page, str(width))
                                assert await panels.count() == 20
                                assert await group.locator('details').first.get_attribute('open') is not None
                                assert await page.locator('[data-testid="stException"]').count() == 0
                                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                                assert not external
                                await page.screenshot(path=str(target/f'GENERATED_NOT_PRODUCTION_cohort_{width}.png'), full_page=True)
                                await context.close()
                        finally:
                            await browser.close()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    assert process.poll() is None
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1', port)) == 0: break
                    time.sleep(.2)
                else: raise AssertionError('Generated cohort startup timeout')
                asyncio.run(browser_case())
                assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
                assert not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-shm','-journal'))
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
