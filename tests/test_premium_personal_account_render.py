"""Real Chromium on synthetic account shell; never production/login acceptance."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from tests.test_personal_account_ui import script


def test_generated_account_login_watchlist_logout_at_three_sizes():
    target=Path('audit_results/premium_home/personal_account')
    target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='atlas-account-render-') as temporary:
        root=Path(temporary)
        source=script(root/'private').replace(
            'import _atlas_account_server_fixture as server', '''
# Synthetic server fixture only, not a production identity authority.
import sys
from types import ModuleType
if '_atlas_account_server_fixture' not in sys.modules:
    fixture=ModuleType('_atlas_account_server_fixture')
    fixture.logged_in=False
    fixture.subject='alice'
    fixture.revoked=False
    fixture.navigated=None
    sys.modules[fixture.__name__]=fixture
import _atlas_account_server_fixture as server
st.caption('GENERATED SYNTHETIC ACCOUNT JOURNEY — NOT PRODUCTION')
''')
        fixture=root/'fixture.py';fixture.write_text(source)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env=dict(os.environ,STREAMLIT_GLOBAL_DEVELOPMENT_MODE='false',
            PYTHONPATH=os.pathsep.join(filter(None,(str(Path.cwd()),os.environ.get('PYTHONPATH','')))))
        with (target/'fixture_server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(fixture),
                '--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true',
                '--browser.gatherUsageStats=false','--theme.base=dark'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    assert process.poll() is None, 'synthetic app exited'
                    with socket.socket() as probe:
                        if probe.connect_ex(('127.0.0.1',port))==0: break
                    time.sleep(.2)
                else: raise AssertionError('synthetic app startup timeout')
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True)
                    try:
                        for width in (360,768,1440):
                            context=browser.new_context(viewport={'width':width,'height':1000})
                            requests=[]
                            def local_only(route):
                                parsed=urlsplit(route.request.url)
                                if parsed.hostname=='127.0.0.1' and parsed.port==port:
                                    route.continue_()
                                else:
                                    requests.append(route.request.url);route.abort()
                            context.route('**/*',local_only)
                            page=context.new_page()
                            page.goto(f'http://127.0.0.1:{port}')
                            page.get_by_role('button',name='Sign in to ATLAS',exact=True).wait_for()
                            page.screenshot(path=str(target/f'GENERATED_SIGN_IN_{width}.png'),full_page=True)
                            page.get_by_role('button',name='Sign in to ATLAS',exact=True).click()
                            page.locator('.atlas-personal-watchlist-head').wait_for()
                            if width==360:
                                page.get_by_label('Watchlist name',exact=True).fill('Personal research')
                                page.get_by_role('button',name='Create watchlist',exact=True).click()
                            page.locator('.atlas-personal-watchlist-name').filter(has_text='Personal research').wait_for()
                            assert page.locator('[data-testid="stException"]').count()==0
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                            page.screenshot(path=str(target/f'GENERATED_ACCOUNT_WORKSPACE_{width}.png'),full_page=True)
                            page.get_by_role('button',name='Sign out',exact=True).click()
                            page.get_by_role('button',name='Sign in to ATLAS',exact=True).wait_for()
                            assert page.locator('.atlas-personal-watchlist-name').count()==0
                            assert requests==[], 'no external identity/provider transport permitted'
                            context.close()
                    finally:
                        browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=5)
