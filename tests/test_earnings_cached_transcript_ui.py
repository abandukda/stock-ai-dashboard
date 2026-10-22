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
