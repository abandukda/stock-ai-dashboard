"""Governed, zero-provider activation of prospective Report Card observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from services.prospective_report_card import ProspectiveLedger, _utc, append_observations_atomic


BUNDLE_SCHEMA = "ATLAS_REPORT_CARD_OBSERVATION_BUNDLE_V1"
FINALIZED_SESSION_STATUS = "FINALIZED_REGULAR_CLOSE"
ALLOWED_PRICE_SOURCES = frozenset({"GOVERNED_OFFICIAL_DAILY_CLOSE", "GOVERNED_ADJUSTED_DAILY_CLOSE"})
ALLOWED_CORPORATE_ACTION_STATUS = frozenset({"NONE", "SPLIT_ADJUSTED", "DIVIDEND_ADJUSTED", "MERGER_PENDING_GOVERNED_TREATMENT"})


@dataclass(frozen=True)
class ObservationResult:
    status: str
    appended: int
    idempotent: int
    signal_count: int
    horizon: int
    session_date: str
    ledger_tip: str
    backup_path: str


def apply_observation_bundle(*, ledger: ProspectiveLedger, backup_root: Path,
                             bundle: Mapping[str, Any], now: datetime) -> ObservationResult:
    """Append one complete matured horizon bundle; never acquire market data."""
    if bundle.get("schema_version") != BUNDLE_SCHEMA:
        raise ValueError("OBSERVATION_BUNDLE_SCHEMA_INVALID")
    activation = ledger.activation_timestamp()
    expected_activation = _utc(bundle.get("activation_timestamp"), "BUNDLE_ACTIVATION")
    if expected_activation != activation:
        raise ValueError("OBSERVATION_ACTIVATION_MISMATCH")
    if str(bundle.get("ledger_tip_before") or "") != ledger.verify():
        raise ValueError("OBSERVATION_LEDGER_TIP_MISMATCH")
    if bundle.get("customer_visible") is not False or bundle.get("public_performance_claims_allowed") is not False:
        raise ValueError("OBSERVATION_INTERNAL_ONLY_CONTRACT_REQUIRED")
    if int(bundle.get("provider_calls", -1)) != 0 or bundle.get("reacquisition") != "none":
        raise ValueError("OBSERVATION_WORKFLOW_MUST_BE_ZERO_PROVIDER")

    opened = _utc(bundle.get("session_open_at"), "SESSION_OPEN")
    closed = _utc(bundle.get("session_close_at"), "SESSION_CLOSE")
    certified_at = _utc(bundle.get("bundle_certified_at"), "BUNDLE_CERTIFIED")
    current = now.astimezone(timezone.utc)
    if (bundle.get("session_status") != FINALIZED_SESSION_STATUS or
            not bundle.get("trading_calendar_source") or not bundle.get("trading_calendar_version") or
            opened <= activation or closed <= opened or certified_at < closed or current < certified_at):
        raise ValueError("OBSERVATION_HORIZON_NOT_MATURE")

    horizon = int(bundle.get("horizon_trading_days", 0))
    records = list(bundle.get("records") or ())
    signals = ledger.rows("SIGNAL")
    expected_ids = {row["record_id"] for row in signals}
    actual_ids = [str(row.get("signal_id") or "") for row in records]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise ValueError("OBSERVATION_SIGNAL_COVERAGE_MISMATCH")

    signal_by_id = {row["record_id"]: row["payload"] for row in signals}
    prepared = []
    session_date = closed.date().isoformat()
    for record in records:
        signal_id = str(record["signal_id"])
        observation = dict(record.get("observation") or {})
        sessions: Sequence[str] = observation.get("trading_sessions") or ()
        if len(sessions) != horizon or str(sessions[-1]) != session_date:
            raise ValueError("OBSERVATION_SESSION_CONTRACT_MISMATCH")
        if observation.get("corporate_action_status") not in ALLOWED_CORPORATE_ACTION_STATUS:
            raise ValueError("CORPORATE_ACTION_STATUS_REQUIRED")
        if observation.get("price_source") not in ALLOWED_PRICE_SOURCES:
            raise ValueError("OBSERVATION_PRICE_AUTHORITY_INVALID")
        provenance = observation.get("price_provenance")
        if not isinstance(provenance, Mapping) or not all(provenance.get(key) for key in ("provider", "instrument", "as_of", "retrieved_at", "currency")):
            raise ValueError("OBSERVATION_PRICE_PROVENANCE_REQUIRED")
        if provenance.get("session_status") != FINALIZED_SESSION_STATUS:
            raise ValueError("OBSERVATION_PRICE_NOT_FINALIZED")
        if observation.get("data_status") == "AVAILABLE":
            reference = float(signal_by_id[signal_id]["reference_price"])
            observed = float(observation["observed_price"])
            spy_reference = float(observation.pop("benchmark_reference_price"))
            spy_observed = float(observation.pop("benchmark_observed_price"))
            stock_return = observed / reference - 1.0
            benchmark_return = spy_observed / spy_reference - 1.0
            observation.update(stock_return=stock_return, benchmark_return=benchmark_return,
                               excess_return=stock_return - benchmark_return)
        elif not observation.get("unavailable_reason"):
            raise ValueError("OBSERVATION_UNAVAILABLE_REASON_REQUIRED")
        prepared.append((signal_id, observation))

    appended, idempotent = append_observations_atomic(
        ledger, horizon=horizon, observations=prepared, now=current,
    )

    tip = ledger.verify()
    backup = ledger.backup(backup_root, now=current)
    with tempfile.TemporaryDirectory(prefix="atlas-report-card-restore-") as directory:
        restored_path = Path(directory) / "restored.sqlite3"
        shutil.copy2(backup, restored_path)
        restored = ProspectiveLedger(restored_path)
        if restored.verify() != tip or len(restored.rows()) != len(ledger.rows()):
            raise ValueError("OBSERVATION_BACKUP_RESTORE_FAILED")
    return ObservationResult("OBSERVATIONS_RECORDED", appended, idempotent, len(signals), horizon,
                             session_date, tip, str(backup))


__all__ = ["ALLOWED_CORPORATE_ACTION_STATUS", "ALLOWED_PRICE_SOURCES", "BUNDLE_SCHEMA",
           "FINALIZED_SESSION_STATUS", "ObservationResult", "apply_observation_bundle"]
