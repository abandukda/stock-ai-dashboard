#!/usr/bin/env python3
"""Run provider-free release monitoring and recovery closure drills."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from services.release_operational_closure import (
    monitoring_drill, persist_and_restore_evidence, publication_rollback_drill,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--restore-output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--trading-session", required=True)
    parser.add_argument("--cronitor-url-env", default="ATLAS_DAILY_BUY_NOW_CRONITOR_TEST_URL")
    parser.add_argument("--owner-email-env", default="ATLAS_DAILY_BUY_NOW_OWNER_EMAIL")
    args = parser.parse_args()
    monitor = monitoring_drill(
        cronitor_url=os.environ.get(args.cronitor_url_env, ""),
        owner_email=os.environ.get(args.owner_email_env, ""),
        run_id=args.run_id, source_sha=args.source_sha, trading_session=args.trading_session,
    )
    rollback = publication_rollback_drill()
    receipt = persist_and_restore_evidence(
        evidence={"monitoring_drill": monitor, "publication_rollback_drill": rollback},
        storage=args.output, restore=args.restore_output,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
