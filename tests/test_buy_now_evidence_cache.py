import json

import pytest

from services.buy_now_evidence_cache import (
    ImmutableEvidenceCache, acquisition_disposition, classify_provider_outcome,
    plan_minimal_daily_requests,
)


def test_immutable_cache_survives_reopen_and_rejects_collision_and_corruption(tmp_path):
    request = {"ticker": "A", "endpoint": "/stock/candle", "session": "2026-10-15"}
    cache = ImmutableEvidenceCache(tmp_path)
    first = cache.persist(request_identity=request, envelope={"status": 200, "body_sha256": "a"*64},
        ticker="A", family="OHLCV", acquired_at="2026-10-16T00:00:00Z",
        finalized_sessions=["2026-10-15"], quality_status="AVAILABLE")
    assert first["status"] == "PERSISTED"
    assert ImmutableEvidenceCache(tmp_path).load(request)["ticker"] == "A"
    assert cache.persist(request_identity=request, envelope={"status": 200, "body_sha256": "a"*64},
        ticker="A", family="OHLCV", acquired_at="2026-10-16T00:00:00Z",
        finalized_sessions=["2026-10-15"], quality_status="AVAILABLE")["status"] == "CACHE_HIT"
    with pytest.raises(RuntimeError, match="IMMUTABLE_COLLISION"):
        cache.persist(request_identity=request, envelope={"status": 200, "body_sha256": "b"*64},
            ticker="A", family="OHLCV", acquired_at="2026-10-16T00:00:00Z",
            finalized_sessions=["2026-10-15"], quality_status="AVAILABLE")
    path = next((tmp_path/"objects").rglob("*.json"))
    value = json.loads(path.read_text()); value["quality_status"] = "CORRUPT"; path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="RECORD_CORRUPT"):
        ImmutableEvidenceCache(tmp_path).load(request)


@pytest.mark.parametrize(("status,payload,certain,expected"), [
    (200, {"s":"no_data"}, True, "TERMINAL_NO_DATA"),
    (429, {}, True, "RATE_LIMITED"), (403, {}, True, "ENTITLEMENT_FAILURE"),
    (503, {}, True, "TEMPORARY_PROVIDER_FAILURE"),
    (200, {"s":"ok","c":[]}, True, "MALFORMED_PAYLOAD"),
    (200, {}, False, "INDETERMINATE_TRANSPORT"),
])
def test_fault_classification(status, payload, certain, expected):
    assert classify_provider_outcome(endpoint="/stock/candle", status_code=status,
        payload=payload, transport_certain=certain) == expected


def test_minimal_daily_plan_reuses_complete_cache_and_refreshes_actions_only_when_stale():
    symbols = ["A", "B", "C"]
    plan = plan_minimal_daily_requests(symbols=symbols, finalized_session="2026-10-15",
        contiguous_session_by_ticker={"A":"2026-10-15", "B":"2026-10-14"},
        corporate_actions_fresh={"B":True})
    assert plan["requests"] == [{"ticker":"B", "endpoint":"/stock/candle",
        "from_session_exclusive":"2026-10-14", "to_session":"2026-10-15"}]
    assert plan["withheld"] == [{"ticker":"C", "reason":"CONTIGUOUS_HISTORY_UNAVAILABLE"}]
    stale = plan_minimal_daily_requests(symbols=["B"], finalized_session="2026-10-15",
        contiguous_session_by_ticker={"B":"2026-10-14"}, corporate_actions_fresh={"B":False})
    assert [row["endpoint"] for row in stale["requests"]] == [
        "/stock/candle", "/stock/split", "/stock/dividend"]


def test_daily_full_population_saves_two_thirds_when_action_cache_is_fresh():
    symbols = [f"S{i:04d}" for i in range(1298)]
    plan = plan_minimal_daily_requests(symbols=symbols, finalized_session="2026-10-15",
        contiguous_session_by_ticker={ticker:"2026-10-14" for ticker in symbols},
        corporate_actions_fresh={ticker:True for ticker in symbols})
    assert plan["request_count"] == 1298
    assert plan["withheld_count"] == 0
    assert 1 - plan["request_count"] / 3894 == pytest.approx(2/3)


def test_ticker_faults_are_isolated_but_systemic_and_indeterminate_stop_closed():
    isolated = acquisition_disposition({"A":"VALID_MARKET_DATA", "B":"TERMINAL_NO_DATA"})
    assert isolated["status"] == "CONTINUE_WITH_EXPLICIT_WITHHOLDING"
    assert isolated["accepted_tickers"] == ["A"] and isolated["withheld_tickers"] == ["B"]
    assert acquisition_disposition({"A":"RATE_LIMITED"})["status"] == "STOP_CLOSED"
    assert acquisition_disposition({"A":"INDETERMINATE_TRANSPORT"})["status"] == "STOP_CLOSED"
