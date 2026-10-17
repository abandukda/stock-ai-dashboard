#!/usr/bin/env python3
"""Build a provider-free recovery package from one consumed backfill claim.

The original journal is read-only.  Preserved responses are verified in place;
the output grants no provider authority and contains only never-attempted slots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.inspect_buy_now_history_backfill_claim import inspect
from services.buy_now_history_backfill_execution import canonical, digest


def build_recovery(*, package: Path, state_root: Path, raw_root: Path,
                   claim_id: str, claim_scope_sha256: str,
                   registered_source_sha: str, recovery_claim_id: str) -> dict:
    if len(registered_source_sha) != 40:
        raise ValueError("BACKFILL_RECOVERY_REGISTERED_SOURCE_INVALID")
    forensic = inspect(package=package, state_root=state_root, raw_root=raw_root,
                       claim_id=claim_id, expected_claim_scope=claim_scope_sha256)
    expected = {
        "authorized_requests": 3894, "completed_receipts": 2847,
        "failed_response_requests": 1, "indeterminate_requests": 0,
        "not_attempted": 1046,
    }
    if any(forensic.get(key) != value for key, value in expected.items()):
        raise RuntimeError("BACKFILL_RECOVERY_FORENSIC_COUNTS_MISMATCH")
    failure = forensic.get("failure") or {}
    if (failure.get("ordinal"), failure.get("ticker"), failure.get("endpoint")) != (2848, "QRVO", "/stock/candle"):
        raise RuntimeError("BACKFILL_RECOVERY_FAILURE_IDENTITY_MISMATCH")
    if (failure.get("response_shape") or {}).get("classification") != "FINNHUB_NO_DATA":
        raise RuntimeError("BACKFILL_RECOVERY_TERMINAL_CLASSIFICATION_INVALID")

    original = json.loads(package.read_text(encoding="utf-8"))["backfill_plan"]
    claim_dir = state_root / "history_backfill_claims" / claim_id
    attempted = {int(path.stem) for path in (claim_dir / "intents").glob("*.json")}
    remaining = [row for row in original["requests"] if int(row["ordinal"]) not in attempted]
    if len(remaining) != 1046 or any(int(row["ordinal"]) <= 2848 for row in remaining):
        raise RuntimeError("BACKFILL_RECOVERY_REMAINING_SCOPE_INVALID")
    if len({int(row["ordinal"]) for row in remaining}) != 1046:
        raise RuntimeError("BACKFILL_RECOVERY_DUPLICATE_ORDINAL")

    plan = {
        "schema_version": "ATLAS_BUY_NOW_HISTORY_BACKFILL_RECOVERY_V1",
        "mode": "PROVIDER_FREE_RECOVERY_PLAN",
        "registered_source_sha": registered_source_sha,
        "original_claim_id": claim_id,
        "original_claim_scope_sha256": claim_scope_sha256,
        "original_source_sha": original["source_sha"],
        "original_plan_sha256": original["plan_sha256"],
        "original_request_count": 3894,
        "preserved_completed_receipts": 2847,
        "preserved_terminal_unavailable": [{
            "ordinal": 2848, "ticker": "QRVO", "reason": "FINNHUB_NO_DATA",
            "envelope_sha256": failure["envelope_sha256"],
            "raw_body_sha256": failure["response_shape"]["raw_body_sha256"],
        }],
        "forensic_manifests": {
            key: forensic[key] for key in (
                "intent_manifest_sha256", "envelope_manifest_sha256",
                "receipt_manifest_sha256",
            )
        },
        "requests": remaining,
        "request_count": len(remaining),
        "absolute_request_ceiling": len(remaining),
        "execution_policy": {
            "concurrency": 1, "rate_limit_rpm": 60, "automatic_retries": 0,
            "intent_before_transport": True, "raw_before_normalization": True,
            "indeterminate_requests_never_retried": True,
        },
        "provider_calls": 0,
        "publication_writes": 0,
        "report_card_mutations": 0,
    }
    plan["plan_sha256"] = digest(plan)
    scope = {
        "schema": "ATLAS_BUY_NOW_HISTORY_BACKFILL_RECOVERY_CLAIM_V1",
        "claim_id": recovery_claim_id,
        "registered_source_sha": registered_source_sha,
        "recovery_plan_sha256": plan["plan_sha256"],
        "original_claim_id": claim_id,
        "original_claim_scope_sha256": claim_scope_sha256,
        "request_count": 1046,
        "request_ordinals_sha256": hashlib.sha256(canonical([row["ordinal"] for row in remaining])).hexdigest(),
        "maximum_requests": 1046,
        "concurrency": 1,
        "initial_rpm": 60,
        "automatic_retries": 0,
    }
    scope["claim_scope_sha256"] = digest(scope)
    token = f"AUTHORIZE_ATLAS_BACKFILL_RECOVERY_CLAIM:{recovery_claim_id}:{scope['claim_scope_sha256']}"
    result = {
        "schema_version": "atlas.backfill-recovery-package.v1",
        "status": "PROVIDER_FREE_RECOVERY_VERIFIED",
        "provider_calls": 0, "publication_writes": 0, "report_card_mutations": 0,
        "recovery_plan": plan, "recovery_claim_scope": scope,
        "proposed_live_authorization_token": token,
        "authorization_status": "OWNER_APPROVAL_REQUIRED_NOT_CONSUMED",
    }
    result["package_sha256"] = digest(result)
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--state-root", type=Path, required=True)
    p.add_argument("--raw-root", type=Path, required=True)
    p.add_argument("--claim-id", required=True)
    p.add_argument("--claim-scope-sha256", required=True)
    p.add_argument("--registered-source-sha", required=True)
    p.add_argument("--recovery-claim-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = build_recovery(package=a.package, state_root=a.state_root,
                            raw_root=a.raw_root, claim_id=a.claim_id,
                            claim_scope_sha256=a.claim_scope_sha256,
                            registered_source_sha=a.registered_source_sha,
                            recovery_claim_id=a.recovery_claim_id)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "package_sha256", "provider_calls")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
