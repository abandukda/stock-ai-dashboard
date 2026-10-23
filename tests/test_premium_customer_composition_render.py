"""Chromium on extracted actual app dispatch; synthetic identities/evidence only."""
import os
from pathlib import Path
import socket, subprocess, sys, tempfile, time, unittest
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from tests.test_personal_account_ui import composition_script
from tests.test_premium_earnings_cache_render import _seed_generated_cache
from tests.test_premium_home_render import capture_complete_streamlit


class PremiumCustomerCompositionRender(unittest.TestCase):
    def test_invited_accounts_research_and_retained_earnings_at_three_sizes(self):
        target=Path('audit_results/premium_home/extracted_composition');target.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='atlas-extracted-composition-') as temporary:
            root=Path(temporary);_seed_generated_cache(root/'cache')
            for mode in ('available','pending'):
                source=composition_script(root/'private'/mode,root/'cache',cache_mode=mode)
                source=source.replace('import _atlas_composition_server_fixture as server', '''
from types import ModuleType
if '_atlas_composition_server_fixture' not in sys.modules:
 fixture=ModuleType('_atlas_composition_server_fixture')
 fixture.logged_in=False;fixture.subject='alice';fixture.revoked=False;fixture.expired=False
 sys.modules[fixture.__name__]=fixture
import _atlas_composition_server_fixture as server
''')
                source=source.replace("now=datetime(2026,10,23,tzinfo=timezone.utc)",'''if st.button('Fixture reset Alice'):
 server.logged_in=False;server.subject='alice';server.revoked=False;server.expired=False
 st.rerun()
if st.button('Fixture select Bob'):
 server.subject='bob'
 st.rerun()
if st.button('Fixture revoke session'):
 server.revoked=True
 st.rerun()
now=datetime(2026,10,23,tzinfo=timezone.utc)''')
                fixture=root/f'{mode}.py';fixture.write_text(source)
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                env=dict(os.environ,STREAMLIT_GLOBAL_DEVELOPMENT_MODE='false',
                    PYTHONPATH=os.pathsep.join(filter(None,[str(Path.cwd()),os.environ.get('PYTHONPATH')])),
                    ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',ATLAS_ALLOW_EXTERNAL_AI='false')
                with (target/f'GENERATED_{mode}_server.log').open('w') as log:
                    process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(fixture),
                        '--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true',
                        '--browser.gatherUsageStats=false','--theme.base=dark'],env=env,stdout=log,stderr=subprocess.STDOUT)
                    try:
                        deadline=time.monotonic()+30
                        while time.monotonic()<deadline:
                            self.assertIsNone(process.poll(),'Extracted app fixture exited')
                            with socket.socket() as probe:
                                if probe.connect_ex(('127.0.0.1',port))==0:break
                            time.sleep(.2)
                        else:self.fail('Extracted composition startup timed out')
                        with sync_playwright() as pw:
                            browser=pw.chromium.launch(headless=True)
                            try:
                                for width in (360,768,1440):
                                    context=browser.new_context(viewport={'width':width,'height':1000});external=[]
                                    def route(request):
                                        parsed=urlsplit(request.request.url)
                                        if parsed.hostname=='127.0.0.1' and parsed.port==port:request.continue_()
                                        else:external.append(request.request.url);request.abort()
                                    context.route('**/*',route);page=context.new_page()
                                    try:
                                        page.goto(f'http://127.0.0.1:{port}')
                                        page.get_by_role('button',name='Fixture reset Alice',exact=True).click()
                                        sign_in=page.get_by_role('button',name='Sign in to ATLAS',exact=True)
                                        sign_in.wait_for();sign_in.click()
                                        page.get_by_role('radio',name='Watchlist',exact=True).wait_for(state='attached')
                                        # Each viewport owns a fresh name; the test demonstrates real adapter persistence.
                                        name=page.get_by_label('Watchlist name',exact=True)
                                        if not name.is_visible():
                                            page.get_by_text('Create a watchlist',exact=True).click()
                                        name.fill(f'Alice composed {mode} {width}')
                                        page.get_by_role('button',name='Create watchlist',exact=True).click()
                                        page.get_by_label('Find a ticker or company',exact=True).fill('NVDA')
                                        page.get_by_label('Find a ticker or company',exact=True).press('Enter')
                                        page.get_by_role('button',name='Add ticker',exact=True).click()
                                        page.get_by_role('button',name='Open Research — NVDA',exact=True).click()
                                        page.get_by_role('textbox',name='Ticker',exact=True).wait_for()
                                        self.assertEqual(page.get_by_role('textbox',name='Ticker',exact=True).input_value(),'NVDA')
                                        authority=page.locator('[data-atlas-qa="research-production-authority"]')
                                        self.assertEqual(authority.get_attribute('data-atlas-ticker'),'NVDA')
                                        capture_complete_streamlit(page,target/f'GENERATED_NOT_PRODUCTION_{mode}_{width}_RESEARCH.png')
                                        page.locator('[data-testid="stRadio"]').get_by_text('Earnings',exact=True).click()
                                        page.get_by_role('button',name='Check available earnings calls',exact=True).click()
                                        page.get_by_role('button',name='Load verified call insights',exact=True).click()
                                        availability='AVAILABLE' if mode=='available' else 'PENDING'
                                        page.get_by_text(f'Transcript availability: AVAILABLE · AI summary availability: {availability}',exact=True).wait_for()
                                        self.assertIn('Source: EARNINGSCALL',page.inner_text('body'))
                                        if mode=='available':
                                            page.get_by_text('Revenue grew 10%.',exact=True).wait_for()
                                            page.get_by_text('Model:',exact=False).wait_for()
                                            marker=page.locator('[data-atlas-transcript-evidence-id]')
                                            marker.wait_for(state='attached')
                                            evidence=marker.get_attribute('data-atlas-transcript-evidence-id')
                                            self.assertTrue(evidence.startswith('TRANSCRIPT:GENERATED:CALL:'))
                                            page.get_by_text('Transcript evidence: '+evidence,exact=True).wait_for()
                                        else:
                                            page.get_by_text('The transcript is cached; a separately approved source-grounded AI summary is still pending.',exact=True).wait_for()
                                        marker=page.locator('[data-atlas-transcript-provider-calls]')
                                        self.assertEqual(marker.get_attribute('data-atlas-transcript-provider-calls'),'0')
                                        self.assertNotIn('PRIVATE GENERATED SOURCE',page.inner_text('body'))
                                        self.assertNotIn('GENERATED_PRIVATE_KEY_NEVER_DISPLAY',page.inner_text('body'))
                                        capture_complete_streamlit(page,target/f'GENERATED_NOT_PRODUCTION_{mode}_{width}_EARNINGS.png')
                                        page.locator('[data-testid="stRadio"]').get_by_text('Account',exact=True).click()
                                        page.get_by_role('button',name='Sign out',exact=True).click()
                                        page.get_by_role('button',name='Sign in to ATLAS',exact=True).wait_for()
                                        self.assertEqual(page.get_by_role('radio',name='Research',exact=True).count(),0)
                                        page.get_by_role('button',name='Fixture select Bob',exact=True).click()
                                        page.get_by_role('button',name='Sign in to ATLAS',exact=True).click()
                                        page.get_by_role('radio',name='Watchlist',exact=True).wait_for(state='attached')
                                        self.assertNotIn(f'Alice composed {mode} {width}',page.inner_text('body'))
                                        page.locator('[data-testid="stRadio"]').get_by_text('Research',exact=True).click()
                                        self.assertEqual(page.get_by_role('textbox',name='Ticker',exact=True).input_value(),'')
                                        self.assertEqual(page.locator('[data-atlas-qa="research-production-authority"]').count(),0)
                                        page.get_by_role('button',name='Fixture revoke session',exact=True).click()
                                        page.get_by_text('Your account session is unavailable.',exact=False).wait_for()
                                        self.assertEqual(page.get_by_role('radio',name='Research',exact=True).count(),0)
                                        self.assertEqual(page.get_by_role('textbox',name='Watchlist name',exact=True).count(),0)
                                        self.assertEqual(page.locator('[data-testid="stException"]').count(),0)
                                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                                        self.assertEqual(external,[])
                                    except Exception:
                                        capture_complete_streamlit(page,target/f'FAILED_{mode}_{width}.png')
                                        (target/f'FAILED_{mode}_{width}_DOM.html').write_text(page.content())
                                        raise
                                    finally:context.close()
                            finally:browser.close()
                    finally:
                        process.terminate()
                        try:process.wait(timeout=10)
                        except subprocess.TimeoutExpired:process.kill();process.wait()
