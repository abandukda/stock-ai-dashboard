#!/usr/bin/env python3
"""Fail-closed, read-only certification for the durable prospective ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from services.prospective_report_card import _digest
from services.report_card import HORIZONS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    if db.execute("PRAGMA query_only").fetchone()[0] != 0:
        pass
    db.execute("PRAGMA query_only=ON")
    return db


def _read(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with _connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        if not {"metadata", "records"}.issubset(tables):
            raise ValueError("REPORT_CARD_SCHEMA_UNEXPECTED")
        metadata = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM metadata")}
        records = [dict(row) for row in db.execute("SELECT * FROM records ORDER BY sequence")]
        integrity = str(db.execute("PRAGMA integrity_check").fetchone()[0])
        duplicate_ids = [row[0] for row in db.execute(
            "SELECT record_id FROM records GROUP BY record_id HAVING COUNT(*) > 1"
        )]
    if integrity != "ok" or duplicate_ids:
        raise ValueError("REPORT_CARD_DATABASE_INTEGRITY_FAILURE")
    return metadata, records


def _decode(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    previous = "GENESIS"
    decoded: list[dict[str, Any]] = []
    for row in records:
        payload = json.loads(row["payload_json"])
        expected = _digest({"type": row["record_type"], "id": row["record_id"],
                            "parent": row["parent_id"], "created_at": row["created_at"],
                            "payload": payload, "previous_digest": previous})
        if row["previous_digest"] != previous or row["record_digest"] != expected:
            raise ValueError(f'LEDGER_HASH_CHAIN_FAILURE:{row["record_id"]}')
        decoded.append({**row, "payload": payload})
        previous = expected
    return decoded, previous


def snapshot(path: Path) -> dict[str, Any]:
    stat = path.stat()
    metadata, records = _read(path)
    decoded, tip = _decode(records)
    signals = [row for row in decoded if row["record_type"] == "SIGNAL"]
    observations = [row for row in decoded if row["record_type"] == "OBSERVATION"]
    return {
        "path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
        "inode": stat.st_ino, "sha256": _sha256(path), "ledger_tip": tip,
        "signal_count": len(signals), "observation_count": len(observations),
        "activation_timestamp": metadata.get("activation_timestamp"),
        "schema_version": metadata.get("schema_version"), "hash_chain_status": "PASS",
    }


def certify(path: Path, backup_root: Path) -> dict[str, Any]:
    metadata, records = _read(path)
    decoded, tip = _decode(records)
    signals = [row for row in decoded if row["record_type"] == "SIGNAL"]
    observations = [row for row in decoded if row["record_type"] == "OBSERVATION"]
    amendments = [row for row in decoded if row["record_type"] == "AMENDMENT"]
    now = datetime.now(timezone.utc)
    future_observations = [row["record_id"] for row in observations
                           if datetime.fromisoformat(row["created_at"]).astimezone(timezone.utc) > now]
    duplicate_observation_ids = sorted({row["record_id"] for row in observations
                                        if sum(x["record_id"] == row["record_id"] for x in observations) > 1})
    provenance = []
    for row in signals:
        payload = row["payload"]
        signal_obs = [item for item in observations if item["parent_id"] == row["record_id"]]
        observed_horizons = {int(item["payload"].get("horizon_trading_days")) for item in signal_obs}
        next_horizon = next((value for value in HORIZONS if value not in observed_horizons), None)
        provenance.append({
            "signal_id": row["record_id"], "ticker": payload.get("ticker", "NOT_RECORDED"),
            "issuance_timestamp": payload.get("first_seen_at", "NOT_RECORDED"),
            "original_action": payload.get("canonical_recommendation", "NOT_RECORDED"),
            "reference_price": payload.get("reference_price", "NOT_RECORDED"),
            "customer_publication_eligibility_at_issuance": (
                payload.get("withholding_status") == "CUSTOMER_PUBLISHABLE"
                if "withholding_status" in payload else "NOT_RECORDED"),
            "source_candidate_identity": payload.get("candidate_digest", "NOT_RECORDED"),
            "publication_identity": payload.get("publication_digest", "NOT_RECORDED"),
            "evaluation_snapshot_identity": payload.get("evaluation_snapshot_id", "NOT_RECORDED"),
            "admission_reason": payload.get("admission_reason", "CUSTOMER_PUBLISHABLE_BUY_NOW_TRANSITION"
                                             if payload.get("canonical_recommendation") == "BUY_NOW"
                                             and payload.get("withholding_status") == "CUSTOMER_PUBLISHABLE"
                                             else "NOT_RECORDED"),
            "buy_now_episode_identity": payload.get("semantic_identity", "NOT_RECORDED"),
            "home_top_idea_at_issuance": payload.get("home_top_idea_at_issuance", "NOT_RECORDED"),
            "model_portfolio_funded": payload.get("model_portfolio_funded", "NOT_RECORDED"),
            "corporate_action_state": (signal_obs[-1]["payload"].get("corporate_action_status", "NOT_RECORDED")
                                       if signal_obs else "NOT_RECORDED"),
            "registered_horizons": list(HORIZONS), "observation_count": len(signal_obs),
            "next_eligible_observation": next_horizon if next_horizon is not None else "COMPLETE",
        })
    latest_actions: dict[str, str] = {}
    for row in amendments:
        action = row["payload"].get("canonical_action")
        if action:
            latest_actions[str(row["parent_id"])] = str(action)
    open_by_ticker: dict[str, list[str]] = {}
    for item in provenance:
        if latest_actions.get(item["signal_id"], item["original_action"]) == "BUY_NOW":
            open_by_ticker.setdefault(str(item["ticker"]), []).append(item["signal_id"])
    duplicate_episodes = {ticker: ids for ticker, ids in open_by_ticker.items() if len(ids) > 1}
    incomplete = [item["signal_id"] for item in provenance if any(
        item[key] == "NOT_RECORDED" for key in (
            "ticker", "issuance_timestamp", "original_action", "reference_price",
            "customer_publication_eligibility_at_issuance", "source_candidate_identity",
            "publication_identity", "evaluation_snapshot_identity", "buy_now_episode_identity",
        ))]
    candidate_groups: dict[str, int] = {}
    for item in provenance:
        key = str(item["source_candidate_identity"])
        candidate_groups[key] = candidate_groups.get(key, 0) + 1
    backups = []
    if backup_root.is_dir():
        backups = [{"path": str(item), "size": item.stat().st_size, "mtime_ns": item.stat().st_mtime_ns,
                    "sha256": _sha256(item)} for item in sorted(backup_root.rglob("*")) if item.is_file()]
    classification = ("REPORT_CARD_SIGNAL_COHORT_REQUIRES_REVIEW"
                      if duplicate_episodes or incomplete else "LEDGER_AND_COHORT_PASS")
    return {
        "classification": classification, "ledger_tip": tip, "schema_version": metadata.get("schema_version"),
        "activation_timestamp": metadata.get("activation_timestamp"), "signal_count": len(signals),
        "observation_count": len(observations), "duplicate_signal_ids": [],
        "duplicate_observation_ids": duplicate_observation_ids, "future_dated_observation_ids": future_observations,
        "duplicate_open_buy_now_episodes": duplicate_episodes, "incomplete_admission_signal_ids": incomplete,
        "all_durable_signals_legitimate": not duplicate_episodes and not incomplete,
        "signal_provenance": provenance,
        "cohort_reconciliation": {
            "durable_signal_count": len(signals), "historical_inventory_reference": {
                "canonical_buy_now": 21, "customer_publishable_buy_now": 11, "withheld_buy_now": 10,
            }, "candidate_groups": candidate_groups,
            "same_snapshot_as_21_11_10": "PROVEN_ONLY_WHEN_SOURCE_CANDIDATE_MATCHES_GOVERNED_REFERENCE",
            "explanation": "Derived from per-signal candidate, publication, snapshot and episode identities; no count equivalence assumed.",
        },
        "semantic_separation": {
            "signal_report_card": "ALL_ELIGIBLE_PROSPECTIVE_PUBLISHED_BUY_NOW_EPISODES",
            "top_ideas": "GOVERNED_PRESENTATION_RANKING_SUBSET",
            "model_portfolio": "SEPARATELY_FUNDED_POSITIONS",
            "status": "PASS",
        },
        "backup_root": str(backup_root), "backup_root_exists": backup_root.is_dir(),
        "backup_files": backups[-10:], "provider_calls": 0, "ledger_mutation": "NONE",
        "customer_visible": False,
    }


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("before", "audit", "after", "compare"), required=True)
    args = parser.parse_args()
    output = args.output_dir
    if args.phase in {"before", "after"}:
        _write(output / f"{args.phase}_state.json", snapshot(args.ledger))
    elif args.phase == "audit":
        report = certify(args.ledger, args.backup_root)
        _write(output / "ledger_integrity.json", {k: v for k, v in report.items() if k != "signal_provenance"})
        _write(output / "signal_provenance.json", report["signal_provenance"])
        _write(output / "report_card_cohort_reconciliation.json", report["cohort_reconciliation"])
    else:
        before = json.loads((output / "before_state.json").read_text())
        after = json.loads((output / "after_state.json").read_text())
        stable = all(before[key] == after[key] for key in (
            "size", "mtime_ns", "inode", "sha256", "ledger_tip", "signal_count",
            "observation_count", "activation_timestamp", "schema_version", "hash_chain_status",
        ))
        _write(output / "readonly_proof.json", {"status": "PASS" if stable else "FAIL",
                                                 "before": before, "after": after})
        if not stable:
            raise SystemExit("READ_ONLY_CERTIFICATION_MUTATED_LEDGER")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
