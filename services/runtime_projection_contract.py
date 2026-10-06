"""Governed binding between a certified source bundle and its deployed projection."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence


VERSION = "ATLAS_RUNTIME_PROJECTION_V1"


def semantic_digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("symbol") or row.get("Ticker") or "").upper().strip()


def _certified_action(row: Mapping[str, Any]) -> str:
    certified = dict(row.get("certified_customer_evaluation") or {})
    return str(dict(certified.get("decision") or {}).get("action") or "").upper()


def inventory_partition(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    canonical = []
    publishable = []
    withheld = []
    customer_allowed = []
    for row in rows:
        ticker = _ticker(row)
        certified = dict(row.get("certified_customer_evaluation") or {})
        allowed = certified.get("customer_publication_allowed") is True
        action = _certified_action(row)
        if allowed:
            customer_allowed.append(ticker)
        if action != "BUY_NOW":
            continue
        canonical.append(ticker)
        (publishable if allowed else withheld).append(ticker)
    return {
        "canonical_buy_now": sorted(set(canonical)),
        "publishable_buy_now": sorted(set(publishable)),
        "withheld_buy_now": sorted(set(withheld)),
        "customer_allowed": sorted(set(customer_allowed)),
    }


def build_runtime_projection_contract(
    *, manifest: Mapping[str, Any], artifacts: Mapping[str, Any],
    candidate_digest: str, publication_digest: str, source_sha: str,
    evidence_snapshot_at: str, source_counts: Mapping[str, Any],
    expected_facts: Mapping[str, Any], required_tickers: Sequence[str],
    source_inventory: Mapping[str, Any],
) -> dict[str, Any]:
    full_rows = list(artifacts.get("full_evaluation_pool.json") or ())
    partition = inventory_partition(full_rows)
    files = {
        name: {"semantic_sha256": semantic_digest(payload), "record_count": len(payload) if isinstance(payload, list) else 1}
        for name, payload in sorted(artifacts.items())
    }
    return {
        "version": VERSION,
        "source_certification": {
            "candidate_digest": candidate_digest,
            "publication_digest": publication_digest,
            "analytical_source_sha": source_sha,
            "evidence_snapshot_at": evidence_snapshot_at,
            "workflow_run_id": str(manifest.get("workflow_run_id") or ""),
            "artifact_semantic_digests": dict(manifest.get("artifact_hashes") or {}),
            "counts": dict(source_counts),
            "inventory": dict(source_inventory),
        },
        "runtime_projection": {
            "semantic_digest": semantic_digest({name: files[name] for name in sorted(files)}),
            "files": files,
            "record_counts": {name: item["record_count"] for name, item in files.items()},
            "deployed_inventory": {
                "customer_allowed_count": len(partition["customer_allowed"]),
                "canonical_buy_now_count": len(partition["canonical_buy_now"]),
                "publishable_buy_now_count": len(partition["publishable_buy_now"]),
                "withheld_buy_now_count": len(partition["withheld_buy_now"]),
                **partition,
            },
            "required_tickers": sorted({str(value).upper() for value in required_tickers}),
            "withheld_customer_leakage": sorted(
                set(partition["customer_allowed"]) & set(source_inventory.get("withheld_buy_now") or ())
            ),
        },
        "expected_facts": dict(expected_facts),
    }


def validate_runtime_projection(
    payload: Any, manifest: Mapping[str, Any], *, artifact_name: str,
) -> tuple[bool, tuple[str, ...]]:
    contract = dict(manifest.get("runtime_projection_contract") or {})
    source = dict(contract.get("source_certification") or {})
    runtime = dict(contract.get("runtime_projection") or {})
    files = dict(runtime.get("files") or {})
    file_contract = dict(files.get(artifact_name) or {})
    failures: list[str] = []
    identity = dict(manifest.get("executor_candidate_identity") or {})
    if contract.get("version") != VERSION:
        failures.append("RUNTIME_PROJECTION_LINEAGE_ABSENT")
    if source.get("candidate_digest") != identity.get("candidate_digest"):
        failures.append("RUNTIME_PROJECTION_CANDIDATE_MISMATCH")
    if source.get("analytical_source_sha") != (manifest.get("source_commit_sha") or identity.get("source_sha")):
        failures.append("RUNTIME_PROJECTION_SOURCE_MISMATCH")
    if not source.get("publication_digest"):
        failures.append("RUNTIME_PROJECTION_PUBLICATION_IDENTITY_ABSENT")
    if semantic_digest(payload) != file_contract.get("semantic_sha256"):
        failures.append("RUNTIME_PROJECTION_DIGEST_MISMATCH")
    actual_count = len(payload) if isinstance(payload, list) else 1
    if actual_count != file_contract.get("record_count"):
        failures.append("RUNTIME_PROJECTION_COUNT_MISMATCH")
    rows = payload if isinstance(payload, list) else []
    tickers = {_ticker(row) for row in rows if isinstance(row, Mapping)}
    required = {str(value).upper() for value in runtime.get("required_tickers") or ()}
    if not required or not required.issubset(tickers):
        failures.append("RUNTIME_PROJECTION_REQUIRED_TICKERS_MISMATCH")
    if artifact_name == "full_evaluation_pool.json":
        partition = inventory_partition(rows)
        deployed = dict(runtime.get("deployed_inventory") or {})
        for key in ("canonical_buy_now", "publishable_buy_now", "withheld_buy_now"):
            if partition[key] != sorted(deployed.get(key) or ()):
                failures.append(f"RUNTIME_PROJECTION_{key.upper()}_MISMATCH")
        source_inventory = dict(source.get("inventory") or {})
        source_publishable = set(source_inventory.get("publishable_buy_now") or ())
        source_withheld = set(source_inventory.get("withheld_buy_now") or ())
        if not source_publishable.issubset(tickers):
            failures.append("RUNTIME_PROJECTION_PUBLISHABLE_INVENTORY_INCOMPLETE")
        if source_withheld & set(partition["customer_allowed"]):
            failures.append("RUNTIME_PROJECTION_WITHHELD_LEAKAGE")
    return not failures, tuple(dict.fromkeys(failures))


__all__ = [
    "VERSION", "build_runtime_projection_contract", "inventory_partition",
    "semantic_digest", "validate_runtime_projection",
]
