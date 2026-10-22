from datetime import date, datetime, timezone
from collections import Counter
import json

import pytest

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.research_refresh_execution import (
    MAX_REQUESTS, compile_execution_plan, execute_live, rehearse, request_parameters,
)
from services.research_refresh_readiness import ALLOWED_CAPABILITIES, plan_research_refresh


NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def _plan(tickers, cache=None):
    return plan_research_refresh(
        tickers, cache or {}, {"status": "APPROVED", "contract_id": CONTRACT_ID,
                               "capabilities": list(ALLOWED_CAPABILITIES)},
        source_sha="a" * 40, now=NOW,
    )


def test_cold_cache_25_tickers_is_exactly_bounded_and_parameter_complete():
    compiled = compile_execution_plan(_plan([f"T{i:02d}" for i in range(25)]),
                                      as_of=date(2026, 10, 16))
    assert len(compiled["requests"]) == MAX_REQUESTS == 225
    counts = Counter(row["capability"] for row in compiled["requests"])
    assert counts == {
        "historical_ohlcv": 25, "splits": 25, "dividends": 25,
        "financial_statements": 25, "basic_financials": 25,
        "stock_earnings": 25, "recommendations": 25,
        "price_targets": 25, "company_news": 25,
    }
    assert {row["capability"] for row in compiled["deferred"]
            if row["reason"] == "DEFERRED_REQUEST_BUDGET"} == {
                "analyst_actions", "earnings_calendar",
            }
    assert compiled["limits"] == {"max_tickers": 25, "max_requests": 225,
                                   "concurrency": 1, "retries": 0}
    assert all(row["request_sha256"] for row in compiled["requests"])
    candle = next(row for row in compiled["requests"] if row["capability"] == "historical_ohlcv")
    assert candle["parameters"]["resolution"] == "D"
    assert isinstance(candle["parameters"]["from"], int)
    assert compiled["provider_calls"] == compiled["publication_writes"] == 0
    assert compiled["recommendation_authority"] == "UNCHANGED"


def test_cache_hits_release_budget_but_never_reacquire_fresh_family():
    cache = {"NVDA": {"historical_ohlcv": {
        "capture_timestamp": "2026-10-18T00:00:00Z", "integrity_verified": True,
    }}}
    compiled = compile_execution_plan(_plan(["NVDA"], cache), as_of=date(2026, 10, 18))
    capabilities = {row["capability"] for row in compiled["requests"]}
    assert "historical_ohlcv" not in capabilities
    assert {"financial_statements", "stock_earnings", "company_news"} <= capabilities


def test_rehearsal_is_raw_first_restart_safe_and_rejects_corrupt_receipt(tmp_path):
    compiled = compile_execution_plan(_plan(["NVDA"]), as_of=date(2026, 10, 18))
    first = rehearse(compiled, durable_root=tmp_path)
    second = rehearse(compiled, durable_root=tmp_path)
    assert first.completed == len(compiled["requests"])
    assert first.resumed == 0
    assert second.resumed == first.completed
    run = tmp_path / compiled["package_sha256"]
    assert len(list((run / "intents").glob("*.json"))) == first.completed
    assert len(list((run / "envelopes").glob("*.json"))) == first.completed
    receipt = sorted((run / "receipts").glob("*.json"))[0]
    value = json.loads(receipt.read_text())
    value["request_sha256"] = "bad"
    receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="RECEIPT_MISMATCH"):
        rehearse(compiled, durable_root=tmp_path)


def test_live_is_fail_closed_even_when_flag_is_set(monkeypatch):
    monkeypatch.delenv("ATLAS_RESEARCH_REFRESH_LIVE_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="LIVE_DISABLED"):
        execute_live()
    monkeypatch.setenv("ATLAS_RESEARCH_REFRESH_LIVE_ENABLED", "true")
    with pytest.raises(PermissionError, match="WORKFLOW_NOT_REGISTERED"):
        execute_live()


def test_scope_and_package_are_deterministic():
    first = compile_execution_plan(_plan(["MSFT", "NVDA"]), as_of=date(2026, 10, 18))
    second = compile_execution_plan(_plan(["NVDA", "MSFT"]), as_of=date(2026, 10, 18))
    assert first == second


def test_tampered_or_non_commit_upstream_identity_fails_closed():
    bad = _plan(["NVDA"])
    bad["requests"][0]["ticker"] = "MSFT"
    with pytest.raises(ValueError, match="PLAN_DIGEST"):
        compile_execution_plan(bad, as_of=date(2026, 10, 18))
    weak = _plan(["NVDA"])
    weak["source_sha"] = "branch-name"
    with pytest.raises(ValueError, match="SOURCE_SHA"):
        compile_execution_plan(weak, as_of=date(2026, 10, 18))


@pytest.mark.parametrize("session", [date(2026, 10, 21), date(2026, 10, 22)])
def test_history_interval_includes_completed_target_session(session):
    params = request_parameters("historical_ohlcv", "NVDA", as_of=session)
    start = int(datetime(session.year, session.month, session.day, tzinfo=timezone.utc).timestamp())
    assert params["to"] == start + 86400 - 1
    # Daily bars may retain provider timestamps later than midnight UTC.
    for offset in (0, 4 * 3600, 20 * 3600, 86399):
        assert params["from"] <= start + offset <= params["to"]
    assert start + 86400 > params["to"]
    assert request_parameters("splits", "NVDA", as_of=session)["to"] == session.isoformat()
    assert request_parameters("dividends", "NVDA", as_of=session)["to"] == session.isoformat()


def _resign_compiled(plan):
    import hashlib
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    plan['scope_sha256'] = digest({key: plan[key] for key in ('source_sha', 'as_of', 'requests', 'limits')})
    plan.pop('package_sha256', None)
    plan['package_sha256'] = digest(plan)
    return plan


def test_compiler_never_expands_a_narrower_owner_request_limit():
    from services.research_refresh_readiness import ResearchRefreshLimits
    upstream = plan_research_refresh(['NVDA'], {}, {
        'status': 'APPROVED', 'contract_id': CONTRACT_ID, 'capabilities': list(ALLOWED_CAPABILITIES),
    }, source_sha='a' * 40, now=NOW, limits=ResearchRefreshLimits(max_tickers=1, max_requests=9))
    compiled = compile_execution_plan(upstream, as_of=date(2026, 10, 16))
    assert compiled['limits']['max_requests'] == 9
    assert compiled['limits']['max_tickers'] == 1
    assert len(compiled['requests']) == 9
    assert {row['capability'] for row in compiled['deferred'] if row['reason'] == 'DEFERRED_REQUEST_BUDGET'} == {'analyst_actions', 'earnings_calendar'}


@pytest.mark.parametrize('mutation', ['parameters', 'path', 'ordinal', 'request_digest', 'scope'])
def test_rehearsal_checks_complete_package_before_any_writes(tmp_path, mutation):
    compiled = compile_execution_plan(_plan(['NVDA']), as_of=date(2026, 10, 16))
    if mutation == 'parameters':
        compiled['requests'][0]['parameters']['symbol'] = 'MSFT'
    elif mutation == 'path':
        compiled['package_sha256'] = '../escape'
    elif mutation == 'ordinal':
        compiled['requests'][0]['ordinal'] = 2
        _resign_compiled(compiled)
    elif mutation == 'request_digest':
        compiled['requests'][0]['request_sha256'] = '0' * 64
        _resign_compiled(compiled)
    else:
        compiled['scope_sha256'] = '0' * 64
        # Update package only; deliberately leave invalid scope.
        import hashlib
        compiled.pop('package_sha256')
        compiled['package_sha256'] = hashlib.sha256(json.dumps(compiled, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    with pytest.raises(ValueError, match='DIGEST_INVALID'):
        rehearse(compiled, durable_root=tmp_path / 'rehearsal')
    assert not (tmp_path / 'rehearsal').exists()
    assert not (tmp_path / 'escape').exists()


@pytest.mark.parametrize('mutation', ['missing_envelope', 'altered_envelope', 'missing_intent', 'altered_intent', 'nonterminal'])
def test_rehearsal_resume_requires_raw_intent_and_envelope_evidence(tmp_path, mutation):
    compiled = compile_execution_plan(_plan(['NVDA']), as_of=date(2026, 10, 16))
    rehearse(compiled, durable_root=tmp_path)
    run = tmp_path / compiled['package_sha256']
    if mutation == 'missing_envelope':
        (run / 'envelopes' / '0001.json').unlink()
    elif mutation == 'altered_envelope':
        (run / 'envelopes' / '0001.json').write_text('[]')
    elif mutation == 'missing_intent':
        (run / 'intents' / '0001.json').unlink()
    elif mutation == 'altered_intent':
        (run / 'intents' / '0001.json').write_text('{}')
    else:
        receipt = run / 'receipts' / '0001.json'
        value = json.loads(receipt.read_text()); value['terminal'] = False
        receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='RESUME_EVIDENCE_INVALID|RECEIPT_MISMATCH'):
        rehearse(compiled, durable_root=tmp_path)


def test_explicit_quote_profile_and_estimate_scope_is_60_requests_for_four_tickers():
    from services.research_refresh_readiness import SUPPORTED_CAPABILITIES, ResearchRefreshLimits
    selected = list(SUPPORTED_CAPABILITIES)
    upstream = plan_research_refresh(
        ['NVDA', 'MSFT', 'META', 'ANET'], {}, {
            'status': 'APPROVED', 'contract_id': CONTRACT_ID, 'capabilities': selected,
        }, source_sha='a' * 40, now=NOW, capabilities=selected,
        limits=ResearchRefreshLimits(max_tickers=4, max_requests=60),
    )
    compiled = compile_execution_plan(upstream, as_of=date(2026, 10, 22))
    assert len(compiled['requests']) == 60
    assert compiled['limits']['max_requests'] == 60
    assert Counter(row['capability'] for row in compiled['requests']) == {
        capability: 4 for capability in (*SUPPORTED_CAPABILITIES, 'splits', 'dividends')
    }
    endpoints = {row['capability']: row['endpoint'] for row in compiled['requests']}
    assert endpoints['live_quote'] == '/quote'
    assert endpoints['company_profile'] == '/stock/profile2'
    assert endpoints['revenue_estimates'] == '/stock/revenue-estimate'
    assert endpoints['eps_estimates'] == '/stock/eps-estimate'
    for row in compiled['requests']:
        if row['capability'] in {'revenue_estimates', 'eps_estimates'}:
            assert row['parameters'] == {'symbol': row['ticker'], 'freq': 'quarterly'}
    assert compiled['provider_calls'] == compiled['publication_writes'] == compiled['report_card_writes'] == 0


def test_explicit_quote_only_scope_does_not_add_historical_adjustment_requests():
    upstream = plan_research_refresh(['NVDA'], {}, {
        'status': 'APPROVED', 'contract_id': CONTRACT_ID, 'capabilities': ['live_quote'],
    }, source_sha='a' * 40, now=NOW, capabilities=['live_quote'])
    compiled = compile_execution_plan(upstream, as_of=date(2026, 10, 22))
    assert [row['capability'] for row in compiled['requests']] == ['live_quote']
    assert not compiled['deferred']
