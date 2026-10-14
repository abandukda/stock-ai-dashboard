#!/usr/bin/env python3
"""Emit one sanitized lifecycle event to the configured external monitor."""
from __future__ import annotations

import argparse
import json
import os

from services.operational_heartbeat import CronitorHeartbeatAdapter, event_envelope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--trading-session", required=True)
    parser.add_argument("--publication-status", required=True)
    parser.add_argument("--failure-code", default="NONE")
    parser.add_argument("--recovery-action", default="NONE")
    parser.add_argument("--url-env", required=True)
    args = parser.parse_args()
    url = os.environ.get(args.url_env, "")
    if not url:
        raise RuntimeError("OPERATIONAL_HEARTBEAT_DESTINATION_MISSING")
    envelope = event_envelope(
        operation=args.operation, state=args.state, run_id=args.run_id,
        source_sha=args.source_sha, trading_session=args.trading_session,
        publication_status=args.publication_status, failure_code=args.failure_code,
        recovery_action=args.recovery_action,
    )
    receipt = CronitorHeartbeatAdapter(url).send(envelope)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
