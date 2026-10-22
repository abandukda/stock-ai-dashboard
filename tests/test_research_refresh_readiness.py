from datetime import datetime, timezone

import pytest

from services.finnhub_enterprise_display_contract import CONTRACT_ID
from services.research_refresh_readiness import (
    ALLOWED_CAPABILITIES, ResearchRefreshLimits, assert_zero_call_preflight,
    plan_research_refresh,
)


NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def _entitlement(*capabilities):
    return {"status": "APPROVED", "contract_id": CONTRACT_ID, "capabilities": list(capabilities)}


def test_plan_is_cache_first_deterministic_bounded_and_transport_free():
    cache = {"NVDA": {
        "historical_ohlcv": {"capture_timestamp": "2026-10-17T20:00:00Z", "integrity_verified": True},
        "company_news": {"capture_timestamp": "2026-10-17T20:00:00Z", "integrity_verified": True},
    }}
    kwargs = dict(
        tickers=["NVDA", "MSFT", "NVDA"], cache_index=cache,
        entitlement=_entitlement(*ALLOWED_CAPABILITIES), source_sha="a" * 40, now=NOW,
    )
    first = plan_research_refresh(**kwargs)
    second = plan_research_refresh(**kwargs)
    assert first == second
    assert first["provider_calls"] == 0
    assert first["mode"] == "PLAN_ONLY_TRANSPORT_DISABLED"
    assert first["authorization_consumed"] is False
    assert first["limits"] == {"max_tickers": 25, "max_requests": 225, "concurrency": 1, "retries": 0}
    assert {row["ticker"] for row in first["requests"]} == {"MSFT", "NVDA"}
    assert {tuple(row.values()) for row in first["retained_fresh"]} == {("NVDA", "historical_ohlcv")}
    assert_zero_call_preflight(first)


def test_unentitled_families_are_explicitly_unavailable_not_planned():
    plan = plan_research_refresh(
        ["NVDA"], {}, _entitlement("historical_ohlcv"), source_sha="b" * 40, now=NOW,
    )
    assert [row["capability"] for row in plan["requests"]] == ["historical_ohlcv"]
    assert len(plan["unavailable"]) == len(ALLOWED_CAPABILITIES) - 1
    assert {row["reason"] for row in plan["unavailable"]} == {"NOT_ENTITLED"}


def test_stale_future_or_unverified_cache_never_suppresses_request():
    cache = {"NVDA": {
        "historical_ohlcv": {"capture_timestamp": "2026-01-01T00:00:00Z", "integrity_verified": True},
        "basic_financials": {"capture_timestamp": "2026-10-19T00:00:00Z", "integrity_verified": True},
        "stock_earnings": {"capture_timestamp": "2026-10-18T11:00:00Z", "integrity_verified": False},
    }}
    plan = plan_research_refresh(
        ["NVDA"], cache, _entitlement(*ALLOWED_CAPABILITIES), source_sha="c" * 40, now=NOW,
    )
    planned = {row["capability"] for row in plan["requests"]}
    assert {"historical_ohlcv", "basic_financials", "stock_earnings"} <= planned


def test_invalid_entitlement_scope_and_preflight_fail_closed():
    with pytest.raises(ValueError, match="ENTITLEMENT"):
        plan_research_refresh(["NVDA"], {}, {"status": "APPROVED", "contract_id": "wrong"}, source_sha="d", now=NOW)
    with pytest.raises(ValueError, match="SCOPE"):
        plan_research_refresh(
            [f"T{i}" for i in range(26)], {}, _entitlement(*ALLOWED_CAPABILITIES), source_sha="d", now=NOW,
        )
    with pytest.raises(ValueError, match="PREFLIGHT"):
        assert_zero_call_preflight({"schema": "wrong"})


def test_request_ceiling_is_hard_and_checked_before_any_transport():
    with pytest.raises(ValueError, match="CEILING"):
        plan_research_refresh(
            ["NVDA", "MSFT"], {}, _entitlement(*ALLOWED_CAPABILITIES), source_sha="e", now=NOW,
            limits=ResearchRefreshLimits(max_tickers=2, max_requests=1),
        )
    for limits in (
        ResearchRefreshLimits(max_requests=226),
        ResearchRefreshLimits(max_tickers=26),
        ResearchRefreshLimits(concurrency=2),
        ResearchRefreshLimits(retries=1),
    ):
        with pytest.raises(ValueError, match="SCOPE"):
            plan_research_refresh(
                ["NVDA"], {}, _entitlement(*ALLOWED_CAPABILITIES),
                source_sha="e", now=NOW, limits=limits,
            )


def test_new_endpoint_families_require_explicit_selection_and_entitlement():
    from services.research_refresh_readiness import SUPPORTED_CAPABILITIES
    entitled = _entitlement(*SUPPORTED_CAPABILITIES)
    default = plan_research_refresh(['NVDA'], {}, entitled, source_sha='a' * 40, now=NOW)
    assert {row['capability'] for row in default['requests']} == set(ALLOWED_CAPABILITIES)
    selected = plan_research_refresh(['NVDA'], {}, entitled, source_sha='a' * 40, now=NOW,
                                    capabilities=['eps_estimates', 'live_quote'])
    assert [row['capability'] for row in selected['requests']] == ['live_quote', 'eps_estimates']
    assert selected['scope_sha256'] != default['scope_sha256']
    unentitled = plan_research_refresh(['NVDA'], {}, _entitlement(), source_sha='a' * 40, now=NOW,
                                      capabilities=['live_quote'])
    assert unentitled['requests'] == []
    assert unentitled['unavailable'] == [{'ticker': 'NVDA', 'capability': 'live_quote', 'reason': 'NOT_ENTITLED'}]


@pytest.mark.parametrize('selection', [['unknown'], ['live_quote', 'live_quote'], [], [True], 'live_quote'])
def test_invalid_explicit_capability_scope_is_rejected(selection):
    with pytest.raises(ValueError, match='CAPABILITY_INVALID'):
        plan_research_refresh(['NVDA'], {}, _entitlement(*ALLOWED_CAPABILITIES), source_sha='a' * 40,
                              now=NOW, capabilities=selection)


def test_new_cache_family_freshness_is_bounded_and_naive_clock_rejected():
    cache = {'NVDA': {'live_quote': {'capture_timestamp': '2026-10-18T11:59:00Z', 'integrity_verified': True}}}
    kwargs = dict(tickers=['NVDA'], cache_index=cache, entitlement=_entitlement('live_quote'),
                  source_sha='a' * 40, capabilities=['live_quote'])
    assert plan_research_refresh(now=NOW, **kwargs)['retained_fresh']
    cache['NVDA']['live_quote']['capture_timestamp'] = '2026-10-18T11:58:59Z'
    assert plan_research_refresh(now=NOW, **kwargs)['requests'][0]['capability'] == 'live_quote'
    with pytest.raises(ValueError, match='TIMEZONE_REQUIRED'):
        plan_research_refresh(now=NOW.replace(tzinfo=None), **kwargs)
