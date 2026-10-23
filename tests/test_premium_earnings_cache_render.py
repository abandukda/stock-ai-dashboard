"""Actual Earnings renderer against TEMP generated cache; never production evidence."""
import os
from pathlib import Path
from PIL import Image
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from test_premium_home_render import capture_complete_streamlit


FIXTURE = r'''
from datetime import datetime, timezone
from pathlib import Path
import os, socket, hashlib
import streamlit as st
from services.transcript_cache_reader import ReadOnlyTranscriptCache
from services.transcript_evidence_store import TranscriptEvidenceStore
from services.transcript_provider import ConfiguredTranscriptProvider
import services.transcript_intelligence_runtime as runtime
from ui.earnings_vnext import _render_transcript_intelligence, _reported_card, _upcoming_card

st.set_page_config(layout='wide',page_title='Generated Earnings cache review')
st.warning('GENERATED FIXTURE — NOT PRODUCTION OR REAL TRANSCRIPT INTELLIGENCE')
now=datetime(2026,10,23,tzinfo=timezone.utc)
end=datetime(2026,12,31,tzinfo=timezone.utc)
mode=str(st.query_params.get('mode','pending'))
if mode not in {'pending','missing','default','available','literal'}: st.stop()
class Response:
    status_code=200
    def json(self):
        return {'id':'GENERATED:CALL','conference_date':'2026-07-20',
                'text':'PRIVATE GENERATED SOURCE: Revenue grew 10%. Margin pressure remains a risk.'}
def fixture_get(*args,**kwargs): return Response()
p=ConfiguredTranscriptProvider(api_key='GENERATED_PRIVATE_KEY_NEVER_DISPLAY',
    base_url='https://v2.api.earningscall.biz',provider_name='earningscall',
    license_state='COMMERCIAL_LICENSE_CONFIRMED',get=fixture_get)
root=Path(os.environ['ATLAS_GENERATED_CACHE_ROOT'])/mode
def forbidden(*args,**kwargs): raise AssertionError('Customer provider/model callback forbidden')
p.transcript=p.available_periods=forbidden
ConfiguredTranscriptProvider.transcript=ConfiguredTranscriptProvider.available_periods=forbidden
TranscriptEvidenceStore.__init__=forbidden
runtime.retrieve_and_summarize_transcript=forbidden
# Reject outbound sockets in fixture execution as well as browser external requests.
socket.socket.connect=forbidden
socket.create_connection=forbidden
reader=None if mode=='default' else ReadOnlyTranscriptCache(root,retention_until=end,
    provider=p,summary_revision='GENERATED_APPROVED_POLICY',clock=lambda:now)
if mode=='literal':
    prose='Revenue grew 10%. ![generated](https://example.invalid/earnings-pixel) [report](https://example.invalid/report) <img src="https://example.invalid/raw"> & detail'
    story={'ticker':'NVDA','company':prose,'event_identity':{'fiscal_period':'Q2 2026','report_date':'2026-07-20'},
        'what_happened':prose,'why_it_matters':[prose],'watch_next':[prose],
        'thesis_strengtheners':[prose],'thesis_weakeners':[prose],'thesis_invalidators':[prose],
        'limitations':[prose],'evidence_ids':[prose],
        'transcript_intelligence':{'semantic_status':'AVAILABLE','evidence_ids':[prose],
            'data':{'management_themes':[{'text':prose}],'supported_risks':[prose]}}}
    _reported_card(story,lambda ticker:None,0,cache_reader=reader)
    _upcoming_card(story,lambda ticker:None,0)
else:
    _render_transcript_intelligence({'ticker':'NVDA'},suffix='generated',cache_reader=reader)
st.markdown('<span data-fixture-complete="true">Generated cache fixture complete</span>',unsafe_allow_html=True)
'''


@patch('services.transcript_provider._now', return_value='2026-10-23T00:00:00+00:00')
def _seed_generated_cache(root, _capture_clock):
    """Create synthetic retained evidence before starting the read-only UI server."""
    from datetime import datetime, timezone
    import hashlib
    from services.transcript_evidence_store import TranscriptEvidenceStore
    from services.transcript_provider import ConfiguredTranscriptProvider
    class Response:
        status_code = 200
        def json(self):
            return {'id':'GENERATED:CALL','conference_date':'2026-07-20',
                    'text':'PRIVATE GENERATED SOURCE: Revenue grew 10%. Margin pressure remains a risk.'}
    provider = ConfiguredTranscriptProvider(api_key='GENERATED_PRIVATE_KEY_NEVER_DISPLAY',
        base_url='https://v2.api.earningscall.biz', provider_name='earningscall',
        license_state='COMMERCIAL_LICENSE_CONFIRMED', get=lambda *a, **k: Response())
    def generated_summary(_payload):
        claim='Revenue grew 10%.'
        return {'management_summary':{'claim':claim,'source_excerpt':claim,
            'source_excerpt_hash':hashlib.sha256(claim.encode()).hexdigest(),
            'claim_type':'PERFORMANCE'}}, 'GENERATED_MOCK_MODEL', 'v1'
    for mode in ('pending', 'missing', 'available', 'literal'):
        store = TranscriptEvidenceStore(root/mode,
            retention_until=datetime(2026,12,31,tzinfo=timezone.utc),
            clock=lambda:datetime(2026,10,23,tzinfo=timezone.utc))
        if mode != 'missing':
            selected_provider, selected_summary = provider, generated_summary
            if mode == 'literal':
                claim = 'Revenue grew 10%. ![generated](https://example.invalid/earnings-pixel) [report](https://example.invalid/report) <img src="https://example.invalid/raw"> & detail'
                class LiteralResponse:
                    status_code = 200
                    def json(self):
                        return {'id':'GENERATED:CALL','conference_date':'2026-07-20','text':claim}
                selected_provider = ConfiguredTranscriptProvider(api_key='GENERATED_PRIVATE_KEY_NEVER_DISPLAY',
                    base_url='https://v2.api.earningscall.biz', provider_name='earningscall',
                    license_state='COMMERCIAL_LICENSE_CONFIRMED', get=lambda *a,**k:LiteralResponse())
                def selected_summary(_payload):
                    return {'management_summary':{'claim':claim,'source_excerpt':claim,
                        'source_excerpt_hash':hashlib.sha256(claim.encode()).hexdigest(),
                        'claim_type':'PERFORMANCE'}, 'management_themes':[{'claim':claim,'source_excerpt':claim,
                        'source_excerpt_hash':hashlib.sha256(claim.encode()).hexdigest(),
                        'claim_type':'PERFORMANCE'}]}, 'GENERATED_MOCK_MODEL', 'v1'
            result = store.run('NVDA',year=2026,quarter=2,provider=selected_provider,
                acquisition_authorized=True,summary_authorized=mode in {'available','literal'},
                summarizer=selected_summary if mode in {'available','literal'} else None,
                summary_revision='GENERATED_APPROVED_POLICY')
            if mode == 'literal':
                assert result.insight is not None, 'Literal-source fixture must pass actual grounding'



class PremiumEarningsCacheRender(unittest.TestCase):
    def test_generated_retained_availability_at_three_viewports(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        target=Path('audit_results/premium_home/earnings_cache'); target.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='atlas-generated-earnings-') as temporary:
            root=Path(temporary); script=root/'fixture.py'; script.write_text(FIXTURE)
            _seed_generated_cache(root/'private')
            env=dict(os.environ,PYTHONPATH=os.pathsep.join(filter(None,[str(Path.cwd()),os.environ.get('PYTHONPATH')])),
                     ATLAS_GENERATED_CACHE_ROOT=str(root/'private'),ATLAS_QA_PROVIDER_CALLS_ALLOWED='0',
                     ATLAS_ALLOW_EXTERNAL_AI='false',ATLAS_CUSTOMER_REPORT_CARD_ENABLED='false')
            with (target/'GENERATED_fixture_server.log').open('w') as log:
                process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(script),
                    '--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true',
                    '--browser.gatherUsageStats=false','--theme.base=dark'],env=env,stdout=log,stderr=subprocess.STDOUT)
                try:
                    deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        if process.poll() is not None: self.fail('Generated Earnings fixture exited')
                        with socket.socket() as probe:
                            if probe.connect_ex(('127.0.0.1',port))==0: break
                        time.sleep(.2)
                    else: self.fail('Generated Earnings fixture startup timeout')
                    with sync_playwright() as pw:
                        browser=pw.chromium.launch(headless=True)
                        try:
                            for mode in ('pending','missing','default','available','literal'):
                                for width in (360,768,1440):
                                    context=browser.new_context(viewport={'width':width,'height':1000})
                                    external=[]
                                    def route(request_route):
                                        url=urlsplit(request_route.request.url)
                                        if url.hostname=='127.0.0.1' and url.port==port:
                                            request_route.continue_()
                                        else:
                                            external.append(request_route.request.url); request_route.abort()
                                    context.route('**/*',route)
                                    page=context.new_page()
                                    try:
                                        page.goto(f'http://127.0.0.1:{port}/?mode={mode}')
                                        page.wait_for_selector('[data-fixture-complete="true"]',timeout=30000)
                                        self.assertEqual(page.locator('[data-testid="stException"]').count(),0)
                                        check=page.get_by_role('button',name='Check available earnings calls',exact=True)
                                        if mode=='default':
                                            self.assertTrue(check.is_disabled())
                                            self.assertIn('Transcript availability: not connected · AI summary availability: pending',page.inner_text('body'))
                                        else:
                                            check.click()
                                            if mode in {'pending','available','literal'}:
                                                page.get_by_role('button',name='Load verified call insights',exact=True).click()
                                                if mode=='pending':
                                                    page.get_by_text('The transcript is cached; a separately approved source-grounded AI summary is still pending.',exact=True).wait_for()
                                                    self.assertIn('Transcript availability: AVAILABLE · AI summary availability: PENDING',page.inner_text('body'))
                                                else:
                                                    if mode == 'literal':
                                                        claim = 'Revenue grew 10%. ![generated](https://example.invalid/earnings-pixel) [report](https://example.invalid/report) <img src="https://example.invalid/raw"> & detail'
                                                        page.get_by_text('Cached AI summary of source-grounded earnings-call evidence',exact=True).wait_for()
                                                        page.get_by_text(claim,exact=True).first.wait_for(state='attached')
                                                        self.assertGreaterEqual(page.locator('.atlas-earnings-literal').count(),10)
                                                        self.assertEqual(page.locator('img[src*="example.invalid"], a[href*="example.invalid"]').count(),0)
                                                        self.assertGreaterEqual(page.locator('h3.atlas-earnings-literal').count(),2)
                                                        # Expand disclosure so literal thesis/limitation evidence is visibly exercised.
                                                        page.get_by_text('What Changes the Thesis',exact=True).click()
                                                        page.get_by_text('Deep Evidence',exact=True).click()
                                                        literal = page.locator('.atlas-earnings-literal').filter(has_text=claim).first
                                                        literal.scroll_into_view_if_needed()
                                                        self.assertTrue(literal.is_visible())
                                                    else:
                                                        page.get_by_text('Revenue grew 10%.',exact=True).wait_for()
                                                    self.assertIn('Transcript availability: AVAILABLE · AI summary availability: AVAILABLE',page.inner_text('body'))
                                                    if mode != 'literal':
                                                        self.assertIn('No transcript analysis is attached to this reported-quarter snapshot.',page.inner_text('body'))
                                                    self.assertNotIn('Transcript analysis unavailable',page.inner_text('body'))
                                                    self.assertIn('Selected call: Q2 2026',page.inner_text('body'))
                                                    self.assertIn('Analysis generated:',page.inner_text('body'))
                                                    self.assertIn('GENERATED_MOCK_MODEL',page.inner_text('body'))
                                                    evidence_marker = page.locator('[data-atlas-transcript-evidence-id]')
                                                    evidence_marker.wait_for(state='attached')
                                                    evidence_id = evidence_marker.get_attribute('data-atlas-transcript-evidence-id')
                                                    self.assertTrue(evidence_id.startswith('TRANSCRIPT:GENERATED:CALL:'))
                                                    page.get_by_text('Transcript evidence: ' + evidence_id, exact=True).wait_for(state='visible')
                                                    self.assertIn('Transcript evidence: ' + evidence_id,page.inner_text('body'))
                                                marker=page.locator('[data-atlas-transcript-provider-calls]')
                                                self.assertEqual(marker.get_attribute('data-atlas-transcript-provider-calls'),'0')
                                            else:
                                                page.get_by_text('Transcript availability: not cached · AI summary availability: pending',exact=True).wait_for()
                                        body=page.inner_text('body')
                                        self.assertIn('GENERATED FIXTURE',body)
                                        for private in ('PRIVATE GENERATED SOURCE','GENERATED_PRIVATE_KEY_NEVER_DISPLAY','Margin pressure remains a risk.','_cache_auth'):
                                            self.assertNotIn(private,body)
                                        self.assertEqual(page.locator('[data-testid="stException"]').count(),0)
                                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                                        self.assertFalse(external,'External browser requests were aborted: '+repr(external))
                                        saved_path = target/f'GENERATED_NOT_PRODUCTION_{mode}_{width}.png'
                                        capture_complete_streamlit(page,saved_path)
                                        if mode in {'default','missing'}:
                                            text = ('Transcript availability: not connected · AI summary availability: pending'
                                                    if mode == 'default' else 'Transcript availability: not cached · AI summary availability: pending')
                                            notice = page.get_by_text(text, exact=True).bounding_box()
                                            self.assertIsNotNone(notice)
                                            with Image.open(saved_path) as saved:
                                                self.assertGreaterEqual(saved.height, 1000)
                                                self.assertGreaterEqual(saved.height, notice['y'] + notice['height'])
                                    except Exception:
                                        page.screenshot(path=str(target/f'FAILED_{mode}_{width}.png'),full_page=True)
                                        (target/f'FAILED_{mode}_{width}_DOM.html').write_text(page.content())
                                        raise
                                    finally: context.close()
                        finally: browser.close()
                finally:
                    process.terminate()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
