"""Refresh non-scoring Twelve context for the currently published equities only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from services.context_evidence import context_coverage, enrich_published_context


PROTECTED_ROW_FIELDS = (
    "canonical_investment_evaluation", "production_rank", "rank", "conviction",
    "trade_plan", "fair_value", "atlas_fair_value", "expected_return",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def protected_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    protected = [
        {
            "ticker": str(row.get("ticker") or row.get("symbol") or "").upper(),
            **{field: row.get(field) for field in PROTECTED_ROW_FIELDS},
        }
        for row in rows
    ]
    return _digest(protected)


def refresh_rows(
    rows: Sequence[Mapping[str, Any]], **acquisition_kwargs: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(rows) != 150:
        raise RuntimeError(f"CONTEXT_REFRESH_REQUIRES_CURRENT_TOP_150:{len(rows)}")
    tickers_before = tuple(str(row.get("ticker") or row.get("symbol") or "").upper() for row in rows)
    before = protected_digest(rows)
    refreshed, telemetry = enrich_published_context(rows, **acquisition_kwargs)
    after = protected_digest(refreshed)
    tickers_after = tuple(str(row.get("ticker") or row.get("symbol") or "").upper() for row in refreshed)
    if tickers_before != tickers_after:
        raise RuntimeError("CONTEXT_REFRESH_CHANGED_PUBLISHED_ORDER")
    if before != after:
        raise RuntimeError("CONTEXT_REFRESH_CHANGED_CANONICAL_DECISIONS")
    report = {
        "version": "ATLAS_PUBLISHED_CONTEXT_REFRESH_V1",
        "status": "PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": os.getenv("GITHUB_SHA") or os.getenv("ATLAS_SOURCE_COMMIT_SHA") or "LOCAL_WORKTREE",
        "population": len(refreshed),
        "provider": "TWELVE_DATA",
        "provider_calls": telemetry.get("provider_calls", 0),
        "successful_calls": telemetry.get("successful_calls", 0),
        "endpoint_success": telemetry.get("endpoint_success") or {},
        "canonical_decision_digest_before": before,
        "canonical_decision_digest_after": after,
        "canonical_decisions_unchanged": before == after,
        "coverage": context_coverage(refreshed),
    }
    return refreshed, report


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, default=str)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=Path("market_full_scan.json"))
    parser.add_argument("--manifest", type=Path, default=Path("publication_manifest.json"))
    parser.add_argument("--report", type=Path, default=Path("context_refresh_report.json"))
    args = parser.parse_args()
    rows = json.loads(args.artifact.read_text(encoding="utf-8"))
    refreshed, report = refresh_rows(rows)
    if report["provider_calls"] <= 0:
        raise RuntimeError("CONTEXT_REFRESH_PROVIDER_CALLS_ZERO")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest.setdefault("artifact_hashes", {})[args.artifact.name] = _digest(refreshed)
    manifest["context_refresh"] = report
    _write_json_atomic(args.artifact, refreshed)
    _write_json_atomic(args.manifest, manifest)
    _write_json_atomic(args.report, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
