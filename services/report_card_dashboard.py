"""Read-only internal prospective Report Card projection."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from statistics import median
from typing import Any

from services.prospective_report_card import _digest
from services.report_card import HORIZONS
from services.report_card_governance import public_report_allowed


def build_internal_report_card(path: Path, *, authorized: bool) -> dict[str, Any]:
    if not authorized:
        raise PermissionError("INTERNAL_REPORT_CARD_ACCESS_REQUIRED")
    if public_report_allowed():
        raise PermissionError("PUBLIC_REPORT_CARD_MUST_REMAIN_OFF")
    ledger_path = Path(path).resolve()
    if not ledger_path.is_file():
        raise FileNotFoundError("INTERNAL_REPORT_CARD_LEDGER_UNAVAILABLE")
    uri = f"file:{ledger_path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        metadata = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM metadata")}
        records = list(db.execute("SELECT * FROM records ORDER BY sequence"))
    previous = "GENESIS"
    decoded = []
    for row in records:
        payload = json.loads(row["payload_json"])
        expected = _digest({"type": row["record_type"], "id": row["record_id"], "parent": row["parent_id"],
                            "created_at": row["created_at"], "payload": payload, "previous_digest": previous})
        if row["previous_digest"] != previous or row["record_digest"] != expected:
            raise ValueError("LEDGER_INTEGRITY_FAILURE")
        previous = expected
        decoded.append({**dict(row), "payload": payload})
    signals = [row for row in decoded if row["record_type"] == "SIGNAL"]
    observations = [row for row in decoded if row["record_type"] == "OBSERVATION"]
    observed = {(row["parent_id"], int(row["payload"]["horizon_trading_days"])): row["payload"] for row in observations}
    table = []
    for signal in signals:
        payload = signal["payload"]
        for horizon in HORIZONS:
            item = observed.get((signal["record_id"], horizon))
            table.append({
                "ticker": payload.get("ticker"), "first_seen_at": payload.get("first_seen_at"),
                "issuance_price": payload.get("reference_price"), "action": payload.get("canonical_recommendation"),
                "opportunity": payload.get("opportunity"), "confidence": payload.get("decision_confidence"),
                "horizon_sessions": horizon, "status": item.get("data_status") if item else "NOT_MATURED_OR_NOT_OBSERVED",
                "observed_price": item.get("observed_price") if item else None,
                "observed_at": item.get("observed_at") if item else None,
                "stock_return": item.get("stock_return") if item else None,
                "spy_return": item.get("benchmark_return") if item else None,
                "excess_return": item.get("excess_return") if item else None,
                "corporate_action_status": item.get("corporate_action_status") if item else None,
            })
    available = [row for row in table if row["status"] == "AVAILABLE"]
    returns = [float(row["stock_return"]) for row in available]
    coverage = {
        str(horizon): {
            "available": sum(row["horizon_sessions"] == horizon and row["status"] == "AVAILABLE" for row in table),
            "unavailable": sum(row["horizon_sessions"] == horizon and row["status"] not in {"AVAILABLE", "NOT_MATURED_OR_NOT_OBSERVED"} for row in table),
            "pending": sum(row["horizon_sessions"] == horizon and row["status"] == "NOT_MATURED_OR_NOT_OBSERVED" for row in table),
        } for horizon in HORIZONS
    }
    return {
        "classification": "INTERNAL_ONLY_PROSPECTIVE_REPORT_CARD", "customer_visible": False,
        "public_performance_claims_allowed": False, "activation_timestamp": metadata.get("activation_timestamp"),
        "ledger_tip_digest": previous, "integrity": "PASS", "signal_count": len(signals),
        "observation_count": len(observations), "spy_comparison_count": sum(row["spy_return"] is not None for row in available),
        "coverage": coverage, "mean_return": sum(returns) / len(returns) if returns else None,
        "median_return": median(returns) if returns else None, "rows": table,
        "limitations": ["PROSPECTIVE_ONLY", "DESCRIPTIVE_ONLY", "INTERNAL_NOT_CUSTOMER_FACING",
                        "NO_CONCLUSION_WHILE_SAMPLE_IS_INSUFFICIENT"],
    }


__all__ = ["build_internal_report_card"]
