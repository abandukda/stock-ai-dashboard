#!/usr/bin/env python3
"""Exercise the exact live backfill state machine without provider credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.buy_now_history_backfill_execution import (
    BackfillExecutor, Response, authorization_token, build_claim_scope, canonical, scope_digest,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_transport(sessions: list[str]):
    timestamps = [int(datetime.combine(date.fromisoformat(v), time(21), tzinfo=timezone.utc).timestamp()) for v in sessions]
    def call(request):
        if request["endpoint"] == "/stock/candle":
            body = {"s": "ok", "t": timestamps, "o": [10.0] * len(timestamps),
                    "h": [11.0] * len(timestamps), "l": [9.0] * len(timestamps),
                    "c": [10.5] * len(timestamps), "v": [1000] * len(timestamps)}
        else:
            body = []
        return Response(200, json.dumps(body, sort_keys=True).encode(), {"x-atlas-fixture": "provider-free"})
    return call


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-source-sha", required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-zip-sha256", required=True)
    parser.add_argument("--package-sha256", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--scope-sha256", required=True)
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.getenv("FINNHUB_API_KEY", "").strip():
        raise PermissionError("BACKFILL_REHEARSAL_PROVIDER_CREDENTIAL_PRESENT")
    package = json.loads(args.package.read_text())
    plan = package["backfill_plan"]
    if _sha(args.package) != args.package_sha256:
        raise PermissionError("BACKFILL_REHEARSAL_PACKAGE_FILE_DIGEST_INVALID")
    if args.source_sha != plan.get("source_sha") or args.plan_sha256 != plan.get("plan_sha256"):
        raise PermissionError("BACKFILL_REHEARSAL_PLAN_IDENTITY_INVALID")
    if args.plan_sha256 != scope_digest({k: v for k, v in plan.items() if k != "plan_sha256"}):
        raise PermissionError("BACKFILL_REHEARSAL_PLAN_SELF_HASH_INVALID")
    if args.scope_sha256 != scope_digest(plan):
        raise PermissionError("BACKFILL_REHEARSAL_SCOPE_IDENTITY_INVALID")
    # The protected workflow verifies the immutable ZIP digest before extraction.
    # The package identity is the signed package value, not an inferred replacement.
    scope = build_claim_scope(
        claim_id=args.claim_id, source_sha=args.source_sha, workflow_source_sha=args.workflow_source_sha,
        artifact_id=args.artifact_id,
        artifact_zip_sha256=args.artifact_zip_sha256, package_sha256=args.package_sha256,
        plan_sha256=args.plan_sha256, scope_sha256=args.scope_sha256, plan=plan,
    )
    rehearsal_authority = f"ATLAS_BUY_NOW_BACKFILL_REHEARSE_ONCE:{args.source_sha}"
    if args.authorization == rehearsal_authority:
        args.authorization = authorization_token(scope)
    if args.authorization != authorization_token(scope):
        raise PermissionError("BACKFILL_REHEARSAL_AUTHORIZATION_INVALID")
    result = BackfillExecutor(
        state_root=args.state_root, raw_root=args.raw_root, scope=scope, plan=plan,
        token=args.authorization, execution_id=args.execution_id,
        transport=fixture_transport(list(plan["missing_sessions"])), provider_free=True,
    ).run()
    result.update({
        "evidence_classification": "PROVIDER_FREE_FIXTURE",
        "source_sha": args.source_sha, "workflow_source_sha": args.workflow_source_sha,
        "artifact_id": args.artifact_id,
        "artifact_zip_sha256": args.artifact_zip_sha256,
        "package_sha256": args.package_sha256, "plan_sha256": args.plan_sha256,
        "scope_sha256": args.scope_sha256, "publication_authorized": False,
        "claim_authorizes_live_acquisition": False,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(result))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
