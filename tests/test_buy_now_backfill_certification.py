import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json

from services.buy_now_backfill_certification import (
    build_certification_inputs, combine_backfill_observations,
)
from services.buy_now_history_backfill_execution import atomic_json, digest


def _plan():
    sessions = ["2026-10-05", "2026-10-06"]
    requests = []
    for ticker in ("AAA", "QRVO"):
        for capability, endpoint in (
            ("historical_ohlcv", "/stock/candle"),
            ("splits", "/stock/split"), ("dividends", "/stock/dividend"),
        ):
            requests.append({"ordinal": len(requests) + 1, "ticker": ticker,
                             "capability": capability, "endpoint": endpoint})
    symbols = ["AAA", "QRVO"]
    membership_sha = hashlib.sha256(
        json.dumps(symbols, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "requests": requests, "request_keys": [f"{r['ticker']}:{r['capability']}:x" for r in requests],
        "missing_sessions": sessions, "range_end": sessions[-1],
        "membership_identity": {"tickers": symbols, "membership_count": 2,
                                "membership_sha256": membership_sha},
    }


def _write(root, request, body):
    encoded = json.dumps(body, separators=(",", ":")).encode()
    atomic_json(root / f"{request['ordinal']:05d}.json", {
        "ordinal": request["ordinal"], "request_sha256": digest(request),
        "status_code": 200, "headers": {},
        "body_base64": base64.b64encode(encoded).decode(),
        "body_sha256": hashlib.sha256(encoded).hexdigest(),
    })


def test_combines_original_and_recovery_once_and_preserves_terminal_unavailable(tmp_path):
    plan = _plan(); original = tmp_path / "original"; recovery = tmp_path / "recovery"
    timestamps = [int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
                  for s in plan["missing_sessions"]]
    for request in plan["requests"]:
        root = original if request["ordinal"] <= 3 else recovery
        if request["endpoint"] == "/stock/candle":
            body = ({"s": "no_data"} if request["ticker"] == "QRVO" else
                    {"s": "ok", "t": timestamps, "o": [1, 2], "h": [2, 3],
                     "l": [1, 2], "c": [2, 3], "v": [10, 11]})
        else:
            body = []
        _write(root, request, body)
    observations, unavailable, report = combine_backfill_observations(
        plan=plan, original_raw_dir=original, recovery_raw_dir=recovery,
    )
    assert list(observations) == ["AAA"]
    assert unavailable["QRVO"]["reason"] == "FINNHUB_NO_DATA"
    assert report["combined_request_count"] == 6
    assert report["available_ticker_count"] == 1
    assert report["unavailable_ticker_count"] == 1


def test_partial_candle_session_coverage_is_explicitly_withheld(tmp_path):
    plan = _plan(); original = tmp_path / "original"; recovery = tmp_path / "recovery"
    timestamps = [int(datetime.fromisoformat(plan["missing_sessions"][0]).replace(
        tzinfo=timezone.utc).timestamp())]
    for request in plan["requests"]:
        root = original if request["ordinal"] <= 3 else recovery
        if request["endpoint"] == "/stock/candle":
            body = ({"s": "no_data"} if request["ticker"] == "QRVO" else
                    {"s": "ok", "t": timestamps, "o": [1], "h": [2],
                     "l": [1], "c": [2], "v": [10]})
        else:
            body = []
        _write(root, request, body)
    observations, unavailable, report = combine_backfill_observations(
        plan=plan, original_raw_dir=original, recovery_raw_dir=recovery,
    )
    assert observations == {}
    assert unavailable["AAA"]["reason"] == "FINNHUB_PARTIAL_SESSION_COVERAGE"
    assert unavailable["AAA"]["missing_sessions"] == ["2026-10-06"]
    assert report["unavailable_ticker_count"] == 2


def test_unexpected_candle_session_still_fails_closed(tmp_path):
    plan = _plan(); original = tmp_path / "original"; recovery = tmp_path / "recovery"
    unexpected = int(datetime(2026, 10, 7, tzinfo=timezone.utc).timestamp())
    for request in plan["requests"]:
        root = original if request["ordinal"] <= 3 else recovery
        body = ({"s": "ok", "t": [unexpected], "o": [1], "h": [2], "l": [1],
                 "c": [2], "v": [10]} if request["endpoint"] == "/stock/candle" else [])
        _write(root, request, body)
    import pytest
    with pytest.raises(ValueError, match="BACKFILL_COMBINED_SESSION_SET_INVALID:AAA"):
        combine_backfill_observations(
            plan=plan, original_raw_dir=original, recovery_raw_dir=recovery,
        )


def test_certification_inputs_append_sessions_and_withhold_no_data():
    plan = _plan()
    retained_rows = [{"ticker": symbol, "current_price": 1.0} for symbol in ("AAA", "QRVO")]
    end = datetime(2026, 10, 2, tzinfo=timezone.utc)
    histories = {symbol: [{
        "symbol": symbol, "timestamp": (end - timedelta(days=220-index)).isoformat(),
        "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100,
        "completed": True,
    } for index in range(221)] for symbol in ("AAA", "QRVO")}
    observations = {"AAA": [{"session": session, "open": 1, "high": 2, "low": 1,
                              "close": 1.6, "volume": 100,
                              "raw_response_sha256": "a" * 64,
                              "corporate_action_status": "NONE"}
                             for session in plan["missing_sessions"]]}
    cert_plan, checkpoint, records = build_certification_inputs(
        backfill_plan=plan, retained_rows=retained_rows, retained_histories=histories,
        observations=observations,
        unavailable={"QRVO": {"reason": "FINNHUB_NO_DATA"}},
    )
    by_symbol = {record["ticker"]: record for record in records}
    assert len(by_symbol["AAA"]["bars"]) == 223
    assert len(by_symbol["QRVO"]["bars"]) == 221
    assert by_symbol["QRVO"]["blockers"] == ["BACKFILL_TERMINAL_FINNHUB_NO_DATA"]
    assert len(checkpoint["receipts"]) == 4
    assert cert_plan["session"] == "2026-10-06"
