#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.buy_now_operational_preflight import run_preflight


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source-sha", required=True); p.add_argument("--checked-out-sha", required=True)
    p.add_argument("--raw-root", type=Path, required=True); p.add_argument("--checkpoint-root", type=Path, required=True)
    p.add_argument("--request-ceiling", type=int, required=True); p.add_argument("--timeout-minutes", type=int, required=True)
    p.add_argument("--require-credential", action="store_true"); p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = run_preflight(source_sha=a.source_sha, checked_out_sha=a.checked_out_sha,
        raw_root=a.raw_root, checkpoint_root=a.checkpoint_root,
        required_labels=("self-hosted", "Linux", "X64", "atlas-worker-1"),
        actual_labels=tuple(os.getenv("ATLAS_RUNNER_LABELS", "").split(",")),
        endpoint_allowlist=("/stock/candle", "/stock/split", "/stock/dividend"),
        request_ceiling=a.request_ceiling, concurrency=1, initial_rpm=60,
        automatic_retries=0, timeout_minutes=a.timeout_minutes,
        require_credential=a.require_credential,
        credential_present=bool(os.getenv("FINNHUB_API_KEY", "").strip()))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
