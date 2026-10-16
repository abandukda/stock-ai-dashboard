#!/usr/bin/env python3
"""Execute one approved, bounded Finnhub history backfill; never publishes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.buy_now_history_backfill_execution import (
    BackfillExecutor, Response, authorization_token, build_claim_scope, scope_digest,
)


class FinnhubZeroRetryTransport:
    def __init__(self, api_key: str, rpm: int = 60):
        import requests
        self.api_key = api_key
        self.minimum_interval = 60.0 / rpm
        self.last_started = 0.0
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=0)
        self.session.mount("https://", adapter)

    def __call__(self, request):
        wait = self.minimum_interval - (time.monotonic() - self.last_started)
        if wait > 0:
            time.sleep(wait)
        self.last_started = time.monotonic()
        response = self.session.get(
            "https://finnhub.io/api/v1" + str(request["endpoint"]),
            params={**dict(request["parameters"]), "token": self.api_key}, timeout=(10, 60),
        )
        # Never persist authentication-bearing request URLs or headers.
        return Response(response.status_code, response.content, {
            key: value for key, value in response.headers.items()
            if key.lower() in {"content-type", "content-length", "x-ratelimit-remaining"}
        })


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
    parser.add_argument("--claim-scope-sha256", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.getenv("FINNHUB_API_KEY", "").strip()
    expected_enablement = f"ENABLE_ATLAS_BACKFILL_ONCE:{args.claim_id}"
    if not key or os.getenv("ATLAS_BACKFILL_MANUAL_ACQUIRE_ENABLED") != expected_enablement:
        raise PermissionError("BACKFILL_LIVE_OPERATION_DISABLED")
    if hashlib.sha256(args.package.read_bytes()).hexdigest() != args.package_sha256:
        raise PermissionError("BACKFILL_PACKAGE_FILE_DIGEST_INVALID")
    package = json.loads(args.package.read_text()); plan = package["backfill_plan"]
    if args.source_sha != plan.get("source_sha") or args.plan_sha256 != plan.get("plan_sha256"):
        raise PermissionError("BACKFILL_PLAN_IDENTITY_INVALID")
    if args.plan_sha256 != scope_digest({k:v for k,v in plan.items() if k != "plan_sha256"}):
        raise PermissionError("BACKFILL_PLAN_SELF_HASH_INVALID")
    if args.scope_sha256 != scope_digest(plan):
        raise PermissionError("BACKFILL_SCOPE_IDENTITY_INVALID")
    scope = build_claim_scope(
        claim_id=args.claim_id, source_sha=args.source_sha, workflow_source_sha=args.workflow_source_sha,
        artifact_id=args.artifact_id,
        artifact_zip_sha256=args.artifact_zip_sha256, package_sha256=args.package_sha256,
        plan_sha256=args.plan_sha256, scope_sha256=args.scope_sha256, plan=plan,
    )
    if args.claim_scope_sha256 != scope["claim_scope_sha256"]:
        raise PermissionError("BACKFILL_CLAIM_SCOPE_IDENTITY_INVALID")
    if args.authorization != authorization_token(scope):
        raise PermissionError("BACKFILL_CLAIM_AUTHORIZATION_INVALID")
    result = BackfillExecutor(
        state_root=args.state_root, raw_root=args.raw_root, scope=scope, plan=plan,
        token=args.authorization, execution_id=args.execution_id,
        transport=FinnhubZeroRetryTransport(key, rpm=60), provider_free=False,
    ).run()
    result.update({"evidence_classification":"LIVE_FINNHUB_RAW_EVIDENCE",
                   "publication_authorized":False, "source_sha":args.source_sha,
                   "workflow_source_sha":args.workflow_source_sha,
                   "plan_sha256":args.plan_sha256, "scope_sha256":args.scope_sha256})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True)+"\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
