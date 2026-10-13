#!/usr/bin/env python3
"""Verify a gateway approval and emit a sanitized execution envelope."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.operations_gateway import GatewayApproval, execution_envelope, resolve_bounded_path, verify_scope


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--scope", type=Path, required=True)
    parser.add_argument("--scope-root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    approval = GatewayApproval.parse(json.loads(args.approval.read_text(encoding="utf-8")))
    scope_path = resolve_bounded_path(args.scope_root, str(args.scope)) if args.scope_root else args.scope
    scope = verify_scope(scope_path, approval)
    output = execution_envelope(approval=approval, scope=scope, run_id=args.run_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
