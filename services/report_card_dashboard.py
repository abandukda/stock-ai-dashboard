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
from services.report_card_signal_detail import build_signal_detail, load_certified_authority


def build_internal_report_card(path: Path, *, authorized: bool, authority_root: Path | None = None) -> dict[str, Any]:
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
    amendments = [row for row in decoded if row["record_type"] == "AMENDMENT"]
    observed = {(row["parent_id"], int(row["payload"]["horizon_trading_days"])): row["payload"] for row in observations}
    table = []
    signal_details = []
    enriched_signal_details = []
    authority_rows = load_certified_authority(authority_root)
    for signal in signals:
        payload = signal["payload"]
        observation_count = sum(row["parent_id"] == signal["record_id"] for row in observations)
        signal_observations = [row["payload"] for row in observations if row["parent_id"] == signal["record_id"]]
        matured = sorted(int(item["horizon_trading_days"]) for item in signal_observations)
        next_horizon = next((horizon for horizon in HORIZONS if horizon not in matured), None)
        latest_action = next((str(row["payload"].get("canonical_action") or "") for row in reversed(amendments)
                              if row["parent_id"] == signal["record_id"] and row["payload"].get("canonical_action")), None)
        publication_eligible = payload.get("withholding_status") == "CUSTOMER_PUBLISHABLE"
        admission_reason = ("CUSTOMER_PUBLISHABLE_BUY_NOW_TRANSITION"
                            if payload.get("canonical_recommendation") == "BUY_NOW" and publication_eligible
                            else "ADMISSION_PROVENANCE_INCOMPLETE")
        signal_details.append({
            "signal_id": signal["record_id"], "ticker": payload.get("ticker"),
            "original_action": payload.get("canonical_recommendation"),
            "buy_now_transition_timestamp": payload.get("first_seen_at"),
            "signal_timestamp": payload.get("first_seen_at"), "reference_price": payload.get("reference_price"),
            "reference_price_timestamp": payload.get("reference_price_timestamp"),
            "signal_provenance": payload.get("evidence_ids") or [],
            "candidate_digest": payload.get("candidate_digest"), "publication_digest": payload.get("publication_digest"),
            "evaluation_snapshot_id": payload.get("evaluation_snapshot_id"),
            "customer_publication_eligible_at_issuance": publication_eligible,
            "admission_reason": admission_reason, "observation_count": observation_count,
            "registered_horizons": list(HORIZONS), "next_eligible_horizon": next_horizon,
            "corporate_action_state": next((item.get("corporate_action_status") for item in reversed(signal_observations)
                                              if item.get("corporate_action_status")), "Not yet observed"),
            "open": latest_action in (None, "", "BUY_NOW"),
        })
        enriched_signal_details.append(build_signal_detail(payload, signal_observations, authority_rows=authority_rows))
        for horizon in HORIZONS:
            item = observed.get((signal["record_id"], horizon))
            table.append({
                "signal_id": signal["record_id"], "ticker": payload.get("ticker"), "first_seen_at": payload.get("first_seen_at"),
                "issuance_price": payload.get("reference_price"), "action": payload.get("canonical_recommendation"),
                "opportunity": payload.get("opportunity"), "confidence": payload.get("decision_confidence"),
                "horizon_sessions": horizon, "status": item.get("data_status") if item else "NOT_MATURED_OR_NOT_OBSERVED",
                "observed_price": item.get("observed_price") if item else None,
                "observed_at": item.get("observed_at") if item else None,
                "stock_return": item.get("stock_return") if item else None,
                "spy_return": item.get("benchmark_return") if item else None,
                "excess_return": item.get("excess_return") if item else None,
                "corporate_action_status": item.get("corporate_action_status") if item else None,
                "observation_count": observation_count,
            })
    available = [row for row in table if row["status"] == "AVAILABLE"]
    returns = [float(row["stock_return"]) for row in available]
    open_tickers = [str(item["ticker"] or "") for item in signal_details if item["open"]]
    duplicated_open_episodes = sorted({ticker for ticker in open_tickers if ticker and open_tickers.count(ticker) > 1})
    admission_defects = [f"REPEATED_BUY_NOW_EPISODE_DUPLICATED:{ticker}" for ticker in duplicated_open_episodes]
    admission_defects.extend(
        f'ADMISSION_PROVENANCE_INCOMPLETE:{item["signal_id"]}'
        for item in signal_details if item["admission_reason"] == "ADMISSION_PROVENANCE_INCOMPLETE"
    )
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
        "open_signal_count": sum(item["open"] for item in signal_details),
        "admission_integrity": "PASS" if not admission_defects else "FAIL",
        "admission_defects": admission_defects,
        "coverage": coverage, "mean_return": sum(returns) / len(returns) if returns else None,
        "median_return": median(returns) if returns else None, "rows": table, "signals": signal_details,
        "signal_details": enriched_signal_details,
        "registered_horizons": list(HORIZONS),
        "next_eligible_observation": metadata.get("next_eligible_observation", "Determined by governed trading-session calendar"),
        "last_backup_status": metadata.get("last_backup_status", "Verify from protected backup workflow"),
        "limitations": ["PROSPECTIVE_ONLY", "DESCRIPTIVE_ONLY", "INTERNAL_NOT_CUSTOMER_FACING",
                        "NO_CONCLUSION_WHILE_SAMPLE_IS_INSUFFICIENT"],
    }


__all__ = ["build_internal_report_card"]
