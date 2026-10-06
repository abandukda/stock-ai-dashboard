#!/usr/bin/env python3
"""CLI orchestration for non-publishing Finnhub full-universe certification."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time
from typing import Any, Mapping

import ijson

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.finnhub_p_fcf_peer_certification import load_governed_classifications
from services.finnhub_canonical_authority import FinnhubCanonicalAdapter
from services.finnhub_shadow_provider import FINNHUB_PAID_CORE_CERTIFICATION_LICENSE, FinnhubShadowAdapter
from services.finnhub_full_universe_executor import (
    SHARD_SIZE, acquire_shard, aggregate_complete_run, build_run_identity, build_single_immutable_candidate,
    combine_evaluation_results, deterministic_canary, deterministic_shards,
    evaluate_records, validate_shards, compare_replay_candidates,
    _buy_now_report, _gate_diagnostics, _method_distribution,
    _pillar_distribution, _publication_diagnostics, _route_distribution,
)
from services.executor_publication_bridge import build_publication_bundle, build_publication_bundle_streaming
from services.finnhub_rate_governance import build_parallel_rate_governor
from services.full_universe_brain_certification import (
    certify_complete_run, compare_deterministic_candidates, load_frozen_universe,
)


DEFAULT_UNIVERSE = Path("total_market_universe.json")
AGGREGATION_PHASE_VERSION = "ATLAS_FULL_UNIVERSE_AGGREGATION_PHASES_V1"
PROHIBITED_CHECKPOINT_KEYS = {
    "api_key", "authentication", "authorization", "headers", "news_text",
    "raw_content", "raw_payload", "raw_response", "secret", "source_excerpt",
    "transcript", "transcript_body", "filing_text", "prepared_remarks", "qa_segments",
}


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Checkpoints are machine-readable recovery artifacts; compact encoding avoids
    # millions of indentation fragments for the 6,033-record candidate while
    # preserving the exact logical payload and its separately governed digest.
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), default=str)
    with path.open("w", encoding="utf-8") as handle:
        handle.writelines(encoder.iterencode(payload))
        handle.write("\n")


def _write_publication_bundle(output: Path, publication_bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Write each distinct canonical payload once and hard-link exact duplicates."""
    output.mkdir(parents=True, exist_ok=True)
    physical_by_identity: dict[int, Path] = {}
    logical_bytes = 0
    physical_bytes = 0
    for name, payload in publication_bundle["artifacts"].items():
        target = output / name
        existing = physical_by_identity.get(id(payload))
        if existing is not None:
            if target.exists():
                target.unlink()
            os.link(existing, target)
            size = existing.stat().st_size
        else:
            _write(target, payload)
            physical_by_identity[id(payload)] = target
            size = target.stat().st_size
            physical_bytes += size
        logical_bytes += size
    manifest_path = output / "publication_manifest.json"
    _write(manifest_path, publication_bundle["manifest"])
    manifest_size = manifest_path.stat().st_size
    return {
        "logical_bytes": logical_bytes + manifest_size,
        "physical_bytes_written": physical_bytes + manifest_size,
        "deduplicated_bytes": logical_bytes - physical_bytes,
    }


def _digest(payload: Any) -> str:
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), default=str)
    for chunk in encoder.iterencode(payload):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


def _profiled(phase: str, operation: Any) -> tuple[Any, dict[str, Any]]:
    started = time.monotonic()
    result = operation()
    return result, {
        "phase": phase,
        "duration_seconds": round(time.monotonic() - started, 6),
        "max_rss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                          if sys.platform == "darwin"
                          else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    }


def _checkpoint(*, checkpoint_type: str, identity: Mapping[str, Any], universe: Mapping[str, Any],
                shard_digests: list[dict[str, str]], payload: Mapping[str, Any],
                phase_metrics: list[Mapping[str, Any]]) -> dict[str, Any]:
    body = {
        "checkpoint_type": checkpoint_type,
        "phase_version": AGGREGATION_PHASE_VERSION,
        "source_sha": identity["source_sha"],
        "universe_sha": universe["source_sha256"],
        "evidence_snapshot_timestamp": identity["evidence_snapshot_at"],
        "run_identity_sha256": identity["run_identity_sha256"],
        "shard_artifact_digests": shard_digests,
        "provider_calls_during_aggregation": 0,
        "phase_metrics": list(phase_metrics),
        "payload": dict(payload),
    }
    return {**body, "content_digest": _digest(body)}


def _load_checkpoint(path: Path, expected_type: str) -> dict[str, Any]:
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    if checkpoint.get("checkpoint_type") != expected_type:
        raise ValueError(f"expected {expected_type} checkpoint")
    if checkpoint.get("phase_version") != AGGREGATION_PHASE_VERSION:
        raise ValueError("aggregation checkpoint phase version mismatch")
    digest = checkpoint.pop("content_digest", None)
    if digest != _digest(checkpoint):
        raise ValueError("aggregation checkpoint content digest mismatch")
    checkpoint["content_digest"] = digest
    return checkpoint


def _shard_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("shard-*.json"))


def _load_verified_shards(directory: Path, inventory: list[Mapping[str, str]] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    paths = _shard_files(directory)
    digests = [{"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    if inventory is not None and digests != [dict(item) for item in inventory]:
        raise ValueError("shard artifact inventory or digest mismatch")
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths], digests


def _verify_shards_without_loading_payloads(
    directory: Path, inventory: list[Mapping[str, str]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Verify every immutable shard while retaining only the first shard identity."""
    paths = _shard_files(directory)
    digests = [{"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths]
    if digests != [dict(item) for item in inventory]:
        raise ValueError("shard artifact inventory or digest mismatch")
    if not paths:
        raise ValueError("immutable source shard set is empty")
    return json.loads(paths[0].read_text(encoding="utf-8")), digests


def _assert_checkpoint_safe(value: Any, path: str = "checkpoint") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in PROHIBITED_CHECKPOINT_KEYS:
                raise ValueError(f"prohibited checkpoint content at {path}.{key}")
            _assert_checkpoint_safe(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_checkpoint_safe(item, f"{path}[{index}]")


def _peer_component_chunks(records: list[Mapping[str, Any]], chunk_count: int) -> list[list[dict[str, Any]]]:
    """Partition records without splitting any production peer-comparison component."""
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    record_nodes: list[tuple[dict[str, Any], str]] = []
    for position, original in enumerate(records):
        record = dict(original)
        row = record.get("row") or {}
        sector = str(row.get("sector") or "").strip().lower()
        industry = str(row.get("industry") or "").strip().lower()
        nodes = ([f"sector:{sector}"] if sector else []) + ([f"industry:{industry}"] if industry else [])
        if not nodes:
            nodes = [f"isolated:{position}:{record.get('ticker')}"]
        for node in nodes[1:]:
            union(nodes[0], node)
        record_nodes.append((record, nodes[0]))
    components: dict[str, list[dict[str, Any]]] = {}
    for record, node in record_nodes:
        components.setdefault(find(node), []).append(record)
    chunks: list[list[dict[str, Any]]] = [[] for _ in range(chunk_count)]
    for component in sorted(components.values(), key=lambda values: (-len(values), str(values[0].get("ticker")))):
        target = min(range(chunk_count), key=lambda index: (len(chunks[index]), index))
        chunks[target].extend(component)
    return [sorted(chunk, key=lambda item: str(item.get("ticker"))) for chunk in chunks]


def _identity(universe: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    snapshot = args.evidence_snapshot or os.getenv("ATLAS_EVIDENCE_SNAPSHOT_AT")
    source_sha = args.source_sha or os.getenv("ATLAS_SOURCE_SHA")
    if not snapshot or not source_sha:
        raise ValueError("immutable evidence snapshot and source SHA are required")
    return build_run_identity(
        universe=universe, evidence_snapshot_at=snapshot, source_sha=source_sha,
    )


def _recovery_identity(shards: list[Mapping[str, Any]], universe: Mapping[str, Any],
                       args: argparse.Namespace) -> dict[str, Any]:
    if not shards or not isinstance(shards[0].get("run_identity"), Mapping):
        raise ValueError("source shards do not contain an immutable run identity")
    identity = dict(shards[0]["run_identity"])
    expected_source_sha = args.source_sha or os.getenv("ATLAS_SOURCE_SHA")
    if identity.get("source_sha") != expected_source_sha:
        raise ValueError("source shard SHA does not match authorized recovery source")
    if args.evidence_snapshot and identity.get("evidence_snapshot_at") != args.evidence_snapshot:
        raise ValueError("source shard snapshot does not match explicitly requested recovery snapshot")
    if identity.get("universe_sha256") != universe["source_sha256"]:
        raise ValueError("source shard universe does not match frozen universe")
    if identity.get("supported_equity_count") != universe["supported_equity_count"]:
        raise ValueError("source shard governed count does not match frozen universe")
    return identity


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
    configured_rpm = args.global_requests_per_minute
    if configured_rpm is None:
        raw_rpm = os.getenv("ATLAS_FINNHUB_GLOBAL_REQUESTS_PER_MINUTE", "").strip()
        configured_rpm = float(raw_rpm) if raw_rpm else None
    rate_governor = build_parallel_rate_governor(
        global_requests_per_minute=configured_rpm,
        parallel_workers=args.parallel_workers,
        shard_index=args.shard_index,
    )
    payload = acquire_shard(
        adapter=FinnhubCanonicalAdapter(), shard=shards[args.shard_index],
        estimate_adapter=FinnhubShadowAdapter(license_class=FINNHUB_PAID_CORE_CERTIFICATION_LICENSE),
        identity=identity, catalog=catalog, pace_seconds=max(0.0, args.pace_seconds),
        rate_governor=rate_governor,
        checkpoint_dir=args.checkpoint_dir,
        strict_provider_health=args.strict_provider_health,
    )
    _write(args.output / f"{shards[args.shard_index]['shard_id']}.json", payload)
    print(json.dumps({"shard": shards[args.shard_index]["shard_id"], **payload["provider_telemetry"]}))
    return 0


def aggregate(args: argparse.Namespace) -> int:
    aggregate_started = time.monotonic()
    cpu_started = time.process_time()
    frozen = load_frozen_universe(args.universe)
    scope = _scope(frozen, args.canary_size)
    identity = _identity(frozen, args)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.shards.glob("shard-*.json"))]
    report = aggregate_complete_run(
        universe=scope, identity=identity, shard_payloads=payloads,
        candidate_eligible=args.canary_size == 0,
        checkpoint_dir=args.checkpoint_dir,
    )
    candidates = report.pop("determinism_candidates", {})
    publication_bundle = report.pop("publication_bundle", None)
    candidate = report.pop("immutable_candidate", None)
    if candidates:
        _write(args.output / "determinism_candidate_digests.json", {
            "status": report["determinism"].get("status"),
            "first_candidate_digest": (candidates.get("first") or {}).get("candidate_digest"),
            "second_candidate_digest": (candidates.get("second") or {}).get("candidate_digest"),
            "structural_diff": report["determinism"].get("structural_diff"),
        })
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
    _write(args.output / "valuation_method_distribution.json", report["valuation_method_distribution"])
    _write(args.output / "gate_diagnostics.json", report["gate_diagnostics"])
    _write(args.output / "publication_diagnostics.json", report["publication_diagnostics"])
    _write(args.output / "pillar_distribution.json", report["pillar_distribution"])
    _write(args.output / "action_distribution.json", report["action_distribution"])
    _write(args.output / "buy_now_provenance.json", report["buy_now_provenance"])
    _write(args.output / "determinism_report.json", report["determinism"])
    if candidate is not None:
        _write(args.output / "immutable_candidate.json", candidate)
    publication_io = {"logical_bytes": 0, "physical_bytes_written": 0, "deduplicated_bytes": 0}
    if publication_bundle is not None:
        publication_io = _write_publication_bundle(args.output / "publication_bundle", publication_bundle)
    _write(args.output / "aggregation_profile.json", {
        "phase_metrics": report.get("aggregation_phase_metrics") or [],
        "total_wall_seconds": round(time.monotonic() - aggregate_started, 6),
        "total_cpu_seconds": round(time.process_time() - cpu_started, 6),
        "max_rss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                          if sys.platform == "darwin"
                          else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "shard_input_bytes": sum(path.stat().st_size for path in sorted(args.shards.glob("shard-*.json"))),
        "candidate_bytes_written": (args.output / "immutable_candidate.json").stat().st_size if candidate is not None else 0,
        "publication_io": publication_io,
        "provider_calls_during_aggregation": 0,
    })
    print(json.dumps({"state": report["state"], "symbols": report["full_universe_completeness"]["terminal_record_count"]}))
    return 0 if report["state"] in {"CANARY_PASS", "FINNHUB_FULL_UNIVERSE_EXECUTOR_CERTIFIED"} else 1


def merge_checkpoints(args: argparse.Namespace) -> int:
    frozen = load_frozen_universe(args.universe)
    payloads, shard_digests = _profiled(
        "A_SHARD_ARTIFACT_INVENTORY_VALIDATION",
        lambda: _load_verified_shards(args.shards),
    )
    (shards, digests), inventory_metric = payloads, shard_digests
    identity = _recovery_identity(shards, frozen, args)
    acquired, merge_metric = _profiled(
        "B_SHARD_MERGE",
        lambda: validate_shards(universe=frozen, identity=identity, shards=shards),
    )
    checkpoint = _checkpoint(
        checkpoint_type="MERGED_SHARD_CHECKPOINT", identity=identity, universe=frozen,
        shard_digests=digests,
        payload={"shard_count": len(shards), "merged_symbol_count": len(acquired)},
        phase_metrics=[inventory_metric, merge_metric],
    )
    _assert_checkpoint_safe(checkpoint)
    _write(args.output / "merged_shard_checkpoint.json", checkpoint)
    prepared_payload = {"run_identity": identity, "records": acquired}
    _assert_checkpoint_safe(prepared_payload)
    prepared_checkpoint = _checkpoint(
        checkpoint_type="PREPARED_EVALUATION_INPUT_CHECKPOINT", identity=identity, universe=frozen,
        shard_digests=digests, payload=prepared_payload,
        phase_metrics=[inventory_metric, merge_metric],
    )
    _assert_checkpoint_safe(prepared_checkpoint)
    _write(args.output / "prepared_evaluation_input_checkpoint.json", prepared_checkpoint)
    print(json.dumps({"checkpoint": checkpoint["checkpoint_type"], "symbols": len(acquired), "provider_calls": 0}))
    return 0


def evaluate_checkpoint_chunk(args: argparse.Namespace) -> int:
    frozen = load_frozen_universe(args.universe)
    prepared = _load_checkpoint(args.prepared_checkpoint, "PREPARED_EVALUATION_INPUT_CHECKPOINT")
    identity = dict(prepared["payload"]["run_identity"])
    _validate_checkpoint_identity(prepared, identity=identity, universe=frozen)
    records = sorted(prepared["payload"]["records"], key=lambda item: str(item.get("ticker")))
    if args.chunk_count < 1 or not 0 <= args.chunk_index < args.chunk_count:
        raise ValueError("invalid canonical evaluation chunk coordinates")
    selected = _peer_component_chunks(records, args.chunk_count)[args.chunk_index]
    evaluation, metric = _profiled(
        "D_CANONICAL_EVALUATION_RECONSTRUCTION",
        lambda: evaluate_records(
            identity=identity, acquired=selected, checkpoint_dir=args.checkpoint_dir,
        ),
    )
    payload = {
        "chunk_index": args.chunk_index, "chunk_count": args.chunk_count,
        "symbol_count": len(selected), "evaluation": evaluation,
    }
    _assert_checkpoint_safe(payload)
    checkpoint = _checkpoint(
        checkpoint_type="CANONICAL_EVALUATION_CHUNK_CHECKPOINT", identity=identity, universe=frozen,
        shard_digests=prepared["shard_artifact_digests"], payload=payload,
        phase_metrics=[metric],
    )
    _assert_checkpoint_safe(checkpoint)
    _write(args.output / f"canonical_evaluation_chunk_{args.chunk_index:02d}.json", checkpoint)
    print(json.dumps({"chunk": args.chunk_index, "symbols": len(selected), "provider_calls": 0}))
    return 0


def certify_checkpoint(args: argparse.Namespace) -> int:
    frozen = load_frozen_universe(args.universe)
    merged = _load_checkpoint(args.merged_checkpoint, "MERGED_SHARD_CHECKPOINT")
    chunk_paths = sorted(args.chunks.glob("canonical_evaluation_chunk_*.json"))
    chunks = [_load_checkpoint(path, "CANONICAL_EVALUATION_CHUNK_CHECKPOINT") for path in chunk_paths]
    if not chunks:
        raise ValueError("no canonical evaluation chunk checkpoints found")
    run_identity = chunks[0].get("run_identity_sha256")
    # The complete identity is preserved in the prepared checkpoint; the merge
    # checkpoint provides the immutable dimensions needed for final validation.
    identity = {
        "source_sha": merged["source_sha"],
        "evidence_snapshot_at": merged["evidence_snapshot_timestamp"],
        "run_identity_sha256": run_identity,
    }
    _validate_checkpoint_identity(merged, identity=identity, universe=frozen)
    expected_count = int(chunks[0]["payload"]["chunk_count"])
    indices = sorted(int(chunk["payload"]["chunk_index"]) for chunk in chunks)
    if indices != list(range(expected_count)):
        raise ValueError("canonical evaluation chunk set is incomplete")
    for chunk in chunks:
        _validate_checkpoint_identity(chunk, identity=identity, universe=frozen)
        if chunk["shard_artifact_digests"] != merged["shard_artifact_digests"]:
            raise ValueError("canonical evaluation chunk shard identity mismatch")
    results = [chunk["payload"]["evaluation"] for chunk in chunks]
    reverse = args.order == "reverse"
    evaluation, evaluation_metric = _profiled(
        "E_DETERMINISTIC_ORDER_REPLAY" if reverse else "D_CANONICAL_EVALUATION_CHECKPOINT_MERGE",
        lambda: combine_evaluation_results(results, reverse=reverse),
    )
    completeness, completeness_metric = _profiled(
        "C_COMPLETENESS_ACCOUNTING",
        lambda: certify_complete_run(
            universe=frozen, records=evaluation["terminal_records"],
            acquisition_complete=True, decision_processing_complete=True,
        ),
    )
    record_projection = [
        {
            "ticker": record.get("ticker"),
            "terminal_data_state": record.get("terminal_data_state"),
            "canonical_action": record.get("canonical_action"),
            "evaluation_digest": record.get("evaluation_digest"),
        }
        for record in evaluation["terminal_records"]
    ]
    payload = {
        "run_identity_sha256": identity["run_identity_sha256"],
        "order": args.order,
        "completeness": completeness,
        "record_projection_sha256": _digest(record_projection),
        "record_count": len(record_projection),
        "inspector": evaluation["inspector"],
    }
    _assert_checkpoint_safe(payload)
    checkpoint = _checkpoint(
        checkpoint_type="CANONICAL_EVALUATION_ORDER_CHECKPOINT", identity=identity, universe=frozen,
        shard_digests=merged["shard_artifact_digests"], payload=payload,
        phase_metrics=[evaluation_metric, completeness_metric],
    )
    _assert_checkpoint_safe(checkpoint)
    _write(args.output / f"canonical_evaluation_{args.order}_checkpoint.json", checkpoint)
    print(json.dumps({"checkpoint": checkpoint["checkpoint_type"], "order": args.order,
                      "symbols": len(evaluation["terminal_records"]), "provider_calls": 0}))
    return 0


def _validate_checkpoint_identity(checkpoint: Mapping[str, Any], *, identity: Mapping[str, Any], universe: Mapping[str, Any]) -> None:
    expected = {
        "source_sha": identity["source_sha"],
        "universe_sha": universe["source_sha256"],
        "evidence_snapshot_timestamp": identity["evidence_snapshot_at"],
        "run_identity_sha256": identity["run_identity_sha256"],
    }
    for key, value in expected.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"aggregation checkpoint {key} mismatch")


def _write_report_artifacts(output: Path, report: dict[str, Any]) -> None:
    candidates = report.pop("determinism_candidates", {})
    publication_bundle = report.pop("publication_bundle", None)
    if candidates.get("first") is not None:
        _write(output / "determinism_candidate_first.json", candidates["first"])
    if candidates.get("second") is not None:
        _write(output / "determinism_candidate_second.json", candidates["second"])
    _write(output / "full_universe_gate_report.json", report)
    for filename, key in (
        ("checkpoint_summary.json", "full_universe_completeness"),
        ("provider_call_telemetry.json", "provider_call_telemetry"),
        ("evidence_inspector_coverage.json", "evidence_inspector_coverage"),
        ("valuation_route_distribution.json", "valuation_route_distribution"),
        ("valuation_method_distribution.json", "valuation_method_distribution"),
        ("gate_diagnostics.json", "gate_diagnostics"),
        ("publication_diagnostics.json", "publication_diagnostics"),
        ("pillar_distribution.json", "pillar_distribution"),
        ("action_distribution.json", "action_distribution"),
        ("buy_now_provenance.json", "buy_now_provenance"),
        ("determinism_report.json", "determinism"),
    ):
        _write(output / filename, report[key])
    _write(output / "evidence_coverage_report.json", {
        "evidence_inspector": report["evidence_inspector_coverage"],
        "forward_route_leakage": report["forward_route_leakage"],
        "shadow_evidence_leakage": report["shadow_evidence_leakage"],
        "authority_violations": report["authority_violations"],
        "terminal_state_counts": report["full_universe_completeness"]["terminal_state_counts"],
    })
    if report.get("immutable_candidate") is not None:
        _write(output / "immutable_candidate.json", report["immutable_candidate"])
    if publication_bundle is not None:
        for name, payload in publication_bundle["artifacts"].items():
            _write(output / "publication_bundle" / name, payload)
        _write(output / "publication_bundle" / "publication_manifest.json", publication_bundle["manifest"])


def _load_canonical_recovery(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    frozen = load_frozen_universe(args.universe)
    merged = _load_checkpoint(args.merged_checkpoint, "MERGED_SHARD_CHECKPOINT")
    first_checkpoint = _load_checkpoint(args.canonical_checkpoint, "CANONICAL_EVALUATION_ORDER_CHECKPOINT")
    second_checkpoint = _load_checkpoint(args.replay_checkpoint, "CANONICAL_EVALUATION_ORDER_CHECKPOINT")
    if first_checkpoint["payload"].get("order") != "forward" or second_checkpoint["payload"].get("order") != "reverse":
        raise ValueError("canonical order checkpoint roles are invalid")
    if not (merged["shard_artifact_digests"] == first_checkpoint["shard_artifact_digests"] == second_checkpoint["shard_artifact_digests"]):
        raise ValueError("merge and canonical checkpoint shard identities differ")
    shards, _ = _load_verified_shards(args.shards, merged["shard_artifact_digests"])
    identity = _recovery_identity(shards, frozen, args)
    for checkpoint in (merged, first_checkpoint, second_checkpoint):
        _validate_checkpoint_identity(checkpoint, identity=identity, universe=frozen)
    chunk_paths = sorted(args.chunks.glob("canonical_evaluation_chunk_*.json"))
    chunks = [_load_checkpoint(path, "CANONICAL_EVALUATION_CHUNK_CHECKPOINT") for path in chunk_paths]
    if len(chunks) != int(chunks[0]["payload"]["chunk_count"] if chunks else 0):
        raise ValueError("canonical evaluation chunk set is incomplete during publication")
    for chunk in chunks:
        _validate_checkpoint_identity(chunk, identity=identity, universe=frozen)
        if chunk["shard_artifact_digests"] != merged["shard_artifact_digests"]:
            raise ValueError("publication chunk shard identity mismatch")
    chunk_results = [chunk["payload"]["evaluation"] for chunk in chunks]
    first_evaluation = combine_evaluation_results(chunk_results)
    second_evaluation = combine_evaluation_results(chunk_results, reverse=True)
    for order_checkpoint, evaluation in ((first_checkpoint, first_evaluation), (second_checkpoint, second_evaluation)):
        projection = [
            {"ticker": record.get("ticker"), "terminal_data_state": record.get("terminal_data_state"),
             "canonical_action": record.get("canonical_action"), "evaluation_digest": record.get("evaluation_digest")}
            for record in evaluation["terminal_records"]
        ]
        if _digest(projection) != order_checkpoint["payload"]["record_projection_sha256"]:
            raise ValueError("canonical order projection digest mismatch")
    canonical_payload = {
        "run_identity_sha256": identity["run_identity_sha256"],
        "first_evaluation": first_evaluation,
        "first_completeness": first_checkpoint["payload"]["completeness"],
        "second_evaluation": second_evaluation,
        "second_completeness": second_checkpoint["payload"]["completeness"],
    }
    return frozen, identity, shards, merged, canonical_payload, first_checkpoint, second_checkpoint


def _load_candidate_recovery(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load only the requested canonical order for memory-bounded candidate assembly."""
    frozen = load_frozen_universe(args.universe)
    merged = _load_checkpoint(args.merged_checkpoint, "MERGED_SHARD_CHECKPOINT")
    first_checkpoint = _load_checkpoint(args.canonical_checkpoint, "CANONICAL_EVALUATION_ORDER_CHECKPOINT")
    second_checkpoint = _load_checkpoint(args.replay_checkpoint, "CANONICAL_EVALUATION_ORDER_CHECKPOINT")
    if first_checkpoint["payload"].get("order") != "forward" or second_checkpoint["payload"].get("order") != "reverse":
        raise ValueError("canonical order checkpoint roles are invalid")
    if not (merged["shard_artifact_digests"] == first_checkpoint["shard_artifact_digests"] == second_checkpoint["shard_artifact_digests"]):
        raise ValueError("merge and canonical checkpoint shard identities differ")
    first_shard, _ = _verify_shards_without_loading_payloads(
        args.shards, merged["shard_artifact_digests"],
    )
    identity = _recovery_identity([first_shard], frozen, args)
    for checkpoint in (merged, first_checkpoint, second_checkpoint):
        _validate_checkpoint_identity(checkpoint, identity=identity, universe=frozen)
    chunk_paths = sorted(args.chunks.glob("canonical_evaluation_chunk_*.json"))
    chunks = [_load_checkpoint(path, "CANONICAL_EVALUATION_CHUNK_CHECKPOINT") for path in chunk_paths]
    if len(chunks) != int(chunks[0]["payload"]["chunk_count"] if chunks else 0):
        raise ValueError("canonical evaluation chunk set is incomplete during candidate assembly")
    for chunk in chunks:
        _validate_checkpoint_identity(chunk, identity=identity, universe=frozen)
        if chunk["shard_artifact_digests"] != merged["shard_artifact_digests"]:
            raise ValueError("candidate chunk shard identity mismatch")
    selected_checkpoint = first_checkpoint if args.order == "forward" else second_checkpoint
    evaluation = combine_evaluation_results(
        [chunk["payload"]["evaluation"] for chunk in chunks],
        reverse=args.order == "reverse",
    )
    projection = [
        {"ticker": record.get("ticker"), "terminal_data_state": record.get("terminal_data_state"),
         "canonical_action": record.get("canonical_action"), "evaluation_digest": record.get("evaluation_digest")}
        for record in evaluation["terminal_records"]
    ]
    if _digest(projection) != selected_checkpoint["payload"]["record_projection_sha256"]:
        raise ValueError("canonical order projection digest mismatch")
    return frozen, identity, merged, evaluation, selected_checkpoint


def build_candidate_checkpoint(args: argparse.Namespace) -> int:
    frozen, identity, merged, evaluation, order_checkpoint = _load_candidate_recovery(args)
    candidate, metric = _profiled(
        f"F_IMMUTABLE_CANDIDATE_{args.order.upper()}",
        lambda: build_single_immutable_candidate(
            universe=frozen, identity=identity, evaluation=evaluation,
            completeness=order_checkpoint["payload"]["completeness"],
        ),
    )
    candidate_state = {"run_identity_sha256": identity["run_identity_sha256"],
                       "order": args.order, "canonical_checkpoint_digest": order_checkpoint["content_digest"],
                       "methodology_version": candidate.get("methodology_version"),
                       "provider_authority_version": candidate.get("provider_authority_version"),
                       "candidate": candidate}
    checkpoint = _checkpoint(
        checkpoint_type="IMMUTABLE_CANDIDATE_ORDER_CHECKPOINT", identity=identity, universe=frozen,
        shard_digests=merged["shard_artifact_digests"], payload=candidate_state,
        phase_metrics=[*order_checkpoint["phase_metrics"], metric],
    )
    _assert_checkpoint_safe(checkpoint)
    _write(args.output / f"immutable_candidate_{args.order}_checkpoint.json", checkpoint)
    print(json.dumps({"checkpoint": checkpoint["checkpoint_type"],
                      "order": args.order, "candidate_digest": candidate.get("candidate_digest"),
                      "provider_calls": 0}))
    return 0


def certify_candidate_determinism(args: argparse.Namespace) -> int:
    first = _load_checkpoint(args.canonical_candidate_checkpoint, "IMMUTABLE_CANDIDATE_ORDER_CHECKPOINT")
    second = _load_checkpoint(args.replay_candidate_checkpoint, "IMMUTABLE_CANDIDATE_ORDER_CHECKPOINT")
    if first["payload"].get("order") != "forward" or second["payload"].get("order") != "reverse":
        raise ValueError("immutable candidate checkpoint roles are invalid")
    identity_keys = ("source_sha", "universe_sha", "evidence_snapshot_timestamp", "run_identity_sha256")
    if any(first.get(key) != second.get(key) for key in identity_keys):
        raise ValueError("immutable candidate checkpoint identity mismatch")
    if first["shard_artifact_digests"] != second["shard_artifact_digests"]:
        raise ValueError("immutable candidate shard identity mismatch")
    first_candidate, second_candidate = first["payload"]["candidate"], second["payload"]["candidate"]
    determinism = compare_deterministic_candidates(first_candidate, second_candidate)
    determinism["structural_diff"] = compare_replay_candidates(first_candidate, second_candidate)
    structural = determinism["structural_diff"]
    determinism["required_equalities"] = {
        "analytical": structural.get("analytical_mismatch_count") == 0,
        "action": structural.get("classifications", {}).get("ACTION_DIFFERENCE") == 0,
        "method_set_fair_value_opportunity_confidence": structural.get("analytical_mismatch_count") == 0,
        "deterministic_serialization_digest": determinism.get("status") == "PASS",
    }
    if not all(determinism["required_equalities"].values()):
        determinism["status"] = "FAIL"
    identity = {"source_sha": first["source_sha"], "evidence_snapshot_at": first["evidence_snapshot_timestamp"],
                "run_identity_sha256": first["run_identity_sha256"]}
    universe = {"source_sha256": first["universe_sha"]}
    payload = {"run_identity_sha256": first["run_identity_sha256"], "determinism": determinism,
               "forward_candidate_digest": first_candidate.get("candidate_digest"),
               "reverse_candidate_digest": second_candidate.get("candidate_digest")}
    checkpoint = _checkpoint(
        checkpoint_type="CANDIDATE_DETERMINISM_CHECKPOINT", identity=identity, universe=universe,
        shard_digests=first["shard_artifact_digests"], payload=payload,
        phase_metrics=[*first["phase_metrics"], *second["phase_metrics"]],
    )
    _assert_checkpoint_safe(checkpoint)
    _write(args.output / "candidate_determinism_checkpoint.json", checkpoint)
    print(json.dumps({"checkpoint": checkpoint["checkpoint_type"],
                      "determinism": determinism.get("status"), "provider_calls": 0}))
    return 0 if determinism.get("status") == "PASS" else 1


def _stream_candidate_metadata(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read only governed candidate/checkpoint metadata without loading evaluations."""
    candidate_fields = {
        "candidate_digest", "evidence_snapshot_at", "source_sha", "universe_sha256",
        "supported_symbol_count", "provider_authority_version", "methodology_version",
        "valuation_version", "six_pillar_version", "action_engine_version",
    }
    outer_fields = {"source_sha", "universe_sha", "evidence_snapshot_timestamp", "run_identity_sha256"}
    candidate: dict[str, Any] = {}
    outer: dict[str, Any] = {}
    with path.open("rb") as handle:
        for prefix, event, value in ijson.parse(handle, use_float=True):
            if event not in {"string", "number", "boolean", "null"}:
                continue
            if prefix in outer_fields:
                outer[prefix] = value
            elif prefix.startswith("payload.candidate."):
                key = prefix.removeprefix("payload.candidate.")
                if key in candidate_fields:
                    candidate[key] = value
    missing_outer = sorted(outer_fields - outer.keys())
    missing_candidate = sorted({"candidate_digest", "supported_symbol_count"} - candidate.keys())
    if missing_outer or missing_candidate:
        raise ValueError(
            f"immutable candidate checkpoint metadata incomplete: outer={missing_outer}, candidate={missing_candidate}")
    return candidate, outer


def publish_checkpoint(args: argparse.Namespace) -> int:
    frozen = load_frozen_universe(args.universe)
    merged = _load_checkpoint(args.merged_checkpoint, "MERGED_SHARD_CHECKPOINT")
    first_checkpoint = _load_checkpoint(args.canonical_checkpoint, "CANONICAL_EVALUATION_ORDER_CHECKPOINT")
    determinism_checkpoint = _load_checkpoint(args.determinism_checkpoint, "CANDIDATE_DETERMINISM_CHECKPOINT")
    candidate, outer = _stream_candidate_metadata(args.canonical_candidate_checkpoint)
    identity = {
        "source_sha": outer["source_sha"],
        "evidence_snapshot_at": outer["evidence_snapshot_timestamp"],
        "run_identity_sha256": outer["run_identity_sha256"],
    }
    for checkpoint in (merged, first_checkpoint, determinism_checkpoint):
        _validate_checkpoint_identity(checkpoint, identity=identity, universe=frozen)
        if checkpoint["shard_artifact_digests"] != merged["shard_artifact_digests"]:
            raise ValueError("publication checkpoint shard identity mismatch")
    determinism = determinism_checkpoint["payload"]["determinism"]
    candidate_digest = candidate.get("candidate_digest")
    if args.expected_candidate_digest and candidate_digest != args.expected_candidate_digest:
        raise ValueError("forward candidate digest differs from authorized publication candidate")
    if candidate_digest != determinism_checkpoint["payload"]["forward_candidate_digest"]:
        raise ValueError("forward candidate digest mismatch")
    if candidate_digest != determinism_checkpoint["payload"]["reverse_candidate_digest"]:
        raise ValueError("certified reverse candidate digest mismatch")
    structural = determinism.get("structural_diff") or {}
    if determinism.get("status") != "PASS" or structural.get("analytical_mismatch_count") != 0:
        raise ValueError("candidate determinism is not certified")
    if determinism_checkpoint.get("provider_calls_during_aggregation") != 0:
        raise ValueError("determinism checkpoint contains provider calls")
    if first_checkpoint["payload"].get("record_count") != int(candidate.get("supported_symbol_count") or -1):
        raise ValueError("candidate record count differs from certified canonical checkpoint")
    completeness = dict(first_checkpoint["payload"]["completeness"])
    inspector = dict(first_checkpoint["payload"]["inspector"])
    if completeness.get("state") != "FULL_UNIVERSE_CERTIFIED" or inspector.get("status") != "PASS":
        raise ValueError("canonical evaluation is not publication eligible")

    def candidate_records():
        with args.canonical_candidate_checkpoint.open("rb") as handle:
            yield from ijson.items(handle, "payload.candidate.evaluations.item", use_float=True)

    (publication, certification_metric) = _profiled(
        "H_PUBLICATION_PROJECTION",
        lambda: build_publication_bundle_streaming(
            candidate_records=candidate_records(), candidate=candidate,
            output=args.output / "publication_bundle", generated_at=str(identity["evidence_snapshot_at"]),
        ),
    )
    publication_summary, manifest = publication
    publication_digest = _digest({
        "artifact_hashes": manifest.get("artifact_hashes"),
        "candidate_digest": candidate_digest,
    })
    disk_rows = publication_summary["disk_rows"]
    def terminal_views():
        for row in disk_rows:
            evaluation = row.get("canonical_investment_evaluation") or {}
            yield {"ticker": row.get("ticker"), "terminal_data_state": row.get("terminal_data_state"),
                   "canonical_action": (evaluation.get("guidance") or {}).get("state") or "RATING_NOT_PUBLISHED",
                   "evaluation": evaluation, "evaluation_digest": row.get("executor_evaluation_digest"),
                   "buy_now_revalidation": row.get("buy_now_revalidation"),
                   "run_identity_sha256": identity["run_identity_sha256"]}
    buy_now_provenance = _buy_now_report(terminal_views(), frozen, identity)
    buy_now_terminal, buy_now_rows = [], []
    for row in disk_rows:
        evaluation = row.get("canonical_investment_evaluation") or {}
        action = (evaluation.get("guidance") or {}).get("state") or "RATING_NOT_PUBLISHED"
        if action != "BUY_NOW":
            continue
        buy_now_rows.append(row)
        buy_now_terminal.append({
            "ticker": row.get("ticker"),
            "terminal_data_state": row.get("terminal_data_state"),
            "canonical_action": action,
            "evaluation": evaluation,
            "evaluation_digest": row.get("executor_evaluation_digest"),
            "buy_now_revalidation": row.get("buy_now_revalidation"),
            "run_identity_sha256": identity["run_identity_sha256"],
        })
    publication_diagnostics = _publication_diagnostics(
        buy_now_terminal, {"full_evaluation_pool.json": buy_now_rows})
    publication_ready = (
        buy_now_provenance.get("status") == "PASS"
        and manifest.get("publication_gate_status") == "PASS"
        and manifest.get("artifact_lineage_status") == "COHERENT"
    )
    report = {
        "executor_version": "ATLAS_FINNHUB_FULL_UNIVERSE_EXECUTOR_V2_MULTI_METHOD",
        "run_identity": identity,
        "full_universe_completeness": completeness,
        "evidence_inspector_coverage": inspector,
        "forward_route_leakage": False,
        "shadow_evidence_leakage": False,
        "authority_violations": 0,
        "valuation_route_distribution": _route_distribution((item["evaluation"] for item in terminal_views())),
        "valuation_method_distribution": _method_distribution(terminal_views()),
        "gate_diagnostics": _gate_diagnostics(terminal_views()),
        "pillar_distribution": _pillar_distribution(terminal_views()),
        "action_distribution": completeness.get("action_counts") or {},
        "provider_call_telemetry": {"provider_calls": 0, "cache_hits": 0, "calls_avoided": 0,
                                    "retry_count": 0, "retry_rate": 0.0},
        "buy_now_provenance": buy_now_provenance,
        "determinism": determinism,
        "publication_bundle_digest": publication_digest,
        "publication_diagnostics": publication_diagnostics,
        "same_snapshot_parity": "PASS" if publication_ready else "FAIL",
        "new_full_universe_candidate_certified": publication_ready,
        "release_smoke_ready": publication_ready,
        "state": ("FINNHUB_FULL_UNIVERSE_EXECUTOR_CERTIFIED" if publication_ready
                  else "PUBLICATION_CERTIFICATION_FAILED"),
        "report_card_prospective_active": False,
        "production_schedule_cutover": False,
    }
    _, serialization_metric = _profiled("G_DETERMINISTIC_SERIALIZATION", lambda: _digest(report))
    report["aggregation_phase_metrics"] = [
        *merged["phase_metrics"], *first_checkpoint["phase_metrics"], *determinism_checkpoint["phase_metrics"],
        certification_metric, serialization_metric,
    ]
    report["provider_calls_during_aggregation"] = 0
    publication_digest = report.get("publication_bundle_digest")
    final_payload = {
        "state": report["state"],
        "terminal_record_count": report["full_universe_completeness"]["terminal_record_count"],
        "candidate_digest": candidate_digest,
        "publication_bundle_digest": publication_digest,
        "evidence_inspector_status": report["evidence_inspector_coverage"].get("status"),
    }
    final_checkpoint = _checkpoint(
        checkpoint_type="FINAL_CANDIDATE_CHECKPOINT", identity=identity, universe=frozen,
        shard_digests=merged["shard_artifact_digests"], payload=final_payload,
        phase_metrics=report["aggregation_phase_metrics"],
    )
    _assert_checkpoint_safe(final_checkpoint)
    _write(args.output / "final_candidate_checkpoint.json", final_checkpoint)
    for filename, key in (
        ("checkpoint_summary.json", "full_universe_completeness"),
        ("provider_call_telemetry.json", "provider_call_telemetry"),
        ("evidence_inspector_coverage.json", "evidence_inspector_coverage"),
        ("valuation_route_distribution.json", "valuation_route_distribution"),
        ("valuation_method_distribution.json", "valuation_method_distribution"),
        ("gate_diagnostics.json", "gate_diagnostics"),
        ("publication_diagnostics.json", "publication_diagnostics"),
        ("pillar_distribution.json", "pillar_distribution"),
        ("action_distribution.json", "action_distribution"),
        ("buy_now_provenance.json", "buy_now_provenance"),
        ("determinism_report.json", "determinism"),
    ):
        _write(args.output / filename, report[key])
    _write(args.output / "full_universe_gate_report.json", report)
    print(json.dumps({"state": report["state"], "symbols": final_payload["terminal_record_count"], "provider_calls": 0}))
    return 0 if report["state"] == "FINNHUB_FULL_UNIVERSE_EXECUTOR_CERTIFIED" else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=(
        "plan", "run-shard", "aggregate", "merge-checkpoints", "evaluate-checkpoint-chunk",
        "certify-checkpoint", "build-candidate-checkpoint", "certify-candidate-determinism", "publish-checkpoint",
    ))
    result.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--shards", type=Path)
    result.add_argument("--source-sha")
    result.add_argument("--evidence-snapshot")
    result.add_argument("--canary-size", type=int, default=0)
    result.add_argument("--shard-size", type=int, default=SHARD_SIZE)
    result.add_argument("--shard-index", type=int, default=0)
    result.add_argument("--pace-seconds", type=float, default=1.05)
    result.add_argument("--global-requests-per-minute", type=float)
    result.add_argument("--parallel-workers", type=int, default=1)
    result.add_argument("--strict-provider-health", action="store_true")
    result.add_argument("--checkpoint-dir", type=Path)
    result.add_argument("--merged-checkpoint", type=Path)
    result.add_argument("--canonical-checkpoint", type=Path)
    result.add_argument("--replay-checkpoint", type=Path)
    result.add_argument("--canonical-candidate-checkpoint", type=Path)
    result.add_argument("--replay-candidate-checkpoint", type=Path)
    result.add_argument("--determinism-checkpoint", type=Path)
    result.add_argument("--expected-candidate-digest")
    result.add_argument("--prepared-checkpoint", type=Path)
    result.add_argument("--chunks", type=Path)
    result.add_argument("--chunk-index", type=int, default=0)
    result.add_argument("--chunk-count", type=int, default=16)
    result.add_argument("--order", choices=("forward", "reverse"), default="forward")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "plan":
        return plan(args)
    if args.command == "run-shard":
        return run_shard(args)
    if args.command in {"aggregate", "merge-checkpoints"} and args.shards is None:
        raise ValueError("--shards is required")
    if args.command == "merge-checkpoints":
        return merge_checkpoints(args)
    if args.command == "evaluate-checkpoint-chunk":
        if args.prepared_checkpoint is None:
            raise ValueError("--prepared-checkpoint is required")
        return evaluate_checkpoint_chunk(args)
    if args.command == "certify-checkpoint":
        if args.merged_checkpoint is None or args.chunks is None:
            raise ValueError("--merged-checkpoint and --chunks are required")
        return certify_checkpoint(args)
    if args.command == "build-candidate-checkpoint":
        if (args.shards is None or args.merged_checkpoint is None or args.canonical_checkpoint is None
                or args.replay_checkpoint is None or args.chunks is None):
            raise ValueError("candidate checkpoint construction requires shards, merge, both order checkpoints, and chunks")
        return build_candidate_checkpoint(args)
    if args.command == "certify-candidate-determinism":
        if args.canonical_candidate_checkpoint is None or args.replay_candidate_checkpoint is None:
            raise ValueError("both immutable candidate order checkpoints are required")
        return certify_candidate_determinism(args)
    if args.command == "publish-checkpoint":
        if (args.merged_checkpoint is None or args.canonical_checkpoint is None
                or args.canonical_candidate_checkpoint is None or args.determinism_checkpoint is None):
            raise ValueError("publication requires merge, forward canonical, forward candidate, and determinism checkpoints")
        return publish_checkpoint(args)
    return aggregate(args)


if __name__ == "__main__":
    raise SystemExit(main())
