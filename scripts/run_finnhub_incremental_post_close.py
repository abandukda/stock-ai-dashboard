#!/usr/bin/env python3
"""Execute an exact incremental plan; never scores or publishes.

This entry point is intentionally unusable without both a plan-bound one-time
authorization string and the protected live-enablement switch.  Provider raw
responses are persisted by the adapter callback before normalization.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.finnhub_canonical_authority import FinnhubCanonicalAdapter
from services.finnhub_incremental_post_close import (
    DurableRawEvidenceSink, execute_incremental_plan,
)
from services.incremental_acquisition_claim import consume_claim, scope_payload


def require_manual_enablement(claim_id: str) -> None:
    """Require the workflow's claim-bound, one-run manual enablement value."""
    expected = f"ENABLE_ATLAS_INCREMENTAL_ONCE:{claim_id}"
    if os.getenv("ATLAS_INCREMENTAL_MANUAL_ACQUIRE_ENABLED") != expected:
        raise PermissionError("INCREMENTAL_LIVE_OPERATION_DISABLED")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--authorize-acquisition", required=True)
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--claim-scope-sha256", required=True)
    parser.add_argument("--claims-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    require_manual_enablement(args.claim_id)
    if not os.getenv("FINNHUB_API_KEY", "").strip():
        raise PermissionError("INCREMENTAL_FINNHUB_CREDENTIAL_UNAVAILABLE")
    scope = scope_payload(
        claim_id=args.claim_id, source_sha=args.source_sha,
        plan_sha256=str(plan.get("plan_sha256", "")),
        session=str(plan.get("session", "")),
    )
    if scope["claim_scope_sha256"] != args.claim_scope_sha256:
        raise PermissionError("INCREMENTAL_CLAIM_SCOPE_DIGEST_INVALID")
    consume_claim(claims_root=args.claims_root, scope=scope,
                  token=args.authorize_acquisition)
    parameters = json.loads(args.parameters.read_text(encoding="utf-8"))
    sink = DurableRawEvidenceSink(args.raw_root / "transport")
    adapter = FinnhubCanonicalAdapter(raw_evidence_sink=sink)
    result = execute_incremental_plan(
        plan=plan, adapter=adapter, raw_root=args.raw_root / "governed",
        checkpoint_path=args.checkpoint, parameters_by_family=parameters,
    )
    result["raw_transport_records"] = sink.count
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
