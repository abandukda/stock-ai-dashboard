from datetime import datetime, timezone
import hashlib
from pathlib import Path

import pytest

from services.report_card_daily_cycle import verify_alert_sink
from services.prospective_report_card import ProspectiveLedger
from services.report_card_daily_cycle import run_daily_cycle
from services.report_card_exchange_calendar import build_xnys_calendar
from services.report_card_market_evidence_acquisition import (
    AUTHORIZATION_TOKEN, PLAN_AUTHORIZATION_TOKEN, build_acquisition_plan,
)


def test_alert_health_probe_is_verified_and_removed(tmp_path):
    root = tmp_path / "alerts"
    verify_alert_sink(root)
    assert root.is_dir()
    assert list(root.iterdir()) == []


def test_alert_health_failure_stops_before_operation(tmp_path, monkeypatch):
    root = tmp_path / "alerts"
    root.mkdir()
    monkeypatch.setattr(Path, "write_text", lambda *args, **kwargs: 0)
    with pytest.raises(RuntimeError, match="ALERT_HEALTH_CHECK_FAILED"):
        verify_alert_sink(root)


class RetainedHistoryProvider:
    def __init__(self, sessions):
        self.sessions = sessions
        self.calls = []

    def fetch(self, capability, symbol, **parameters):
        self.calls.append((capability, symbol))
        provenance = {
            "certification_status": "CERTIFIED",
            "raw_evidence_id": f"fixture:{capability}:{symbol}",
            "content_hash": hashlib.sha256(f"{capability}:{symbol}".encode()).hexdigest(),
        }
        if capability == "historical_ohlcv":
            payload = {
                "timestamps": [datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() for day in self.sessions],
                "close": [100.0 + index for index, _ in enumerate(self.sessions)],
                "completed_session_flags": [True] * len(self.sessions),
            }
        else:
            payload = {"corporate_actions": []}
        return {"provenance": provenance, "payload": payload}


def test_daily_cycle_deduplicates_requests_and_appends_missed_horizons_in_order(tmp_path):
    activated = datetime(2026, 10, 8, 21, 0, tzinfo=timezone.utc)
    now = datetime(2026, 10, 15, 21, 0, tzinfo=timezone.utc)
    ledger_path = tmp_path / "primary/ledger.sqlite3"
    ledger = ProspectiveLedger(ledger_path)
    ledger.activate(activation_timestamp=activated.isoformat(), now=activated)
    for ticker in ("NVDA", "MSFT"):
        ledger.append("SIGNAL", f"sig-{ticker}", {
            "signal_id": f"sig-{ticker}", "ticker": ticker, "reference_price": 100.0,
            "executable_reference_timestamp": activated.isoformat(), "first_seen_at": activated.isoformat(),
        }, created_at=activated)
    calendar = build_xnys_calendar(start_date="2026-10-08", as_of=now)
    provider = RetainedHistoryProvider(calendar["trading_sessions"])
    plan = build_acquisition_plan(
        ledger=ledger, calendar=calendar, authorization=PLAN_AUTHORIZATION_TOKEN,
        source_sha="a" * 40,
    )
    result = run_daily_cycle(
        ledger_path=ledger_path, backup_root=tmp_path / "backup", alert_root=tmp_path / "alerts",
        provider=provider, calendar=calendar, now=now, authorization=AUTHORIZATION_TOKEN,
        source_sha="a" * 40,
        approved_plan=plan, approved_plan_hash=plan["artifact_sha256"],
        kill_switch_check=lambda: False,
        entitlement_evidence={"status":"APPROVED", "contract_id":"test", "effective_at":"2026-10-08",
                              "capabilities":["historical_ohlcv","splits","dividends"]},
    )
    assert result["status"] == "DAILY_CYCLE_COMPLETE"
    assert [(row["horizon"], row["target_session"]) for row in result["horizons"]] == [
        (1, "2026-10-09"), (5, "2026-10-15")
    ]
    assert len(provider.calls) == 7
    assert result["request_budget"]["distinct_requests"] == 7
    assert len(ProspectiveLedger(ledger_path).rows("OBSERVATION")) == 4

    replay_provider = RetainedHistoryProvider(calendar["trading_sessions"])
    replay_plan = build_acquisition_plan(
        ledger=ProspectiveLedger(ledger_path), calendar=calendar,
        authorization=PLAN_AUTHORIZATION_TOKEN, source_sha="a" * 40,
    )
    replay = run_daily_cycle(
        ledger_path=ledger_path, backup_root=tmp_path / "backup2", alert_root=tmp_path / "alerts",
        provider=replay_provider, calendar=calendar, now=now, authorization=AUTHORIZATION_TOKEN,
        source_sha="a" * 40,
        approved_plan=replay_plan, approved_plan_hash=replay_plan["artifact_sha256"],
        kill_switch_check=lambda: False,
        entitlement_evidence={"status":"APPROVED", "contract_id":"test", "effective_at":"2026-10-08",
                              "capabilities":["historical_ohlcv","splits","dividends"]},
    )
    assert replay["status"] == "NO_DUE_OBSERVATIONS"
    assert replay["provider_calls"] == 0
    assert replay_provider.calls == []
