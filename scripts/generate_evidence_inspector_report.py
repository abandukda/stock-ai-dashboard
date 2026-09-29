#!/usr/bin/env python3
"""Generate an internal parameter-coverage report from persisted evaluations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from services.evidence_inspector import coverage_report, inventory


def _evaluations(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("evaluations") or []
    output = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        evaluation = row.get("canonical_investment_evaluation")
        if isinstance(evaluation, Mapping):
            output.append({**dict(evaluation), "ticker": evaluation.get("ticker") or row.get("ticker")})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("market_full_scan.json"))
    parser.add_argument("--output", type=Path, default=Path("audit_results/evidence_inspector/parameter_coverage.json"))
    parser.add_argument("--universe", type=Path, default=Path("total_market_universe.json"))
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = coverage_report(_evaluations(payload))
    universe_payload = json.loads(args.universe.read_text(encoding="utf-8"))
    supported_count = int(
        (universe_payload.get("governed_pre_acquisition_summary") or {}).get("us_stock_universe_count") or 0
    )
    if supported_count <= 0:
        raise ValueError("frozen universe does not declare a governed stock count")
    report["expected_supported_symbol_count"] = supported_count
    report["accounted_symbol_count"] = report["symbol_count"]
    report["unaccounted_symbol_count"] = max(0, supported_count - report["symbol_count"])
    report["universe_sha256"] = hashlib.sha256(args.universe.read_bytes()).hexdigest()
    if report["unaccounted_symbol_count"]:
        report["status"] = "PARAMETER_VISIBILITY_INCOMPLETE"
        report["full_universe_blocker"] = "PERSISTED_EVALUATIONS_DO_NOT_COVER_FROZEN_SUPPORTED_UNIVERSE"
    report["parameter_inventory"] = inventory()
    report["source_artifact"] = str(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "symbol_count", "canonical_parameter_count")}))
    return 0 if report["status"] == "PARAMETER_VISIBILITY_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
