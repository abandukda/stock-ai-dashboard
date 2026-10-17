#!/usr/bin/env python3
"""Execute one approved recovery suffix; never certifies or publishes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.buy_now_history_backfill_execution import (
    RecoveryBackfillExecutor, digest, recovery_authorization_token,
)
from scripts.inspect_buy_now_history_backfill_claim import inspect
from scripts.run_buy_now_history_backfill import FinnhubZeroRetryTransport


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--recovery-package", type=Path, required=True)
    p.add_argument("--original-package", type=Path, required=True)
    p.add_argument("--state-root", type=Path, required=True)
    p.add_argument("--raw-root", type=Path, required=True)
    p.add_argument("--workflow-source-sha", required=True)
    p.add_argument("--registered-source-sha", required=True)
    p.add_argument("--artifact-id", type=int, required=True)
    p.add_argument("--artifact-zip-sha256", required=True)
    p.add_argument("--package-file-sha256", required=True)
    p.add_argument("--package-sha256", required=True)
    p.add_argument("--plan-sha256", required=True)
    p.add_argument("--claim-id", required=True)
    p.add_argument("--claim-scope-sha256", required=True)
    p.add_argument("--execution-id", required=True)
    p.add_argument("--authorization", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    _write(a.output, {"status": "STARTED_FAIL_CLOSED",
                      "workflow_source_sha": a.workflow_source_sha,
                      "registered_source_sha": a.registered_source_sha,
                      "claim_id": a.claim_id,
                      "claim_scope_sha256": a.claim_scope_sha256,
                      "publication_writes": 0, "report_card_mutations": 0})
    key = os.getenv("FINNHUB_API_KEY", "").strip()
    expected_enablement = f"ENABLE_ATLAS_BACKFILL_RECOVERY_ONCE:{a.claim_id}"
    if not key or os.getenv("ATLAS_BACKFILL_RECOVERY_MANUAL_ACQUIRE_ENABLED") != expected_enablement:
        raise PermissionError("BACKFILL_RECOVERY_LIVE_OPERATION_DISABLED")
    if len(a.workflow_source_sha) != 40 or _sha(a.recovery_package) != a.package_file_sha256:
        raise PermissionError("BACKFILL_RECOVERY_PACKAGE_FILE_IDENTITY_INVALID")
    package = json.loads(a.recovery_package.read_text())
    embedded = package.get("package_sha256")
    if embedded != a.package_sha256 or embedded != digest({k: v for k, v in package.items() if k != "package_sha256"}):
        raise PermissionError("BACKFILL_RECOVERY_PACKAGE_IDENTITY_INVALID")
    plan, scope = package.get("recovery_plan") or {}, package.get("recovery_claim_scope") or {}
    checks = (
        package.get("status") == "PROVIDER_FREE_RECOVERY_VERIFIED",
        package.get("authorization_status") == "OWNER_APPROVAL_REQUIRED_NOT_CONSUMED",
        plan.get("registered_source_sha") == scope.get("registered_source_sha") == a.registered_source_sha,
        plan.get("plan_sha256") == scope.get("recovery_plan_sha256") == a.plan_sha256,
        scope.get("claim_id") == a.claim_id,
        scope.get("claim_scope_sha256") == a.claim_scope_sha256,
        a.artifact_id == 12083244989,
        a.artifact_zip_sha256 == "997a9395cdbb3f4c7eb208fcfb45bdd331daee1953baef0fa2726a85f05b69f9",
        a.authorization == recovery_authorization_token(scope),
    )
    if not all(checks):
        raise PermissionError("BACKFILL_RECOVERY_BOUND_AUTHORITY_INVALID")
    forensic = inspect(package=a.original_package, state_root=a.state_root,
                       raw_root=a.raw_root, claim_id=str(plan["original_claim_id"]),
                       expected_claim_scope=str(plan["original_claim_scope_sha256"]))
    manifests = plan.get("forensic_manifests") or {}
    if any((
        forensic.get("completed_receipts") != 2847,
        forensic.get("failed_response_requests") != 1,
        forensic.get("indeterminate_requests") != 0,
        forensic.get("not_attempted") != 1046,
        forensic.get("intent_manifest_sha256") != manifests.get("intent_manifest_sha256"),
        forensic.get("envelope_manifest_sha256") != manifests.get("envelope_manifest_sha256"),
        forensic.get("receipt_manifest_sha256") != manifests.get("receipt_manifest_sha256"),
    )):
        raise PermissionError("BACKFILL_RECOVERY_ORIGINAL_EVIDENCE_CHANGED")
    try:
        result = RecoveryBackfillExecutor(
            state_root=a.state_root, raw_root=a.raw_root, scope=scope, plan=plan,
            token=a.authorization, execution_id=a.execution_id,
            transport=FinnhubZeroRetryTransport(key, rpm=60),
        ).run()
    except BaseException as exc:
        claim_dir = a.state_root / "history_backfill_recovery_claims" / a.claim_id
        result = {"status": "FAILED_CLOSED", "terminal_error": type(exc).__name__,
                  "terminal_error_code": str(exc).split(":", 1)[0],
                  "durable_intents": len(list((claim_dir / "intents").glob("*.json"))),
                  "completed_receipts": len(list((claim_dir / "receipts").glob("*.json"))),
                  "workflow_source_sha": a.workflow_source_sha,
                  "registered_source_sha": a.registered_source_sha,
                  "claim_scope_sha256": a.claim_scope_sha256,
                  "publication_writes": 0, "report_card_mutations": 0}
        _write(a.output, result)
        print(json.dumps(result, sort_keys=True))
        raise
    result.update({"evidence_classification": "LIVE_FINNHUB_RECOVERY_RAW_EVIDENCE",
                   "publication_authorized": False,
                   "workflow_source_sha": a.workflow_source_sha,
                   "registered_source_sha": a.registered_source_sha,
                   "plan_sha256": a.plan_sha256, "artifact_id": a.artifact_id,
                   "artifact_zip_sha256": a.artifact_zip_sha256})
    _write(a.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
