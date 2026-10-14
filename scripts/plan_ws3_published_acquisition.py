"""Provider-free WS3 planning for the immutable customer-published population."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.plan_g6_enterprise_expansion import canonical_bytes, digest, published_tickers

CONTRACT = "ATLAS_WS3_PUBLISHED_ACQUISITION_PLAN_V1"
MEMBERSHIP_CONTRACT = "ATLAS_WS3_CUSTOMER_PUBLISHED_MEMBERSHIP_V1"
EXPECTED_COUNT = 1298
EXPECTED_MEMBERSHIP_SHA256 = "d6be219fdb882bb451f604b23d93f6eb2856a370140e70e895edfc0f2c2327f9"

DATASETS = (
    {"dataset": "annual_statements", "endpoint": "/stock/financials-reported", "params": {"freq": "annual"}, "refresh_hours": 720, "preserve_existing_11": True},
    {"dataset": "quarterly_statements", "endpoint": "/stock/financials-reported", "params": {"freq": "quarterly"}, "refresh_hours": 168, "preserve_existing_11": True},
    {"dataset": "earnings_actuals", "endpoint": "/stock/earnings", "params": {}, "refresh_hours": 24},
    {"dataset": "eps_estimates", "endpoint": "/stock/eps-estimate", "params": {"freq": "quarterly"}, "refresh_hours": 24},
    {"dataset": "revenue_estimates", "endpoint": "/stock/revenue-estimate", "params": {"freq": "quarterly"}, "refresh_hours": 24},
    {"dataset": "price_history", "endpoint": "/stock/candle", "params": {"resolution": "D", "window": "REGISTERED_BOUNDED_WINDOW"}, "refresh_hours": 24},
    {"dataset": "company_profile", "endpoint": "/stock/profile2", "params": {}, "refresh_hours": 720},
    {"dataset": "sec_filings", "endpoint": "/stock/filings", "params": {}, "refresh_hours": 24},
    {"dataset": "company_catalysts", "endpoint": "/company-news", "params": {"window": "REGISTERED_BOUNDED_WINDOW"}, "refresh_hours": 24},
)


def recover_membership(records: list[dict[str, Any]], manifest: dict[str, Any], *, source_file_sha256: str) -> dict[str, Any]:
    if manifest.get("workflow_run_id") != "37216506983" or manifest.get("customer_publication_count") != EXPECTED_COUNT:
        raise ValueError("SOURCE_MANIFEST_IDENTITY_MISMATCH")
    lineage = (manifest.get("artifact_lineage") or {}).get("full_evaluation_pool.json") or {}
    expected_semantic = (manifest.get("artifact_hashes") or {}).get("full_evaluation_pool.json")
    if not expected_semantic or lineage.get("semantic_sha256") != expected_semantic:
        raise ValueError("SOURCE_MANIFEST_LINEAGE_MISMATCH")
    tickers = published_tickers(records)
    membership_sha = digest(tickers)
    if len(tickers) != EXPECTED_COUNT or membership_sha != EXPECTED_MEMBERSHIP_SHA256:
        raise ValueError("PUBLISHED_MEMBERSHIP_MISMATCH")
    candidate = manifest.get("executor_candidate_identity") or {}
    for record in records:
        if (record.get("publication_certification") or {}).get("customer_publication_allowed") is True:
            if record.get("candidate_digest") != candidate.get("candidate_digest") or record.get("source_sha") != manifest.get("source_commit_sha"):
                raise ValueError("PUBLISHED_RECORD_LINEAGE_MISMATCH")
    body = {
        "contract": MEMBERSHIP_CONTRACT,
        "source_run_id": manifest["workflow_run_id"],
        "source_commit_sha": manifest["source_commit_sha"],
        "candidate_digest": candidate["candidate_digest"],
        "source_file_sha256": source_file_sha256,
        "source_semantic_sha256": expected_semantic,
        "membership_count": len(tickers),
        "membership_sha256": membership_sha,
        "tickers": tickers,
        "selection": "publication_certification.customer_publication_allowed == true",
        "immutable": True,
    }
    return {**body, "artifact_sha256": digest(body)}


def build_plan(membership: dict[str, Any], existing_tickers: list[str], *, batch_size: int = 25) -> dict[str, Any]:
    if membership.get("contract") != MEMBERSHIP_CONTRACT or membership.get("artifact_sha256") != digest({k: v for k, v in membership.items() if k != "artifact_sha256"}):
        raise ValueError("MEMBERSHIP_ARTIFACT_INVALID")
    tickers = membership["tickers"]
    existing = set(existing_tickers)
    if len(existing) != 11 or not existing.issubset(set(tickers)):
        raise ValueError("PRESERVED_SCOPE_INVALID")
    requests = []
    for spec in DATASETS:
        for ticker in tickers:
            if spec.get("preserve_existing_11") and ticker in existing:
                continue
            requests.append({"dataset": spec["dataset"], "method": "GET", "endpoint": spec["endpoint"], "ticker": ticker,
                             "parameters": {"symbol": ticker, **spec["params"]}, "refresh_hours": spec["refresh_hours"]})
    keys = [(r["dataset"], r["ticker"]) for r in requests]
    if len(keys) != len(set(keys)):
        raise ValueError("REQUEST_DUPLICATE")
    batches = []
    for offset in range(0, len(requests), batch_size):
        rows = requests[offset:offset + batch_size]; number = len(batches) + 1
        body = {"contract": "ATLAS_WS3_IMMUTABLE_BATCH_V1", "batch_id": f"WS3-B{number:04d}",
                "membership_artifact_sha256": membership["artifact_sha256"], "request_cap": batch_size,
                "request_count": len(rows), "requests": [{"ordinal": i + 1, **r} for i, r in enumerate(rows)],
                "pacing": {"concurrency": 1, "minimum_inter_request_seconds": 1.0, "rate_limit_rpm": 60, "retry_count": 0},
                "state": "AWAITING_EXACT_OWNER_AUTHORIZATION"}
        h = digest(body); batches.append({"manifest": body, "manifest_sha256": h,
            "required_authorization_token": f"AUTHORIZE_WS3_BATCH:WS3-B{number:04d}:{h}"})
    counts = {spec["dataset"]: sum(r["dataset"] == spec["dataset"] for r in requests) for spec in DATASETS}
    return {"contract": CONTRACT, "state": "PLANNING_ONLY_NO_PROVIDER_CALLS", "membership": {k: membership[k] for k in ("source_run_id","candidate_digest","membership_count","membership_sha256","artifact_sha256")},
            "preserved_existing": {"ticker_count": 11, "annual_periods": 147, "quarterly_periods": 447, "tickers": sorted(existing)},
            "request_counts": counts, "total_call_budget": len(requests), "minimum_pacing_minutes": len(requests) / 60,
            "batch_size": batch_size, "batch_count": len(batches), "batches": batches,
            "execution_policy": {"incremental_only": True, "raw_persistence_before_inspection": True, "per_response_sha256": True,
                "retry_count": 0, "stop_conditions": ["HTTP_429", "AUTH_OR_ENTITLEMENT_FAILURE", "HTTP_4XX_OR_5XX", "TIMEOUT_OR_PROVIDER_ERROR", "RATE_BUDGET_VIOLATION", "RAW_PERSISTENCE_FAILURE", "SCHEMA_OR_IDENTITY_MISMATCH", "DUPLICATE_REQUEST", "MEMBERSHIP_OR_MANIFEST_DRIFT"]},
            "provider_calls_performed": 0, "rating_authority": "UNCHANGED", "publication_authority": "UNCHANGED"}


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--records", type=Path, required=True); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--existing-tickers", type=Path, required=True); p.add_argument("--output-root", type=Path, required=True); a = p.parse_args()
    raw = a.records.read_bytes(); records = json.loads(raw); manifest = json.loads(a.manifest.read_text()); existing = json.loads(a.existing_tickers.read_text())
    membership = recover_membership(records, manifest, source_file_sha256=hashlib.sha256(raw).hexdigest()); plan = build_plan(membership, existing)
    a.output_root.mkdir(parents=True, exist_ok=True)
    (a.output_root / "ws3_customer_published_membership.json").write_bytes(canonical_bytes(membership) + b"\n")
    (a.output_root / "ws3_acquisition_plan.json").write_bytes(canonical_bytes(plan) + b"\n")
    for batch in plan["batches"]:
        (a.output_root / f"{batch['manifest']['batch_id']}.json").write_bytes(canonical_bytes(batch) + b"\n")
    print(json.dumps({"membership": membership["membership_count"], "calls": plan["total_call_budget"], "batches": plan["batch_count"]}, sort_keys=True))


if __name__ == "__main__": main()
