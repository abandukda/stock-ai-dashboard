from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib

import pytest

from services.prospective_report_card import ProspectiveLedger
from services.report_card_market_evidence_acquisition import (
    AUTHORIZATION_TOKEN, PLAN_AUTHORIZATION_TOKEN, acquire_market_evidence,
    build_acquisition_plan, derive_acquisition_scope, estimated_provider_calls, request_budget,
)
from scripts.acquire_report_card_market_evidence import resolve_verified_backup


UTC = timezone.utc
ACTIVATED = datetime(2026, 10, 8, 21, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 9, 21, 0, tzinfo=UTC)
SESSIONS = ["2026-10-08", "2026-10-09"]


def ledger(path: Path, *, duplicate=False) -> ProspectiveLedger:
    item = ProspectiveLedger(path)
    item.activate(activation_timestamp=ACTIVATED.isoformat(), now=ACTIVATED)
    rows = [("sig-nvda", "NVDA"), ("sig-msft", "MSFT")]
    if duplicate:
        rows.append(("sig-nvda-2", "NVDA"))
    for signal_id, ticker in rows:
        item.append("SIGNAL", signal_id, {
            "signal_id": signal_id,
            "ticker": ticker,
            "reference_price": 100,
            "executable_reference_timestamp": ACTIVATED.isoformat(),
            "first_seen_at": ACTIVATED.isoformat(),
        }, created_at=ACTIVATED)
    return item


def calendar():
    return {
        "source": "XNYS_GOVERNED_CALENDAR",
        "version": "2026.10.09",
        "trading_sessions": SESSIONS,
        "finalized_session": "2026-10-09",
        "session_status": "FINALIZED_REGULAR_CLOSE",
        "session_open_at": "2026-10-09T13:30:00+00:00",
        "session_close_at": "2026-10-09T20:00:00+00:00",
    }


def governed(payload, ticker, capability, *, status="CERTIFIED"):
    return {
        "provenance": {
            "certification_status": status,
            "raw_evidence_id": f"FINNHUB:{capability}:{ticker}",
            "content_hash": f"hash-{capability}-{ticker}",
        },
        "payload": payload,
    }


class Provider:
    def __init__(self, *, missing=None, stale=None, failed=None):
        self.calls = []
        self.missing = missing
        self.stale = stale
        self.failed = failed

    def fetch(self, capability, symbol, **parameters):
        self.calls.append((capability, symbol, parameters))
        if (capability, symbol) == self.failed:
            return governed({"reason": "HTTP_503"}, symbol, capability, status="DATA_UNAVAILABLE")
        if capability == "historical_ohlcv":
            closes = [100.0, 101.0]
            if symbol == self.missing:
                closes = [None, None]
            elif symbol == self.stale:
                closes = [100.0, None]
            return governed({
                "timestamps": [1791417600, 1791504000],
                "close": closes,
                "completed_session_flags": [True, True],
            }, symbol, capability)
        return governed({"corporate_actions": []}, symbol, capability)


def test_scope_is_ledger_derived_and_duplicate_tickers_are_deduplicated(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3", duplicate=True)
    scope = derive_acquisition_scope(ledger=item, trading_sessions=SESSIONS, finalized_session="2026-10-09")
    assert scope.tickers == ("MSFT", "NVDA")
    assert scope.horizons == (1,)
    assert scope.target_sessions == {1: "2026-10-09"}
    assert estimated_provider_calls(scope) == 7
    assert request_budget(scope, retry_attempts=0) == {
        "unique_due_tickers": 2, "due_horizons": 1, "distinct_requests": 7,
        "zero_retry_ceiling": 7, "retry_ceiling": 7,
    }


def test_horizons_share_successful_requests_but_retry_ceiling_remains_conservative(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    sessions = ["2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"]
    scope = derive_acquisition_scope(ledger=item, trading_sessions=sessions, finalized_session="2026-10-15")
    assert scope.horizons == (1, 5)
    assert scope.target_sessions == {1: "2026-10-09", 5: "2026-10-15"}
    assert request_budget(scope, retry_attempts=0)["distinct_requests"] == 7
    assert request_budget(scope, retry_attempts=1)["retry_ceiling"] == 14
    with pytest.raises(ValueError, match="RETRY_LIMIT"):
        request_budget(scope, retry_attempts=2)


def test_plan_mode_is_exact_ledger_scope_and_makes_zero_provider_calls(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3", duplicate=True)
    plan = build_acquisition_plan(
        ledger=item, calendar=calendar(), authorization=PLAN_AUTHORIZATION_TOKEN,
        source_sha="a" * 40,
    )
    assert plan["status"] == "PLAN_ONLY"
    assert plan["due_tickers"] == ["MSFT", "NVDA"]
    assert plan["benchmark_ticker"] == "SPY"
    assert plan["provider_call_budget"] == 7
    assert plan["provider_calls"] == 0
    assert plan["retry_attempts"] == 0
    assert plan["ledger_mutation_allowed"] is False


def test_plan_mode_requires_distinct_authorization(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    with pytest.raises(PermissionError, match="PLAN_NOT_AUTHORIZED"):
        build_acquisition_plan(
            ledger=item, calendar=calendar(), authorization=AUTHORIZATION_TOKEN,
            source_sha="a" * 40,
        )


def test_acquisition_is_deterministic_except_declared_artifact_hash(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    first = acquire_market_evidence(
        ledger=item, provider=Provider(), calendar=calendar(), now=NOW,
        authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
    )
    second = acquire_market_evidence(
        ledger=item, provider=Provider(), calendar=calendar(), now=NOW,
        authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
    )
    assert first == second
    assert first["provider_calls"] == 7
    assert first["customer_visible"] is False
    assert first["raw_machine_readable_redistribution"] is False
    assert set(first["instruments"]) == {"NVDA", "MSFT", "SPY"}
    assert first["benchmark_references"]["sig-nvda"]["price"] == 100.0
    assert first["benchmark_references"]["sig-nvda"]["as_of"] == "2026-10-08"


def test_authorization_and_finalized_session_fail_closed(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    with pytest.raises(PermissionError, match="NOT_AUTHORIZED"):
        acquire_market_evidence(
            ledger=item, provider=Provider(), calendar=calendar(), now=NOW,
            authorization="false", source_sha="a" * 40,
        )
    opened = calendar(); opened["session_status"] = "OPEN"
    with pytest.raises(ValueError, match="NOT_FINALIZED"):
        acquire_market_evidence(
            ledger=item, provider=Provider(), calendar=opened, now=NOW,
            authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
        )


def test_missing_price_is_explicit_and_never_zero(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    result = acquire_market_evidence(
        ledger=item, provider=Provider(missing="NVDA"), calendar=calendar(), now=NOW,
        authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
    )
    assert result["instruments"]["NVDA"]["data_status"] == "MISSING_PRICE"
    assert result["instruments"]["NVDA"]["unavailable_reason"] == "FINALIZED_DAILY_CLOSE_MISSING"
    assert "2026-10-09" not in result["instruments"]["NVDA"]["closes"]


def test_stale_price_is_distinct_from_missing_price(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    result = acquire_market_evidence(
        ledger=item, provider=Provider(stale="NVDA"), calendar=calendar(), now=NOW,
        authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
    )
    assert result["instruments"]["NVDA"]["data_status"] == "STALE_PRICE"
    assert result["instruments"]["NVDA"]["unavailable_reason"] == "FINALIZED_DAILY_CLOSE_STALE"
    assert result["instruments"]["NVDA"]["latest_available_session"] == "2026-10-08"


def test_provider_error_retries_then_fails_corporate_action_evidence(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")
    provider = Provider(failed=("splits", "MSFT"))
    with pytest.raises(ValueError, match="CORPORATE_ACTION_EVIDENCE_UNAVAILABLE"):
        acquire_market_evidence(
            ledger=item, provider=provider, calendar=calendar(), now=NOW,
            authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
            retry_attempts=1,
        )
    assert sum(call[:2] == ("splits", "MSFT") for call in provider.calls) == 2


def test_partial_price_arrays_fail_closed(tmp_path):
    item = ledger(tmp_path / "ledger.sqlite3")

    class Partial(Provider):
        def fetch(self, capability, symbol, **parameters):
            record = super().fetch(capability, symbol, **parameters)
            if capability == "historical_ohlcv" and symbol == "NVDA":
                record = deepcopy(record); record["payload"]["close"].pop()
            return record

    with pytest.raises(ValueError, match="PARTIAL_PRICE_ACQUISITION"):
        acquire_market_evidence(
            ledger=item, provider=Partial(), calendar=calendar(), now=NOW,
            authorization=AUTHORIZATION_TOKEN, source_sha="a" * 40,
        )


def test_dispatch_workflow_is_inert_and_requires_distinct_primary_and_backup():
    source = Path(".github/workflows/atlas_report_card_market_evidence_acquisition.yml").read_text(
        encoding="utf-8"
    )
    assert "schedule:" not in source
    assert "execution_mode:" in source
    assert "REPORT_CARD_PLAN_ONCE" in source
    assert 'test "${{ inputs.authorize_acquisition }}" = "REPORT_CARD_ACQUIRE_ONCE"' in source
    assert "ATLAS_REPORT_CARD_DURABLE_ROOT" in source
    assert "ATLAS_REPORT_CARD_BACKUP_ROOT" in source
    assert '--backup-root "$ATLAS_REPORT_CARD_BACKUP_ROOT"' in source
    assert "append_observation" not in source
    assert "REPORT_CARD_APPEND_ONCE" not in source


def test_timestamped_backup_requires_sidecar_and_matching_logical_tip(tmp_path):
    primary = ledger(tmp_path / "primary" / "report-card.sqlite3")
    backup_root = tmp_path / "backup"
    backup_root.mkdir()
    backup = primary.backup(backup_root, now=ACTIVATED)
    expected = hashlib.sha256(backup.read_bytes()).hexdigest()
    assert backup.with_suffix(".sqlite3.sha256").read_text(encoding="utf-8").strip() == expected
    assert resolve_verified_backup(backup_root=backup_root, primary_tip=primary.verify()) == backup


def test_backup_resolution_fails_closed_on_bad_or_ambiguous_identity(tmp_path):
    primary = ledger(tmp_path / "primary" / "report-card.sqlite3")
    backup_root = tmp_path / "backup"
    backup_root.mkdir()
    first = primary.backup(backup_root, now=ACTIVATED)
    first.with_suffix(".sqlite3.sha256").write_text("0" * 64 + "\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="VERIFIED_REPORT_CARD_BACKUP_REQUIRED"):
        resolve_verified_backup(backup_root=backup_root, primary_tip=primary.verify())

    first = primary.backup(backup_root, now=ACTIVATED)
    second = primary.backup(backup_root, now=NOW)
    with pytest.raises(RuntimeError, match="REPORT_CARD_BACKUP_IDENTITY_AMBIGUOUS"):
        resolve_verified_backup(backup_root=backup_root, primary_tip=primary.verify())
