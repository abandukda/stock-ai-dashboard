from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.prospective_report_card import ProspectiveLedger
from services.report_card_observation_activation import BUNDLE_SCHEMA, apply_observation_bundle


ACTIVATION = datetime(2026, 10, 8, 3, 20, 17, tzinfo=timezone.utc)
CLOSE = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)


def ledger_with_signals(path: Path) -> ProspectiveLedger:
    ledger = ProspectiveLedger(path)
    ledger.activate(activation_timestamp=ACTIVATION.isoformat(), now=ACTIVATION)
    for ticker, price in (("NVDA", 100.0), ("MSFT", 200.0)):
        ledger.append("SIGNAL", ticker, {"signal_id": ticker, "semantic_identity": ticker,
                      "ticker": ticker, "reference_price": price, "first_seen_at": ACTIVATION.isoformat()},
                      created_at=ACTIVATION + timedelta(seconds=1))
    return ledger


def bundle(ledger: ProspectiveLedger):
    records = []
    for ticker, price in (("NVDA", 110.0), ("MSFT", 190.0)):
        records.append({"signal_id": ticker, "observation": {
            "observed_price": price, "observed_at": "2026-10-08T20:00:00+00:00",
            "price_source": "GOVERNED_MARKET_CLOSE", "corporate_action_status": "NONE",
            "data_status": "AVAILABLE", "benchmark_ticker": "SPY",
            "benchmark_observed_at": "2026-10-08T20:00:00+00:00",
            "benchmark_reference_price": 500.0, "benchmark_observed_price": 505.0,
            "benchmark_return": None, "trading_sessions": ["2026-10-08"]}})
    return {"schema_version": BUNDLE_SCHEMA, "activation_timestamp": ACTIVATION.isoformat(),
            "ledger_tip_before": ledger.verify(), "session_open_at": "2026-10-08T13:30:00+00:00",
            "session_close_at": CLOSE.isoformat(), "horizon_trading_days": 1, "records": records,
            "provider_calls": 0, "reacquisition": "none", "customer_visible": False,
            "public_performance_claims_allowed": False}


def test_complete_mature_bundle_is_atomic_backed_up_and_idempotent(tmp_path):
    ledger = ledger_with_signals(tmp_path / "primary/ledger.sqlite3")
    payload = bundle(ledger)
    result = apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup",
                                      bundle=payload, now=CLOSE + timedelta(minutes=1))
    assert (result.appended, result.signal_count, result.session_date) == (2, 2, "2026-10-08")
    assert ProspectiveLedger(Path(result.backup_path)).verify() == result.ledger_tip
    payload["ledger_tip_before"] = ledger.verify()
    replay = apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup2",
                                      bundle=payload, now=CLOSE + timedelta(minutes=2))
    assert (replay.appended, replay.idempotent) == (0, 2)


def test_before_close_fails_without_mutating_ledger(tmp_path):
    ledger = ledger_with_signals(tmp_path / "ledger.sqlite3")
    tip = ledger.verify()
    with pytest.raises(ValueError, match="OBSERVATION_HORIZON_NOT_MATURE"):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=bundle(ledger),
                                 now=CLOSE - timedelta(seconds=1))
    assert ledger.verify() == tip and ledger.rows("OBSERVATION") == []


@pytest.mark.parametrize("mutation,error", [
    (lambda b: b["records"].pop(), "OBSERVATION_SIGNAL_COVERAGE_MISMATCH"),
    (lambda b: b.update(ledger_tip_before="wrong"), "OBSERVATION_LEDGER_TIP_MISMATCH"),
    (lambda b: b["records"][0]["observation"].update(corporate_action_status=""), "CORPORATE_ACTION_STATUS_REQUIRED"),
    (lambda b: b["records"][0]["observation"].update(benchmark_observed_at="2026-10-07T20:00:00+00:00"),
     "STOCK_BENCHMARK_BOUNDARIES_NOT_ALIGNED"),
])
def test_bundle_fails_closed(mutation, error, tmp_path):
    ledger = ledger_with_signals(tmp_path / "ledger.sqlite3")
    payload = bundle(ledger)
    mutation(payload)
    with pytest.raises(ValueError, match=error):
        apply_observation_bundle(ledger=ledger, backup_root=tmp_path / "backup", bundle=payload,
                                 now=CLOSE + timedelta(minutes=1))


def test_observation_workflow_is_manual_internal_and_zero_provider():
    source = Path(".github/workflows/atlas_internal_report_card_observation.yml").read_text()
    assert "  workflow_dispatch:" in source and "  schedule:" not in source
    assert "atlas-internal-report-card" in source
    assert "runs-on: [self-hosted, Linux, X64, atlas-worker-1]" in source
    assert "python3 scripts/run_internal_report_card_observations.py" in source
    assert "FINNHUB_API_KEY" not in source and "customer_visible'] is False" in source


def test_finnhub_workflow_is_manual_only_but_governance_unchanged():
    source = Path(".github/workflows/atlas_finnhub_full_universe_certification.yml").read_text()
    assert "  workflow_dispatch:" in source and "  schedule:" not in source
    for cron in ("15 4", "00 11", "00 16", "00 19", "00 23"):
        assert cron not in source
    assert 'SHARD_SIZE: "150"' in source
    assert "run_finnhub_full_universe.py run-shard" in source
    assert "run_finnhub_full_universe.py aggregate" in source
