"""Customer callbacks use injected retained evidence, never acquisition/model APIs."""
import pytest
import ui.earnings_vnext as ui
from services.transcript_cache_reader import TranscriptCacheReadError


class Surface:
    def __init__(self): self.session_state = {}; self.output = []; self.buttons = []
    def markdown(self, value, **kwargs): self.output.append(str(value))
    caption = info = warning = write = markdown
    def button(self, label, **kwargs):
        self.buttons.append((label,kwargs))
        return not kwargs.get('disabled',False)
    def selectbox(self, label, labels, **kwargs): return labels[0]


class Cache:
    def __init__(self, status='PENDING'): self.calls=[]; self.status=status
    def period_index(self,ticker):
        self.calls.append(('index',ticker))
        return {'data':{'periods':[{'fiscal_year':2026,'fiscal_quarter':2}]}}
    def read(self,ticker,**kwargs):
        self.calls.append(('read',ticker,kwargs))
        return {'transcript_status':'AVAILABLE','ai_summary_status':self.status,
                'customer_projection':{'semantic_status':'AVAILABLE','management_summary':{'claim':'Approved cached analysis.'}},
                'cache_status':'READ_ONLY_HIT','provider_calls':0}


@pytest.fixture
def surface(monkeypatch):
    from services.transcript_provider import ConfiguredTranscriptProvider
    import services.transcript_intelligence_runtime as runtime
    def forbidden(*args,**kwargs): raise AssertionError('Customer interaction cannot acquire or generate')
    monkeypatch.setattr(ConfiguredTranscriptProvider,'transcript',forbidden)
    monkeypatch.setattr(ConfiguredTranscriptProvider,'available_periods',forbidden)
    monkeypatch.setattr(runtime,'retrieve_and_summarize_transcript',forbidden)
    screen=Surface(); monkeypatch.setattr(ui,'st',screen)
    return screen


def test_default_backend_is_unconfigured_and_disabled(surface):
    ui._render_transcript_intelligence({'ticker':'NVDA'},suffix='test')
    assert surface.buttons[-1][1]['disabled'] is True
    assert any('not connected' in line for line in surface.output)


@pytest.mark.parametrize('status',['PENDING','AVAILABLE'])
def test_buttons_only_read_injected_cache_and_distinguish_summary(surface,status):
    cache=Cache(status)
    ui._render_transcript_intelligence({'ticker':'NVDA'},suffix='test',cache_reader=cache)
    assert cache.calls == [('index','NVDA'),('read','NVDA',{'year':2026,'quarter':2})]
    assert surface.session_state['earnings-transcript-result-NVDA'] == (2026,2)
    assert all(not isinstance(value,dict) for value in surface.session_state.values())
    text=' '.join(surface.output)
    assert ('Approved cached analysis.' in text) == (status=='AVAILABLE')
    assert ('separately approved source-grounded AI summary is still pending' in text) == (status=='PENDING')


def test_account_change_revalidates_instead_of_reusing_session_projection(surface):
    ui._render_transcript_intelligence({'ticker':'NVDA'},suffix='test',cache_reader=Cache('AVAILABLE'))
    surface.output.clear()
    class WrongAccount(Cache):
        def period_index(self,ticker): return {'data':{'periods':[]}}
    ui._render_transcript_intelligence({'ticker':'NVDA'},suffix='test',cache_reader=WrongAccount())
    assert 'Approved cached analysis.' not in ' '.join(surface.output)
    assert any('not cached' in line for line in surface.output)


def test_corrupt_cache_never_falls_back_to_provider(surface):
    class Invalid(Cache):
        def read(self,*args,**kwargs): raise TranscriptCacheReadError('PRIVATE_ERROR')
    ui._render_transcript_intelligence({'ticker':'NVDA'},suffix='test',cache_reader=Invalid())
    assert any('could not be verified' in line for line in surface.output)
    assert 'PRIVATE_ERROR' not in ' '.join(surface.output)


def test_unsigned_legacy_cache_has_explicit_pending_revalidation(surface):
    class Legacy(Cache):
        def read(self,*args,**kwargs):
            raise TranscriptCacheReadError('TRANSCRIPT_CACHE_ACCOUNT_BINDING_REVALIDATION_REQUIRED')
    ui._render_transcript_intelligence({'ticker':'NVDA'},suffix='test',cache_reader=Legacy())
    assert any('pending offline account-binding revalidation' in line for line in surface.output)


def test_snapshot_unavailability_is_scoped_and_does_not_contradict_selected_call(surface):
    story = {'ticker': 'NVDA', 'event_identity': {'fiscal_period': 'Q3 2026',
             'report_date': '2026-10-20'}}
    ui._render_transcript_intelligence(story, suffix='separate-periods', cache_reader=Cache('AVAILABLE'))
    text = ' '.join(surface.output)
    assert 'Snapshot period: Q3 2026' in text
    assert 'Selected call: Q2 2026' in text
    assert 'No transcript analysis is attached to this reported-quarter snapshot.' in text
    assert 'Transcript analysis unavailable' not in text
    assert 'Approved cached analysis.' in text
    assert 'availability for one period does not establish availability for another' in text


def test_cached_analysis_provenance_uses_only_returned_metadata(surface):
    class DatedCache(Cache):
        def read(self, *args, **kwargs):
            value = super().read(*args, **kwargs)
            value.update(provider='EARNINGSCALL', capture_timestamp='2026-07-21T12:00:00Z')
            value['customer_projection'].update(generation_timestamp='2026-07-22T12:00:00Z',
                model_provider='GENERATED_MOCK_MODEL', model_version='review-v1')
            return value
    ui._render_transcript_intelligence({'ticker':'NVDA'}, suffix='dated', cache_reader=DatedCache('AVAILABLE'))
    text = ' '.join(surface.output)
    assert 'Source: EARNINGSCALL' in text
    assert 'Captured: Jul 21, 2026' in text
    assert 'Analysis generated: Jul 22, 2026' in text
    assert 'Model: GENERATED_MOCK_MODEL' in text and 'Version: review-v1' in text


def test_earnings_customer_changes_trigger_provider_free_browser_capture():
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load((root/'.github/workflows/atlas_premium_home_review.yml').read_text(), Loader=yaml.BaseLoader)
    paths = workflow['on']['pull_request']['paths']
    assert {'ui/earnings_vnext.py', 'tests/test_earnings_cached_transcript_ui.py',
            'tests/test_premium_earnings_cache_render.py'} <= set(paths)
    job = workflow['jobs']['provider-free-home-review']
    assert job['env']['ATLAS_QA_PROVIDER_CALLS_ALLOWED'] == '0'
    assert job['env']['ATLAS_ALLOW_EXTERNAL_AI'] == 'false'
    assert any('test_premium_*render.py' in step.get('run','') for step in job['steps'])


def test_grounded_claims_and_source_metadata_are_literal_not_markdown(surface):
    from copy import deepcopy
    from html import unescape
    from html.parser import HTMLParser
    import hashlib
    from services.transcript_intelligence_runtime import validate_grounded_summary
    text = 'Revenue grew 10%. ![source](https://example.invalid/pixel) [report](https://example.invalid/report) <img src=x> & detail\nNext line'
    grounded = {'claim': text, 'source_excerpt': text,
                'source_excerpt_hash': hashlib.sha256(text.encode()).hexdigest(), 'claim_type': 'PERFORMANCE'}
    assert validate_grounded_summary({'management_summary': grounded}, text)[0]
    story = {'ticker': 'NVDA', 'event_identity': {'fiscal_period': text},
             'transcript_intelligence': {'semantic_status': 'AVAILABLE', 'evidence_ids': [text],
                'data': {'management_themes': [{'text': text}], 'supported_risks': [text]}}}
    before = deepcopy(story)
    class LiteralCache(Cache):
        def read(self, *args, **kwargs):
            value = super().read(*args, **kwargs)
            value.update(provider=text, capture_timestamp=text, transcript_evidence_id=text)
            value['customer_projection'].update(management_summary={'claim': text},
                management_themes=[{'claim': text}], source_evidence_ids=[text],
                model_provider=text, model_version=text, generation_timestamp=text)
            return value
    ui._render_transcript_intelligence(story, suffix='literal', cache_reader=LiteralCache('AVAILABLE'))
    output = '\n'.join(surface.output)
    class Elements(HTMLParser):
        def __init__(self): super().__init__(); self.bad = []
        def handle_starttag(self, tag, attrs):
            if tag in {'img', 'a', 'script'} or any(k in {'src','href'} for k,v in attrs):
                self.bad.append((tag, attrs))
    parsed = Elements(); parsed.feed(output)
    assert parsed.bad == []
    assert text in unescape(output)
    assert 'white-space:pre-wrap' in output and 'overflow-wrap:anywhere' in output
    assert story == before
