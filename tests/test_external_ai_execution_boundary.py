import sys
from types import SimpleNamespace
from services import ai_synthesis, ai_valuation_synthesis
from engines import ask_atlas_engine


def test_configured_key_alone_cannot_construct_a_paid_client(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','MOCK_ONLY_KEY')
    calls=[]
    def forbidden(**kwargs):
        calls.append('constructed')
        raise AssertionError('No paid client without authorization')
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=forbidden))
    assert ai_synthesis._call_llm([], 'deterministic')=='deterministic'
    assert ai_valuation_synthesis.synthesize_assumptions({}) is None
    assert not calls


def test_explicit_approved_path_can_be_validated_with_mock_transport(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','MOCK_ONLY_KEY')
    calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='source-grounded mock'))])
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=lambda **kwargs:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))))
    assert ai_synthesis._call_llm([], 'fallback',allow_external_ai=True)=='source-grounded mock'
    assert len(calls)==1


def test_ask_atlas_remains_deterministic_with_key_but_no_execution_approval(monkeypatch):
    from tests.test_atlas_vnext_ux3b_research_ask import _report
    monkeypatch.setattr(ask_atlas_engine,'llm_is_configured',lambda:True)
    def forbidden(*a,**kw):raise AssertionError('Model boundary crossed')
    monkeypatch.setattr(ask_atlas_engine,'answer_ticker_question',forbidden)
    result=ask_atlas_engine.ask_atlas('Give me the generic view',_report())
    assert result['answer_mode']=='deterministic'


def test_buy_now_key_alone_does_not_cross_paid_boundary(monkeypatch):
    import pytest
    from engines.buy_now_synthesis import configured_openai_generator
    monkeypatch.setenv('OPENAI_API_KEY', 'MOCK_ONLY_KEY')
    def forbidden(**kwargs):
        raise AssertionError('SDK must not be constructed')
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=forbidden))
    with pytest.raises(RuntimeError, match='EXTERNAL_AI_EXECUTION_NOT_AUTHORIZED'):
        configured_openai_generator({})


def test_buy_now_explicit_opt_in_uses_mock_transport(monkeypatch):
    from engines.buy_now_synthesis import configured_openai_generator
    monkeypatch.setenv('OPENAI_API_KEY', 'MOCK_ONLY_KEY')
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))))
    assert configured_openai_generator({}, allow_external_ai=True) == {}
    assert len(calls) == 1
