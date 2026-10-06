#!/usr/bin/env python3
"""Bind exact Git production artifacts to an immutable certified source."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.runtime_projection_contract import build_runtime_projection_contract


ARTIFACTS = (
    "market_full_scan.json", "market_prescreen.json", "recovery_scan.json",
    "etf_scan.json", "total_market_universe.json", "market_scan_state.json",
    "discovery_candidate_pool.json", "full_evaluation_pool.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--publication-digest", required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.root / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expectations = json.loads(args.expectations.read_text(encoding="utf-8"))
    artifacts = {name: json.loads((args.root / name).read_text(encoding="utf-8")) for name in ARTIFACTS}
    identity = dict(manifest.get("executor_candidate_identity") or {})
    full_rows = artifacts["full_evaluation_pool.json"]
    facts = {}
    for ticker, expected in dict(expectations.get("expected_facts") or {}).items():
        row = next(item for item in full_rows if str(item.get("ticker") or "").upper() == ticker)
        certified = dict(row.get("certified_customer_evaluation") or {})
        decision = dict(certified.get("decision") or {})
        fields = dict(certified.get("fields") or {})
        facts[ticker] = {
            "action": decision.get("action"),
            "atlas_fair_value": dict(fields.get("atlas_fair_value") or {}).get("value"),
            "opportunity": decision.get("opportunity"),
            "decision_confidence": decision.get("decision_confidence"),
            "customer_publication_allowed": certified.get("customer_publication_allowed"),
            "evaluation_snapshot_id": dict(certified.get("digests") or {}).get("evaluation_snapshot_id"),
        }
        if facts[ticker] != expected:
            raise SystemExit(f"certified fact mismatch for {ticker}: {facts[ticker]!r} != {expected!r}")
    expected_identity = dict(expectations.get("identity") or {})
    actual_identity = {
        "candidate_digest": str(identity.get("candidate_digest") or ""),
        "publication_digest": args.publication_digest,
        "source_sha": str(manifest.get("source_commit_sha") or identity.get("source_sha") or ""),
        "evidence_snapshot_at": str(identity.get("generated_at") or manifest.get("generated_at") or ""),
    }
    if actual_identity != expected_identity:
        raise SystemExit(f"certified identity mismatch: {actual_identity!r} != {expected_identity!r}")
    manifest["runtime_projection_contract"] = build_runtime_projection_contract(
        manifest=manifest, artifacts=artifacts,
        candidate_digest=str(identity.get("candidate_digest") or ""),
        publication_digest=args.publication_digest,
        source_sha=str(manifest.get("source_commit_sha") or identity.get("source_sha") or ""),
        evidence_snapshot_at=str(identity.get("generated_at") or manifest.get("generated_at") or ""),
        source_counts={
            "universe_count": manifest.get("universe_count"),
            "customer_publication_count": manifest.get("customer_publication_count"),
            "certified_count": manifest.get("certified_count"),
            "withheld_count": manifest.get("withheld_count"),
        },
        expected_facts=facts,
        source_inventory=dict(expectations.get("source_inventory") or {}),
        required_tickers=[str(item.get("ticker") or item.get("symbol") or "") for item in full_rows],
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
