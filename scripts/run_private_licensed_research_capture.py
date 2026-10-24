#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.licensed_research_private_execution import execute_private_capture


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("approval", "scope", "entitlement", "primary-root", "claim-root", "receipt"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--expected-packet-sha256", required=True)
    args = parser.parse_args()
    execute_private_capture(
        approval_path=args.approval, scope_path=args.scope, entitlement_path=args.entitlement,
        primary_root=args.primary_root, backup_root=args.backup_root, claim_root=args.claim_root,
        receipt_path=args.receipt, packet_path=args.packet,
        expected_packet_sha256=args.expected_packet_sha256,
        repository_root=ROOT,
        live_enabled=os.getenv("ATLAS_LICENSED_RESEARCH_PRIVATE_EXECUTION_ENABLED") == "true",
    )


if __name__ == "__main__":
    main()
