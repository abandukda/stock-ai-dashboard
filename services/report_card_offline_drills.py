"""Disposable, provider-free observation append and restore drills."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Any, Mapping
from services.prospective_report_card import ProspectiveLedger
from services.report_card_daily_operations import ordered_catch_up
from services.report_card_observation_activation import apply_observation_bundle
from services.report_card_observation_producer import build_observation_bundle

def run_disposable_drill(*, ledger_path: Path, evidence: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    original = ProspectiveLedger(ledger_path)
    original_tip = original.verify()
    with tempfile.TemporaryDirectory(prefix="atlas-report-card-drill-") as root, \
            tempfile.TemporaryDirectory(prefix="atlas-report-card-drill-backup-") as backup_root:
        copy = Path(root) / "ledger.sqlite3"
        with original._connect() as source, __import__("sqlite3").connect(copy) as target:
            source.backup(target)
        ledger = ProspectiveLedger(copy)
        results = []
        for horizon, session in ordered_catch_up(evidence.get("target_sessions") or {}):
            first = build_observation_bundle(ledger=ledger, evidence=evidence, horizon=horizon, certified_at=now)
            second = build_observation_bundle(ledger=ledger, evidence=evidence, horizon=horizon, certified_at=now)
            if first != second:
                raise RuntimeError("DISPOSABLE_PRODUCER_REPLAY_MISMATCH")
            result = apply_observation_bundle(ledger=ledger, backup_root=Path(backup_root) / f"backup-{horizon}",
                                              bundle=first, now=now)
            restored = ProspectiveLedger(result.backup_path)
            if restored.verify() != result.ledger_tip:
                raise RuntimeError("DISPOSABLE_RESTORE_MISMATCH")
            results.append({"horizon": horizon, "session": session, "appended": result.appended,
                            "idempotent": result.idempotent, "restored_tip": restored.verify()})
        final_tip = ledger.verify()
    if original.verify() != original_tip:
        raise RuntimeError("SOURCE_LEDGER_MUTATED_BY_DISPOSABLE_DRILL")
    return {"status": "PASS", "source_tip": original_tip, "disposable_tip": final_tip,
            "ordered_results": results, "provider_calls": 0, "source_ledger_mutations": 0}

__all__ = ["run_disposable_drill"]
