#!/usr/bin/env python3
"""CLI orchestration for non-publishing Finnhub full-universe certification."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.finnhub_p_fcf_peer_certification import load_governed_classifications
from services.finnhub_canonical_authority import FinnhubCanonicalAdapter
from services.finnhub_full_universe_executor import (
    SHARD_SIZE, acquire_shard, aggregate_complete_run, build_run_identity,
    deterministic_canary, deterministic_shards,
)
from services.full_universe_brain_certification import load_frozen_universe


DEFAULT_UNIVERSE = Path("total_market_universe.json")


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _identity(universe: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    snapshot = args.evidence_snapshot or os.getenv("ATLAS_EVIDENCE_SNAPSHOT_AT")
    source_sha = args.source_sha or os.getenv("ATLAS_SOURCE_SHA")
    if not snapshot or not source_sha:
        raise ValueError("immutable evidence snapshot and source SHA are required")
    return build_run_identity(
        universe=universe, evidence_snapshot_at=snapshot, source_sha=source_sha,
    )


def _scope(universe: dict[str, Any], canary_size: int) -> dict[str, Any]:
    if not canary_size:
        return universe
    symbols = deterministic_canary(universe["supported_symbols"], canary_size)
    return {
        **universe, "supported_symbols": symbols, "supported_equity_count": len(symbols),
        "certification_scope": f"DETERMINISTIC_CANARY_{canary_size}",
        "parent_supported_equity_count": universe["supported_equity_count"],
    }


def plan(args: argparse.Namespace) -> int:
    frozen = load_frozen_universe(args.universe)
    scope = _scope(frozen, args.canary_size)
    identity = _identity(frozen, args)
    shards = deterministic_shards(scope["supported_symbols"], shard_size=args.shard_size)
    _write(args.output / "run_identity.json", identity)
    _write(args.output / "shard_manifest.json", {
        "run_identity_sha256": identity["run_identity_sha256"],
        "certification_scope": scope.get("certification_scope", "FULL_6033"),
        "expected_symbol_count": scope["supported_equity_count"],
        "shard_size": args.shard_size, "shard_count": len(shards), "shards": shards,
    })
    print(json.dumps({"shard_count": len(shards), "symbol_count": scope["supported_equity_count"]}))
    return 0


def run_shard(args: argparse.Namespace) -> int:
    frozen = load_frozen_universe(args.universe)
    scope = _scope(frozen, args.canary_size)
    identity = _identity(frozen, args)
    shards = deterministic_shards(scope["supported_symbols"], shard_size=args.shard_size)
    if args.shard_index < 0 or args.shard_index >= len(shards):
        raise ValueError("shard index outside deterministic manifest")
    catalog, _ = load_governed_classifications()
    payload = acquire_shard(
        adapter=FinnhubCanonicalAdapter(), shard=shards[args.shard_index],
        identity=identity, catalog=catalog, pace_seconds=max(0.0, args.pace_seconds),
        checkpoint_dir=args.checkpoint_dir,
    )
    _write(args.output / f"{shards[args.shard_index]['shard_id']}.json", payload)
    print(json.dumps({"shard": shards[args.shard_index]["shard_id"], **payload["provider_telemetry"]}))
    return 0


def aggregate(args: argparse.Namespace) -> int:
    frozen = load_frozen_universe(args.universe)
    scope = _scope(frozen, args.canary_size)
    identity = _identity(frozen, args)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.shards.glob("shard-*.json"))]
    report = aggregate_complete_run(
        universe=scope, identity=identity, shard_payloads=payloads,
        candidate_eligible=args.canary_size == 0,
        checkpoint_dir=args.checkpoint_dir,
    )
    _write(args.output / "full_universe_gate_report.json", report)
    _write(args.output / "checkpoint_summary.json", report["full_universe_completeness"])
    _write(args.output / "provider_call_telemetry.json", report["provider_call_telemetry"])
    _write(args.output / "evidence_inspector_coverage.json", report["evidence_inspector_coverage"])
    _write(args.output / "evidence_coverage_report.json", {
        "evidence_inspector": report["evidence_inspector_coverage"],
        "forward_route_leakage": report["forward_route_leakage"],
        "shadow_evidence_leakage": report["shadow_evidence_leakage"],
        "authority_violations": report["authority_violations"],
        "terminal_state_counts": report["full_universe_completeness"]["terminal_state_counts"],
    })
    _write(args.output / "valuation_route_distribution.json", report["valuation_route_distribution"])
    _write(args.output / "pillar_distribution.json", report["pillar_distribution"])
    _write(args.output / "action_distribution.json", report["action_distribution"])
    _write(args.output / "buy_now_provenance.json", report["buy_now_provenance"])
    _write(args.output / "determinism_report.json", report["determinism"])
    if report.get("immutable_candidate") is not None:
        _write(args.output / "immutable_candidate.json", report["immutable_candidate"])
    print(json.dumps({"state": report["state"], "symbols": report["full_universe_completeness"]["terminal_record_count"]}))
    return 0 if report["state"] in {"CANARY_PASS", "FINNHUB_FULL_UNIVERSE_EXECUTOR_CERTIFIED"} else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=("plan", "run-shard", "aggregate"))
    result.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--shards", type=Path)
    result.add_argument("--source-sha")
    result.add_argument("--evidence-snapshot")
    result.add_argument("--canary-size", type=int, default=0)
    result.add_argument("--shard-size", type=int, default=SHARD_SIZE)
    result.add_argument("--shard-index", type=int, default=0)
    result.add_argument("--pace-seconds", type=float, default=1.05)
    result.add_argument("--checkpoint-dir", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "plan":
        return plan(args)
    if args.command == "run-shard":
        return run_shard(args)
    if args.shards is None:
        raise ValueError("--shards is required for aggregate")
    return aggregate(args)


if __name__ == "__main__":
    raise SystemExit(main())
