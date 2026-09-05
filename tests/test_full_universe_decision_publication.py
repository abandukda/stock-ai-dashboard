from datetime import datetime, timedelta, timezone

from services.full_universe_decision_publication import acquire_full_universe_decisions, publish_evaluations
from engines.home_guidance_story_v1 import build_home_guidance_candidate


NOW = datetime(2026, 9, 5, 22, 0, tzinfo=timezone.utc)


class Response:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): return None
    def json(self): return self.payload


def daily(symbol, count=220):
    start = NOW.date() - timedelta(days=count + 2)
    values = []
    for index in range(count):
        price = 80 + index * .1
        values.append({"datetime": str(start + timedelta(days=index)), "open": price - .2,
                       "high": price + .5, "low": price - .5, "close": price,
                       "volume": 1_000_000 + index * 100})
    return {"meta": {"symbol": symbol, "exchange_timezone": "America/New_York"}, "values": list(reversed(values))}


def row(symbol):
    return {"ticker": symbol, "price": 100, "entry_low": 95, "entry_high": 105,
            "stop_loss": 90, "target_1": 125, "risk_reward": 2,
            "forward_eps": 6, "revenue_growth": 10, "operating_profit_margin": 20,
            "forward_revenue": 1000,
            "drawdown_label": "Moderate drawdown"}


def getter(url, *, params, **kwargs):
    symbol = params["symbol"]
    if url.endswith("/time_series"):
        return Response(daily(symbol))
    if url.endswith("/statistics"):
        return Response({"statistics": {"financials": {
            "operating_margin": .20,
            "income_statement": {"quarterly_revenue_growth": .10, "quarterly_earnings_growth_yoy": .12},
            "balance_sheet": {"current_ratio_mrq": 1.5},
            "cash_flow": {"levered_free_cash_flow_ttm": 1000, "operating_cash_flow_ttm": 1200},
        }}})
    raise AssertionError(url)


def test_full_universe_publication_uses_engine_history_and_preserves_order():
    rows = [row("AAA"), row("BBB")]
    result = acquire_full_universe_decisions(
        rows, get=getter, secrets={"TWELVE_DATA_API_KEY": "secret", "TWELVE_DATA_ENABLED": "true", "ATLAS_DATA_MODE": "INTERNAL_TRIAL"},
        environ={}, now=NOW,
    )
    assert result["provider_calls"] == 4
    assert result["technical_history_successes"] == 2
    for symbol in ("AAA", "BBB"):
        evaluation = result["evaluations"][symbol]
        assert evaluation["technical_quality"]["score"] == evaluation["technical_confirmation"]["score"]
        assert evaluation["technical_quality"]["score"] is not None
        assert evaluation["technical_confirmation"]["fingerprint"]
        assert evaluation["decision_metrics_methodology"] == "ATLAS_DECISION_METRICS_V1"
        assert evaluation["fundamental_quality"]["status"] == "AVAILABLE"
        assert evaluation["guidance"]["policy_version"] == "HOME_MULTI_THESIS_ACTION_V1"
        assert evaluation["opportunity_thesis"] == evaluation["guidance"]["opportunity_thesis"]
    published = publish_evaluations(rows, result)
    assert [item["ticker"] for item in published] == ["AAA", "BBB"]
    assert all("canonical_investment_evaluation" in item for item in published)
    assert all((item["canonical_investment_evaluation"].get("guidance") or {}).get("policy_version") == "HOME_MULTI_THESIS_ACTION_V1" for item in published)
    home = build_home_guidance_candidate(published[0], production_rank=1)
    assert home["opportunity"] == result["evaluations"]["AAA"]["opportunity"]
    assert home["decision_confidence"] == result["evaluations"]["AAA"]["decision_confidence"]


def test_flag_off_makes_zero_calls_and_does_not_publish():
    calls = []
    rows = [row("AAA")]
    result = acquire_full_universe_decisions(
        rows, get=lambda *a, **k: calls.append((a, k)),
        secrets={"TWELVE_DATA_API_KEY": "secret", "TWELVE_DATA_ENABLED": "false", "ATLAS_DATA_MODE": "INTERNAL_TRIAL"},
        environ={}, now=NOW,
    )
    assert result["status"] == "DISABLED" and result["provider_calls"] == 0 and calls == []
    assert publish_evaluations(rows, result) == rows


def test_one_bad_history_fails_closed_only_for_that_ticker():
    def mixed(url, *, params, **kwargs):
        if url.endswith("/time_series") and params["symbol"] == "BAD":
            return Response({"meta": {"symbol": "BAD"}, "values": []})
        return getter(url, params=params, **kwargs)
    result = acquire_full_universe_decisions(
        [row("GOOD"), row("BAD")], get=mixed,
        secrets={"TWELVE_DATA_API_KEY": "secret", "TWELVE_DATA_ENABLED": "true", "ATLAS_DATA_MODE": "INTERNAL_TRIAL"},
        environ={}, now=NOW,
    )
    assert result["evaluations"]["GOOD"]["technical_quality"]["score"] is not None
    assert result["evaluations"]["BAD"]["technical_quality"]["score"] is None
    assert result["evaluations"]["BAD"]["guidance"]["state"] == "DATA_LIMITED"
