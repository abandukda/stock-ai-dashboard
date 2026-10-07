#!/usr/bin/env python3
"""Fail-closed certification closure for an existing Finnhub shard set.

This module deliberately has no provider client imports and no acquisition path.
It validates immutable shard payloads/manifests and the output of the existing
offline aggregator.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.finnhub_full_universe_executor import (
    deterministic_shards, shard_checkpoint_contract,
    validate_certified_shard_checkpoint,
)
from services.full_universe_brain_certification import load_frozen_universe


FINAL_STATE = "FINNHUB_FULL_UNIVERSE_CERTIFICATION_CLOSED_GREEN"
EXPECTED_SHARDS = 41
EXPECTED_SYMBOLS = 6033
EXPECTED_HISTORICAL_PROVIDER_CALLS = 36198
GOVERNED_RPM = 500.0
PARALLEL_WORKERS = 5
HISTORICAL_ACQUISITION_SECONDS = 5182.417
HISTORICAL_WORKFLOW_SECONDS = 7090.0
HISTORICAL_AGGREGATION_SECONDS = 1218.624
BURST_CEILING = 20.0


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


PROVIDER_CONFIGURATION_IDENTITY = _digest({
    "authority": "FINNHUB_CANONICAL",
    "core_adapter": "FinnhubCanonicalAdapter",
    "estimate_adapter": "FinnhubShadowAdapter:PAID_CORE_CERTIFICATION",
    "authorized_families": [
        "company_profile", "financial_statements", "basic_financials",
        "historical_ohlcv", "eps_estimates", "ebitda_estimates",
    ],
})


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_evidence(
    *, evidence_root: Path, universe_path: Path, source_run_id: str,
    source_sha: str, source_run_identity: str, output: Path,
) -> dict[str, Any]:
    if not source_run_id.strip() or not source_sha.strip() or not source_run_identity.strip():
        raise ValueError("explicit source run ID, source SHA, and source run identity are required")
    universe = load_frozen_universe(universe_path)
    shards = deterministic_shards(universe["supported_symbols"])
    if len(shards) != EXPECTED_SHARDS or universe["supported_equity_count"] != EXPECTED_SYMBOLS:
        raise ValueError("governed universe is not the expected 41-shard/6033-symbol contract")

    payload_paths = sorted(evidence_root.glob("shard-*.json"))
    manifest_paths = sorted((evidence_root / "certification").glob("shard-*.checkpoint.json"))
    if len(payload_paths) != EXPECTED_SHARDS or len(manifest_paths) != EXPECTED_SHARDS:
        raise ValueError("closure requires exactly 41 payloads and 41 certified manifests")
    if len({path.name for path in payload_paths}) != EXPECTED_SHARDS:
        raise ValueError("duplicate shard payload artifact")
    if len({path.name for path in manifest_paths}) != EXPECTED_SHARDS:
        raise ValueError("duplicate certified shard manifest")

    first = _load(payload_paths[0])
    identity = dict(first.get("run_identity") or {})
    if identity.get("source_sha") != source_sha:
        raise ValueError("evidence source SHA mismatch")
    if identity.get("run_identity_sha256") != source_run_identity:
        raise ValueError("evidence source run identity mismatch")
    payload_by_name = {path.stem: path for path in payload_paths}
    manifest_by_name = {
        path.name.removesuffix(".checkpoint.json"): path for path in manifest_paths
    }
    for shard in shards:
        shard_id = str(shard["shard_id"])
        payload_path = payload_by_name.get(shard_id)
        manifest_path = manifest_by_name.get(shard_id)
        if payload_path is None or manifest_path is None:
            raise ValueError(f"certified shard artifact missing for {shard_id}")
        raw = payload_path.read_bytes()
        contract = shard_checkpoint_contract(
            identity=identity, shard=shard,
            provider_configuration_identity=PROVIDER_CONFIGURATION_IDENTITY,
            global_requests_per_minute=GOVERNED_RPM,
            burst_ceiling=BURST_CEILING,
            parallel_workers=PARALLEL_WORKERS,
        )
        validate_certified_shard_checkpoint(
            payload=json.loads(raw), artifact_digest=hashlib.sha256(raw).hexdigest(),
            checkpoint=_load(manifest_path), expected_contract=contract,
        )

    symbols = []
    for path in payload_paths:
        payload = _load(path)
        shard_identity = dict(payload.get("run_identity") or {})
        if shard_identity != identity:
            raise ValueError("shard immutable run identity mismatch")
        symbols.extend(str(row.get("ticker") or "").upper() for row in payload.get("records") or ())
    expected = list(universe["supported_symbols"])
    if len(symbols) != EXPECTED_SYMBOLS or len(set(symbols)) != EXPECTED_SYMBOLS:
        raise ValueError("closure symbol completeness or uniqueness failure")
    if sorted(symbols) != sorted(expected):
        raise ValueError("closure symbol set mismatch")

    summary = {
        "status": "PASS",
        "evidence_source_run_id": source_run_id,
        "evidence_source_sha": source_sha,
        "evidence_source_run_identity": source_run_identity,
        "evidence_snapshot_at": identity.get("evidence_snapshot_at"),
        "certified_payloads": EXPECTED_SHARDS,
        "certified_manifests": EXPECTED_SHARDS,
        "certified_symbols": EXPECTED_SYMBOLS,
        "missing": 0,
        "duplicates": 0,
        "unexpected": 0,
        "closure_provider_calls": 0,
    }
    _write(output, summary)
    return summary


def finalize(
    *, gate_report_path: Path, profile_path: Path, preflight_path: Path,
    execution_sha: str, expected_candidate_digest: str,
    expected_publication_digest: str, repository_integrity: str,
    closure_started_epoch: float, output: Path,
) -> dict[str, Any]:
    preflight = _load(preflight_path)
    gate = _load(gate_report_path)
    profile = _load(profile_path)
    determinism = dict(gate.get("determinism") or {})
    diff = dict(determinism.get("structural_diff") or {})
    completeness = dict(gate.get("full_universe_completeness") or {})
    provider = dict(gate.get("provider_call_telemetry") or {})
    candidate = str((gate.get("determinism") or {}).get("first_digest") or "")
    publication = str(gate.get("publication_bundle_digest") or "")

    checks = {
        "preflight": preflight.get("status") == "PASS",
        "payloads": preflight.get("certified_payloads") == EXPECTED_SHARDS,
        "manifests": preflight.get("certified_manifests") == EXPECTED_SHARDS,
        "symbols": completeness.get("terminal_record_count") == EXPECTED_SYMBOLS,
        "missing": not completeness.get("missing_symbols"),
        "duplicates": not completeness.get("duplicate_symbols"),
        "unexpected": not completeness.get("unexpected_symbols"),
        "unexplained_absence": not completeness.get("unexplained_provider_absence"),
        "historical_provider_calls": provider.get("provider_calls") == EXPECTED_HISTORICAL_PROVIDER_CALLS,
        "closure_provider_calls": profile.get("provider_calls_during_aggregation") == 0,
        "determinism": determinism.get("status") == "PASS",
        "records_compared": diff.get("records_compared") == EXPECTED_SYMBOLS,
        "analytical_mismatches": diff.get("analytical_mismatch_count") == 0,
        "order_only_mismatches": diff.get("order_only_mismatch_count") == 0,
        "action_differences": (diff.get("classifications") or {}).get("ACTION_DIFFERENCE") == 0,
        "numerical_differences": (diff.get("classifications") or {}).get("NUMERICAL_DIFFERENCE") == 0,
        "authority_violations": gate.get("authority_violations") == 0,
        "evidence_inspector": (gate.get("evidence_inspector_coverage") or {}).get("status") == "PASS",
        "forward_leakage": gate.get("forward_route_leakage") is False,
        "shadow_leakage": gate.get("shadow_evidence_leakage") is False,
        "candidate_digest": candidate == expected_candidate_digest,
        "publication_digest": publication == expected_publication_digest,
        "publication_gate": gate.get("new_full_universe_candidate_certified") is True,
        "repository_integrity": repository_integrity == "PASS",
    }
    if not all(checks.values()):
        failed = sorted(key for key, passed in checks.items() if not passed)
        raise ValueError("closure certification failed: " + ",".join(failed))

    result = {
        "classification": FINAL_STATE,
        "execution_sha": execution_sha,
        "evidence_source_run_id": preflight["evidence_source_run_id"],
        "evidence_source_sha": preflight["evidence_source_sha"],
        "evidence_source_run_identity": preflight["evidence_source_run_identity"],
        "checkpoint_validation": {"payloads": 41, "manifests": 41, "status": "PASS"},
        "symbol_completeness": {"expected": 6033, "actual": 6033, "status": "PASS"},
        "closure_provider_calls": 0,
        "historical_provider_calls": EXPECTED_HISTORICAL_PROVIDER_CALLS,
        "determinism": "PASS",
        "analytical_mismatches": 0,
        "candidate_digest": candidate,
        "candidate_digest_match": True,
        "publication_digest": publication,
        "publication_digest_match": True,
        "repository_integrity": "PASS",
        "historical_performance": {
            "fresh_provider_acquisition_seconds": HISTORICAL_ACQUISITION_SECONDS,
            "fresh_provider_acquisition_90m_objective": "PASS",
            "historical_aggregation_seconds": HISTORICAL_AGGREGATION_SECONDS,
            "historical_full_workflow_seconds_approximate": HISTORICAL_WORKFLOW_SECONDS,
            "end_to_end_workflow_90m": "NOT_PROVEN",
        },
        "zero_provider_closure_runtime_seconds": round(time.time() - closure_started_epoch, 3),
        "workflow_conclusion": "GREEN",
        "checks": checks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write(output, result)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-evidence")
    validate.add_argument("--evidence-root", type=Path, required=True)
    validate.add_argument("--universe", type=Path, required=True)
    validate.add_argument("--source-run-id", required=True)
    validate.add_argument("--source-sha", required=True)
    validate.add_argument("--source-run-identity", required=True)
    validate.add_argument("--output", type=Path, required=True)
    finish = sub.add_parser("finalize")
    finish.add_argument("--gate-report", type=Path, required=True)
    finish.add_argument("--aggregation-profile", type=Path, required=True)
    finish.add_argument("--preflight", type=Path, required=True)
    finish.add_argument("--execution-sha", required=True)
    finish.add_argument("--expected-candidate-digest", required=True)
    finish.add_argument("--expected-publication-digest", required=True)
    finish.add_argument("--repository-integrity", required=True)
    finish.add_argument("--closure-started-epoch", type=float, required=True)
    finish.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "validate-evidence":
        validate_evidence(
            evidence_root=args.evidence_root, universe_path=args.universe,
            source_run_id=args.source_run_id, source_sha=args.source_sha,
            source_run_identity=args.source_run_identity, output=args.output,
        )
    else:
        finalize(
            gate_report_path=args.gate_report, profile_path=args.aggregation_profile,
            preflight_path=args.preflight, execution_sha=args.execution_sha,
            expected_candidate_digest=args.expected_candidate_digest,
            expected_publication_digest=args.expected_publication_digest,
            repository_integrity=args.repository_integrity,
            closure_started_epoch=args.closure_started_epoch, output=args.output,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
