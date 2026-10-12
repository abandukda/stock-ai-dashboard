from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.prospective_report_card import ProspectiveLedger
from services.report_card_observation_activation import apply_observation_bundle
from services.report_card_observation_producer import EVIDENCE_SCHEMA, build_observation_bundle


UTC = timezone.utc
ACTIVATION = datetime(2026, 10, 8, 21, 0, tzinfo=UTC)
CERTIFIED = datetime(2026, 10, 9, 21, 15, tzinfo=UTC)


def _ledger(path: Path) -> ProspectiveLedger:
    ledger = ProspectiveLedger(path)
    ledger.activate(activation_timestamp=ACTIVATION.isoformat(), now=ACTIVATION)
    for ticker, price in (("NVDA", 190.0), ("MSFT", 520.0)):
        signal_id = f"signal-{ticker.lower()}"
        ledger.append("SIGNAL", signal_id, {
            "signal_id": signal_id,
            "ticker": ticker,
            "reference_price": price,
            "first_seen_at": ACTIVATION.isoformat(),
            "executable_reference_timestamp": ACTIVATION.isoformat(),
        }, created_at=ACTIVATION)
    return ledger


def _instrument(ticker: str, close: float) -> dict:
    return {
        "data_status": "AVAILABLE",
        "closes": {"2026-10-09": close},
        "corporate_action_status": "NONE",
        "price_source": "GOVERNED_OFFICIAL_DAILY_CLOSE",
        "price_provenance": {
            "provider": "FINNHUB", "instrument": ticker,
            "as_of": "2026-10-09T20:00:00+00:00",
            "retrieved_at": "2026-10-09T20:15:00+00:00", "currency": "USD",
            "session_status": "FINALIZED_REGULAR_CLOSE",
        },
    }


def _evidence() -> dict:
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "captured_at": "2026-10-09T20:15:00+00:00",
        "session_open_at": "2026-10-09T13:30:00+00:00",
        "session_close_at": "2026-10-09T20:00:00+00:00",
        "session_status": "FINALIZED_REGULAR_CLOSE",
        "trading_calendar_source": "XNYS_GOVERNED_CALENDAR",
        "trading_calendar_version": "2026.10",
        "trading_sessions": ["2026-10-09"],
        "benchmark_references": {
            "signal-nvda": {"price": 680.0, "as_of": ACTIVATION.isoformat()},
            "signal-msft": {"price": 680.0, "as_of": ACTIVATION.isoformat()},
        },
        "instruments": {
            "NVDA": _instrument("NVDA", 195.0),
            "MSFT": _instrument("MSFT", 525.0),
            "SPY": _instrument("SPY", 685.0),
        },
    }


def test_deterministic_bundle_matches_consumer_schema_and_appends_atomically(tmp_path):
    ledger = _ledger(tmp_path / "primary" / "report-card.sqlite3")
    first = build_observation_bundle(ledger=ledger, evidence=_evidence(), horizon=1, certified_at=CERTIFIED)
    second = build_observation_bundle(ledger=ledger, evidence=_evidence(), horizon=1, certified_at=CERTIFIED)
    assert first == second
    assert first["provider_calls"] == 0
    assert [row["signal_id"] for row in first["records"]] == ["signal-nvda", "signal-msft"]
    result = apply_observation_bundle(
        ledger=ledger, backup_root=tmp_path / "backup", bundle=deepcopy(first), now=CERTIFIED,
    )
    assert result.appended == 2
    assert result.idempotent == 0
    replay = apply_observation_bundle(
        ledger=ledger, backup_root=tmp_path / "backup2", bundle={**deepcopy(first), "ledger_tip_before": ledger.verify()},
        now=CERTIFIED,
    )
    assert replay.appended == 0
    assert replay.idempotent == 2


def test_immature_horizon_fails_closed(tmp_path):
    ledger = _ledger(tmp_path / "primary" / "report-card.sqlite3")
    with pytest.raises(ValueError, match="OBSERVATION_HORIZON_IMMATURE"):
        build_observation_bundle(ledger=ledger, evidence=_evidence(), horizon=5, certified_at=CERTIFIED)


@pytest.mark.parametrize("mutation,code", [
    (lambda e: e.update(session_status="OPEN"), "MARKET_SESSION_NOT_FINALIZED"),
    (lambda e: e["instruments"]["NVDA"]["price_provenance"].update(instrument="MSFT"), "PRICE_TICKER_OWNERSHIP_MISMATCH"),
    (lambda e: e["benchmark_references"]["signal-nvda"].update(as_of="2026-10-09T20:00:00+00:00"), "BENCHMARK_REFERENCE_LOOKAHEAD"),
    (lambda e: e["instruments"]["NVDA"].update(price_source="LIVE_QUOTE"), "PRICE_SOURCE_INVALID"),
])
def test_integrity_failures(mutation, code, tmp_path):
    ledger = _ledger(tmp_path / "primary" / "report-card.sqlite3")
    evidence = _evidence(); mutation(evidence)
    with pytest.raises(ValueError, match=code):
        build_observation_bundle(ledger=ledger, evidence=evidence, horizon=1, certified_at=CERTIFIED)


def test_missing_and_delisted_are_explicit_not_zero(tmp_path):
    ledger = _ledger(tmp_path / "primary" / "report-card.sqlite3")
    evidence = _evidence()
    evidence["instruments"]["NVDA"].update(
        data_status="DELISTED", unavailable_reason="PROVIDER_CONFIRMED_DELISTED", closes={},
    )
    bundle = build_observation_bundle(ledger=ledger, evidence=evidence, horizon=1, certified_at=CERTIFIED)
    observation = bundle["records"][0]["observation"]
    assert observation["data_status"] == "DELISTED"
    assert observation["unavailable_reason"] == "PROVIDER_CONFIRMED_DELISTED"
    assert observation["observed_price"] is None
