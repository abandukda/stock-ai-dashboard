#!/usr/bin/env python3
"""Capture certified publications into the internal prospective ledger.

No provider clients are imported or called by this command.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.prospective_report_card import ProspectiveLedger, capture_certified_publication, internal_dashboard


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _require_durable_path(path: Path, *, workspace: Path | None, temporary: Path | None, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_absolute():
        raise ValueError(f"{label}_MUST_BE_ABSOLUTE")
    for forbidden in (workspace, temporary):
        if forbidden and (resolved == forbidden or resolved.is_relative_to(forbidden)):
            raise ValueError(f"{label}_MUST_NOT_USE_EPHEMERAL_RUNNER_STORAGE")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--activation-timestamp", required=True)
    parser.add_argument("--expected-candidate-digest", required=True)
    parser.add_argument("--expected-publication-digest", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--maximum-evidence-age-hours", type=float, default=36.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve() if os.environ.get("GITHUB_WORKSPACE") else None
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve() if os.environ.get("RUNNER_TEMP") else None
    ledger_path = _require_durable_path(args.ledger, workspace=workspace, temporary=temporary, label="LEDGER")
    backup_root = _require_durable_path(args.backup_root, workspace=workspace, temporary=temporary, label="BACKUP_ROOT")
    if backup_root == ledger_path.parent or backup_root.is_relative_to(ledger_path.parent) or ledger_path.is_relative_to(backup_root):
        raise ValueError("PRIMARY_AND_BACKUP_STORAGE_MUST_BE_DISJOINT")
    manifest, rows = _json(args.manifest), _json(args.publication)
    identity = manifest.get("release_certification") or {}
    candidate = (manifest.get("executor_candidate_identity") or {}).get("candidate_digest") or identity.get("candidate_digest")
    actual = (str(candidate or ""), str(identity.get("publication_digest") or ""), str(identity.get("source_sha") or ""))
    expected = (args.expected_candidate_digest, args.expected_publication_digest, args.expected_source_sha)
    if actual != expected:
        raise ValueError(f"EXPECTED_PUBLICATION_IDENTITY_MISMATCH:{actual}")
    if not isinstance(rows, list):
        raise TypeError("PUBLICATION_ROWS_MUST_BE_LIST")

    # Exercise the exact capture contract against an ephemeral ledger first.  No
    # operational activation boundary may exist until at least one row passes
    # identity, publication, freshness, security, and price-provenance gates.
    with tempfile.TemporaryDirectory(prefix="atlas-report-card-preflight-") as directory:
        preflight_ledger = ProspectiveLedger(Path(directory) / "preflight.sqlite3")
        preflight_ledger.activate(activation_timestamp=args.activation_timestamp, now=now)
        preflight = capture_certified_publication(
            ledger=preflight_ledger, manifest=manifest, rows=rows, observed_at=now,
            maximum_evidence_age=timedelta(hours=args.maximum_evidence_age_hours),
        )
    if preflight.captured == 0:
        report = {
            "status": "NO_ELIGIBLE_SIGNAL", "activation_timestamp": None,
            "captured": 0, "idempotent": 0, "rejected": preflight.rejected,
            "signal_ids": [], "reasons": preflight.reasons,
            "ledger_path": str(ledger_path), "backup_path": None,
            "ledger_tip_digest": None, "provider_calls": 0, "reacquisition": "none",
            "customer_report_card_visible": False, "dashboard": None,
            "preflight": "PASS_NO_ELIGIBLE_SIGNAL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(args.output, 0o600)
        print(json.dumps(report, sort_keys=True))
        return 0

    ledger = ProspectiveLedger(ledger_path)
    activation = ledger.activate(activation_timestamp=args.activation_timestamp, now=now)
    result = capture_certified_publication(
        ledger=ledger, manifest=manifest, rows=rows, observed_at=now,
        maximum_evidence_age=timedelta(hours=args.maximum_evidence_age_hours),
    )
    backup = ledger.backup(backup_root, now=now)
    report = {
        "status": result.status, "activation_timestamp": activation,
        "captured": result.captured, "idempotent": result.idempotent, "rejected": result.rejected,
        "signal_ids": result.signal_ids, "reasons": result.reasons,
        "ledger_path": str(ledger_path), "backup_path": str(backup),
        "ledger_tip_digest": ledger.verify(), "provider_calls": 0, "reacquisition": "none",
        "customer_report_card_visible": False, "dashboard": internal_dashboard(ledger, authorized=True),
        "preflight": "PASS_ELIGIBLE_SIGNAL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"INTERNAL_PROSPECTIVE_TRACKING_BLOCKED:{type(exc).__name__}:{exc}", file=sys.stderr)
        raise
