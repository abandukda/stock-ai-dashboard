"""Sequential, recoverable Report Card daily cycle."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from services.prospective_report_card import ProspectiveLedger
from services.report_card_market_evidence_acquisition import acquire_market_evidence
from services.report_card_observation_activation import apply_observation_bundle
from services.report_card_observation_producer import build_observation_bundle


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _sqlite_copy(source: Path, destination: Path) -> None:
    source_ledger = ProspectiveLedger(source)
    source_ledger.verify()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source_ledger._connect() as connection:
        target = __import__("sqlite3").connect(destination)
        try:
            connection.backup(target)
        finally:
            target.close()


def verify_alert_sink(path: Path) -> None:
    """Prove alert storage is writable before provider access or mutation."""
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".atlas-alert-health"
    try:
        probe.write_text("healthy\n", encoding="utf-8")
        healthy = probe.read_text(encoding="utf-8") == "healthy\n"
    except OSError:
        healthy = False
    if not healthy:
        raise RuntimeError("ALERT_HEALTH_CHECK_FAILED")
    probe.unlink(missing_ok=True)


def run_daily_cycle(*, ledger_path: Path, backup_root: Path, alert_root: Path,
                    provider: Any, calendar: dict[str, Any], now: datetime,
                    authorization: str, source_sha: str, approved_plan: dict[str, Any],
                    approved_plan_hash: str, kill_switch_check: Any,
                    entitlement_evidence: dict[str, Any],
                    retry_attempts: int = 0) -> dict[str, Any]:
    """Acquire once, then validate and append due horizons oldest-first."""
    verify_alert_sink(alert_root)
    ledger = ProspectiveLedger(ledger_path)
    tip_before = ledger.verify()
    evidence = acquire_market_evidence(
        ledger=ledger, provider=provider, calendar=calendar, now=now,
        authorization=authorization, source_sha=source_sha, retry_attempts=retry_attempts,
        approved_plan=approved_plan, approved_plan_hash=approved_plan_hash,
        kill_switch_check=kill_switch_check,
        entitlement_evidence=entitlement_evidence,
    )
    if evidence.get("status") == "NO_DUE_OBSERVATIONS":
        return {"status": "NO_DUE_OBSERVATIONS", "ledger_tip_before": tip_before,
                "ledger_tip_after": ledger.verify(), "provider_calls": 0, "horizons": []}
    ordered = sorted(
        (
            (int(horizon), str(session))
            for horizon, session in (evidence.get("target_sessions") or {}).items()
        ),
        key=lambda item: (item[1], item[0]),
    )
    results: list[dict[str, Any]] = []
    for horizon, target_session in ordered:
        certified_at = now.astimezone(timezone.utc)
        first = build_observation_bundle(ledger=ledger, evidence=evidence, horizon=horizon,
                                         certified_at=certified_at)
        second = build_observation_bundle(ledger=ledger, evidence=evidence, horizon=horizon,
                                          certified_at=certified_at)
        first_digest, second_digest = _digest(first), _digest(second)
        if first_digest != second_digest:
            raise RuntimeError(f"OBSERVATION_REPLAY_MISMATCH:{horizon}")
        with tempfile.TemporaryDirectory(prefix="atlas-report-card-disposable-") as directory, \
                tempfile.TemporaryDirectory(prefix="atlas-report-card-disposable-backup-") as backup_directory:
            disposable_path = Path(directory) / "ledger.sqlite3"
            _sqlite_copy(ledger_path, disposable_path)
            disposable = ProspectiveLedger(disposable_path)
            validation = apply_observation_bundle(
                ledger=disposable, backup_root=Path(backup_directory),
                bundle=first, now=certified_at,
            )
            if validation.appended + validation.idempotent != validation.signal_count:
                raise RuntimeError(f"DISPOSABLE_OBSERVATION_VALIDATION_FAILED:{horizon}")
        applied = apply_observation_bundle(
            ledger=ledger, backup_root=backup_root, bundle=second, now=certified_at,
        )
        results.append({
            "horizon": horizon, "target_session": target_session,
            "bundle_sha256": second_digest, "appended": applied.appended,
            "idempotent": applied.idempotent, "ledger_tip": applied.ledger_tip,
            "backup_path": applied.backup_path,
        })
    tip_after = ledger.verify()
    report = {
        "status": "DAILY_CYCLE_COMPLETE",
        "ledger_tip_before": tip_before,
        "ledger_tip_after": tip_after,
        "evidence_sha256": evidence.get("artifact_sha256"),
        "provider_calls": evidence.get("provider_calls"),
        "request_budget": evidence.get("request_budget"),
        "horizons": results,
        "customer_visible": False,
        "public_performance_claims_allowed": False,
    }
    report["report_sha256"] = _digest(report)
    return report


__all__ = ["run_daily_cycle", "verify_alert_sink"]
