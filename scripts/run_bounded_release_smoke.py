"""Bounded-memory verification of a certified full-universe publication bundle.

This command deliberately performs no analytical calculation.  It verifies the
immutable publication identities, streams the large publication pool once, and
materializes only the already-published customer slice needed by browser smoke.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

import ijson

from services.finnhub_full_universe_executor import ACTION_ALIASES


PUBLICATION_FILES = (
    "market_full_scan.json",
    "market_prescreen.json",
    "recovery_scan.json",
    "etf_scan.json",
    "total_market_universe.json",
    "market_scan_state.json",
    "discovery_candidate_pool.json",
    "full_evaluation_pool.json",
)


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _peak_rss_mib() -> float:
    """Normalize getrusage RSS units (bytes on macOS, KiB on Linux)."""
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return value / divisor


def _semantic_json_sha256(path: Path) -> str:
    """Reproduce publication_governance._hash_payload without loading arrays."""
    with path.open("rb") as handle:
        first = b""
        while True:
            byte = handle.read(1)
            if not byte or not byte.isspace():
                first = byte
                break
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), default=str)
    if first == b"[":
        digest.update(b"[")
        with path.open("rb") as handle:
            for index, item in enumerate(ijson.items(handle, "item", use_float=True)):
                if index:
                    digest.update(b",")
                for chunk in encoder.iterencode(item):
                    digest.update(chunk.encode("utf-8"))
        digest.update(b"]")
        return digest.hexdigest()
    # Governed non-array publication artifacts are small metadata objects.
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    for chunk in encoder.iterencode(payload):
        digest.update(chunk.encode("utf-8"))
    return digest.hexdigest()


def _verify_publication_artifact_hashes(
    bundle: Path, manifest: Mapping[str, Any], *, semantic_contract: bool,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    expected_hashes = dict(manifest.get("artifact_hashes") or {})
    lineage = dict(manifest.get("artifact_lineage") or {})
    verified: dict[str, str] = {}
    diagnostics: dict[str, dict[str, Any]] = {}
    for name in PUBLICATION_FILES:
        path = bundle / name
        expected = expected_hashes.get(name)
        raw = _sha256(path)
        if semantic_contract:
            lineage_digest = dict(lineage.get(name) or {}).get("semantic_sha256")
            if lineage_digest != expected:
                raise ValueError(f"PUBLICATION_MANIFEST_LINEAGE_DIGEST_MISMATCH:{name}")
            governed = _semantic_json_sha256(path)
            digest_contract = "CANONICAL_JSON_SEMANTIC_SHA256"
        else:
            governed = raw
            digest_contract = "LEGACY_RAW_FILE_SHA256"
        if governed != expected:
            raise ValueError(f"PUBLICATION_ARTIFACT_DIGEST_MISMATCH:{name}")
        verified[name] = governed
        diagnostics[name] = {
            "manifest_semantic_digest": expected,
            "raw_storage_digest": raw,
            "digest_contract": digest_contract,
            "semantic_digest_verified": governed == expected,
        }
    return verified, diagnostics


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_fresh_backend_handoff(
    path: Path, *, candidate_digest: str, publication_digest: str,
    source_sha: str, evidence_snapshot_at: str, universe_sha256: str,
) -> dict[str, Any]:
    handoff = _load(path)
    expected = {
        "schema": "ATLAS_RELEASE_FULL_BACKEND_HANDOFF_V1",
        "status": "PASS",
        "candidate_digest": candidate_digest,
        "publication_digest": publication_digest,
        "source_sha": source_sha,
        "evidence_snapshot_at": evidence_snapshot_at,
        "universe_sha256": universe_sha256,
        "provider_calls": 0,
        "reacquisition": "none",
        "dataset_gate": "PASS",
        "dataset_certification_status": "PASS",
        "publication_gate_status": "PASS",
    }
    mismatches = [key for key, value in expected.items() if handoff.get(key) != value]
    if mismatches:
        raise ValueError("FRESH_BACKEND_HANDOFF_MISMATCH:" + ",".join(mismatches))
    return handoff


def _verify_fresh_artifact_contract(
    *, manifest: dict[str, Any], checkpoint: dict[str, Any],
    determinism: dict[str, Any], candidate_digest: str,
    evidence_snapshot_at: str, universe_sha256: str,
) -> None:
    checks = {
        "publication_gate": manifest.get("publication_gate_status") == "PASS",
        "candidate_verified": manifest.get("executor_candidate_digest_verified") is True,
        "customer_publication": int(manifest.get("customer_publication_count") or 0) > 0,
        "report_card_off": manifest.get("report_card_prospective_active") is False,
        "snapshot_identity": str(manifest.get("generated_at") or "") == evidence_snapshot_at,
        "universe_identity": bool(universe_sha256),
        "completeness": checkpoint.get("state") == "FULL_UNIVERSE_CERTIFIED",
        "symbol_count": checkpoint.get("terminal_record_count") == 6033
            and checkpoint.get("expected_supported_symbol_count") == 6033,
        "missing_symbols": not checkpoint.get("missing_symbols"),
        "duplicate_symbols": not checkpoint.get("duplicate_symbols"),
        "unexpected_symbols": not checkpoint.get("unexpected_symbols"),
        "customer_publishable": checkpoint.get("customer_publishable") is True,
        "determinism": determinism.get("status") == "PASS",
        "first_digest": determinism.get("first_digest") == candidate_digest,
        "second_digest": determinism.get("second_digest") == candidate_digest,
        "zero_mismatches": (determinism.get("structural_diff") or {}).get(
            "analytical_mismatch_count") == 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ValueError("FRESH_ARTIFACT_CONTRACT_FAILED:" + ",".join(failures))


def _stream_top_level_scalars(path: Path, keys: Iterable[str]) -> dict[str, Any]:
    """Read selected root scalar fields without materializing embedded records."""
    wanted = set(keys)
    values: dict[str, Any] = {}
    with path.open("rb") as handle:
        for prefix, event, value in ijson.parse(handle, use_float=True):
            if prefix in wanted and event in {"string", "number", "boolean", "null"}:
                values[prefix] = value
                if values.keys() == wanted:
                    break
    return values


def _action(row: dict[str, Any]) -> str:
    evaluation = row.get("canonical_investment_evaluation") or {}
    engine_state = str(
        (evaluation.get("guidance") or {}).get("state") or "RATING_NOT_PUBLISHED"
    )
    return ACTION_ALIASES.get(engine_state, engine_state)


def _allowed(row: dict[str, Any]) -> bool:
    return (row.get("publication_certification") or {}).get("customer_publication_allowed") is True


def _stream_pool(path: Path) -> tuple[
    dict[str, int], list[dict[str, Any]], list[str], int, dict[str, Any],
]:
    actions: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    withheld: list[str] = []
    canonical_buy: list[str] = []
    publishable_buy: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    count = 0
    with path.open("rb") as handle:
        for row in ijson.items(handle, "item", use_float=True):
            count += 1
            ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
            if ticker in seen:
                duplicates.add(ticker)
            seen.add(ticker)
            action = _action(row)
            actions[action] = actions.get(action, 0) + 1
            if action == "BUY_NOW":
                canonical_buy.append(ticker)
                if _allowed(row):
                    publishable_buy.append(ticker)
                else:
                    withheld.append(ticker)
            # Browser smoke needs only customer-visible records plus a bounded
            # representative set for Research state coverage.
            if (action == "BUY_NOW" and _allowed(row)) or len(selected) < 24:
                selected.append(row)
    return actions, selected, sorted(withheld), count, {
        "canonical_buy_now": sorted(canonical_buy),
        "publishable_buy_now": sorted(publishable_buy),
        "withheld_buy_now": sorted(withheld),
        "duplicate_tickers": sorted(duplicates),
    }


LEGACY_RESEARCH_SMOKE_TICKERS = ("NVDA", "REGN")
FRESH_RESEARCH_ANCHOR_TICKERS = ("NVDA", "MSFT")


def _stream_customer_rows(
    path: Path, research_tickers: Iterable[str] = LEGACY_RESEARCH_SMOKE_TICKERS,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Collect only published BUY_NOW and bounded Research rows from the UI pool."""
    selected: dict[str, dict[str, Any]] = {}
    published_buy: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    research_tickers = {str(value).upper() for value in research_tickers}
    with path.open("rb") as handle:
        for row in ijson.items(handle, "item", use_float=True):
            ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
            if ticker in seen:
                duplicates.add(ticker)
            seen.add(ticker)
            if _action(row) == "BUY_NOW" and _allowed(row):
                published_buy.append(ticker)
                selected[ticker] = row
            elif ticker in research_tickers:
                selected[ticker] = row
    return list(selected.values()), sorted(published_buy), sorted(duplicates)


def _verify_fresh_inventory(
    *, action_distribution: Mapping[str, Any], checkpoint: Mapping[str, Any],
    provenance: Mapping[str, Any], observed_actions: Mapping[str, int],
    pool_inventory: Mapping[str, Any], market_publishable: Iterable[str],
    market_duplicates: Iterable[str], universe_sha256: str,
    authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Cross-check the governed fresh BUY_NOW inventory without fixed counts."""
    action_distribution = {str(key): int(value) for key, value in action_distribution.items()}
    observed_actions = {str(key): int(value) for key, value in observed_actions.items()}
    if action_distribution != observed_actions:
        raise ValueError("FRESH_INVENTORY_ACTION_DISTRIBUTION_MISMATCH")
    if dict(checkpoint.get("action_counts") or {}) != action_distribution:
        raise ValueError("FRESH_INVENTORY_CHECKPOINT_ACTION_DISTRIBUTION_MISMATCH")

    canonical = list(pool_inventory.get("canonical_buy_now") or ())
    pool_publishable = list(pool_inventory.get("publishable_buy_now") or ())
    pool_withheld = list(pool_inventory.get("withheld_buy_now") or ())
    market_publishable = [str(value).upper() for value in market_publishable]
    records = list(provenance.get("records") or ())
    provenance_tickers = [str(row.get("ticker") or "").upper() for row in records]
    provenance_publishable = sorted(
        str(row.get("ticker") or "").upper()
        for row in records if row.get("publication_eligible") is True
    )
    provenance_withheld = sorted(
        str(row.get("ticker") or "").upper()
        for row in records if row.get("publication_eligible") is not True
    )
    duplicate_sources = {
        "full_evaluation_pool": list(pool_inventory.get("duplicate_tickers") or ()),
        "market_full_scan": list(market_duplicates),
        "buy_now_provenance": sorted({ticker for ticker in provenance_tickers
                                      if provenance_tickers.count(ticker) > 1}),
    }
    if any(duplicate_sources.values()):
        raise ValueError("FRESH_INVENTORY_DUPLICATE_TICKER")

    canonical_set = set(canonical)
    provenance_set = set(provenance_tickers)
    publishable_set = set(provenance_publishable)
    withheld_set = set(provenance_withheld)
    if provenance_set - canonical_set:
        raise ValueError("FRESH_INVENTORY_UNEXPECTED_BUY_NOW_TICKER")
    if publishable_set - canonical_set:
        raise ValueError("FRESH_INVENTORY_PUBLISHABLE_NOT_CANONICAL_BUY_NOW")
    if withheld_set - canonical_set:
        raise ValueError("FRESH_INVENTORY_WITHHELD_NOT_CANONICAL_BUY_NOW")
    if publishable_set & withheld_set:
        raise ValueError("FRESH_INVENTORY_PARTITION_OVERLAP")
    if publishable_set | withheld_set != canonical_set:
        raise ValueError("FRESH_INVENTORY_CANONICAL_PARTITION_INCOMPLETE")

    canonical_count = int(action_distribution.get("BUY_NOW", 0))
    publishable_count = int(provenance.get("publishable_buy_now_count") or 0)
    provenance_canonical_count = int(provenance.get("canonical_buy_now_count") or 0)
    withheld_count = canonical_count - publishable_count
    if canonical_count != len(canonical_set) or provenance_canonical_count != canonical_count:
        raise ValueError("FRESH_INVENTORY_CANONICAL_COUNT_MISMATCH")
    if publishable_count != len(publishable_set):
        raise ValueError("FRESH_INVENTORY_PUBLISHABLE_COUNT_MISMATCH")
    if withheld_count != len(withheld_set):
        raise ValueError("FRESH_INVENTORY_WITHHELD_COUNT_MISMATCH")
    if set(pool_publishable) != publishable_set or set(pool_withheld) != withheld_set:
        raise ValueError("FRESH_INVENTORY_FULL_POOL_PARTITION_MISMATCH")
    if set(market_publishable) != publishable_set:
        if set(market_publishable) & withheld_set:
            raise ValueError("FRESH_INVENTORY_WITHHELD_PUBLICATION_LEAK")
        raise ValueError("FRESH_INVENTORY_CUSTOMER_PROJECTION_MISMATCH")
    if set(checkpoint.get("buy_now_tickers") or ()) != publishable_set:
        raise ValueError("FRESH_INVENTORY_CHECKPOINT_PUBLISHABLE_MISMATCH")
    if set(checkpoint.get("withheld_buy_now_tickers") or ()) != withheld_set:
        raise ValueError("FRESH_INVENTORY_CHECKPOINT_WITHHELD_MISMATCH")
    if provenance.get("status") != "PASS":
        raise ValueError("FRESH_INVENTORY_PROVENANCE_NOT_CERTIFIED")
    if any(str(row.get("universe_sha256") or "") != universe_sha256 for row in records):
        raise ValueError("FRESH_INVENTORY_PROVENANCE_UNIVERSE_MISMATCH")

    if authorization:
        expected_counts = {
            "canonical_buy_now_count": canonical_count,
            "publishable_buy_now_count": publishable_count,
            "withheld_buy_now_count": withheld_count,
        }
        for key, actual in expected_counts.items():
            if key in authorization and int(authorization[key]) != actual:
                raise ValueError("FRESH_INVENTORY_AUTHORIZATION_COUNT_MISMATCH")
        for key, actual in (
            ("publishable_buy_now", publishable_set), ("withheld_buy_now", withheld_set),
        ):
            if key in authorization and set(authorization[key]) != actual:
                raise ValueError("FRESH_INVENTORY_AUTHORIZATION_TICKER_MISMATCH")

    return {
        "canonical_buy_now_count": canonical_count,
        "customer_publishable_buy_now_count": publishable_count,
        "withheld_buy_now_count": withheld_count,
        "customer_publishable_buy_now": sorted(publishable_set),
        "withheld_buy_now": sorted(withheld_set),
        "canonical_buy_now": sorted(canonical_set),
        "withheld_publication_leaks": [],
        "authority": {
            "canonical": ["action_distribution.json", "full_evaluation_pool.json"],
            "partition": ["buy_now_provenance.json", "checkpoint_summary.json"],
            "customer_projection": "market_full_scan.json",
            "identity_and_gate": ["publication_manifest.json", "backend_handoff.json"],
        },
    }


def _write_canonical(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str),
        encoding="utf-8",
    )


def _copy_small_bundle(
    bundle: Path, runtime: Path, selected: Iterable[dict[str, Any]],
    customer_rows: Iterable[dict[str, Any]], research_tickers: Iterable[str],
) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    rows_by_ticker = {
        str(row.get("ticker") or row.get("symbol") or "").upper(): row
        for row in selected if isinstance(row, dict)
    }
    research_tickers = tuple(str(value).upper() for value in research_tickers)
    for row in customer_rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
        if ticker in research_tickers:
            rows_by_ticker[ticker] = row
    rows = list(rows_by_ticker.values())
    missing = sorted(set(research_tickers) - set(rows_by_ticker))
    if missing:
        raise ValueError(f"BOUNDED_RESEARCH_RECORD_MISSING:{','.join(missing)}")
    for name in ("market_scan_state.json", "total_market_universe.json",
                 "recovery_scan.json", "etf_scan.json"):
        shutil.copyfile(bundle / name, runtime / name)
    _write_canonical(runtime / "market_full_scan.json", rows)
    _write_canonical(runtime / "full_evaluation_pool.json", rows)
    _write_canonical(runtime / "market_prescreen.json", [])
    _write_canonical(runtime / "discovery_candidate_pool.json", [])
    manifest = _load(bundle / "publication_manifest.json")
    source_hashes = dict(manifest.get("artifact_hashes") or {})
    manifest["runtime_projection"] = {
        "mode": "RELEASE_SMOKE_BOUNDED_UI",
        "source_artifact_hashes": source_hashes,
        "research_tickers": list(research_tickers),
        "record_count": len(rows),
        "provider_calls": 0,
        "analytical_recomputation": False,
    }
    manifest["artifact_hashes"] = {
        name: _sha256(runtime / name) for name in PUBLICATION_FILES
    }
    _write_canonical(runtime / "publication_manifest.json", manifest)


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    bundle = args.bundle.resolve()
    report_root = args.report_root.resolve()
    manifest = _load(bundle / "publication_manifest.json")
    identity = manifest.get("executor_candidate_identity") or {}
    source_sha = manifest.get("source_commit_sha")
    identity_source_sha = identity.get("source_sha")
    if not source_sha or not identity_source_sha:
        raise ValueError("CERTIFIED_CANDIDATE_SOURCE_SHA_MISSING")
    if source_sha != identity_source_sha or source_sha != args.expected_source_sha:
        raise ValueError("CERTIFIED_CANDIDATE_SOURCE_SHA_MISMATCH")
    candidate_digest = identity.get("candidate_digest")
    if candidate_digest != args.expected_candidate_digest:
        raise ValueError("CERTIFIED_CANDIDATE_DIGEST_MISMATCH")
    evidence_snapshot_at = str(identity.get("evidence_snapshot_at") or manifest.get("generated_at") or "")
    universe_sha256 = str(identity.get("universe_sha256") or "")
    gate = _stream_top_level_scalars(
        report_root / "full_universe_gate_report.json",
        ("provider_calls_during_aggregation", "same_snapshot_parity", "report_card_prospective_active"),
    )
    determinism = _load(report_root / "determinism_report.json")
    inspector = _load(report_root / "evidence_inspector_coverage.json")
    if determinism.get("status") != "PASS" or (determinism.get("structural_diff") or {}).get(
            "analytical_mismatch_count") != 0:
        raise ValueError("CANDIDATE_DETERMINISM_NOT_CERTIFIED")
    legacy_contract = (
        gate.get("provider_calls_during_aggregation") is not None
        or gate.get("same_snapshot_parity") is not None
    )
    if legacy_contract:
        if gate.get("provider_calls_during_aggregation") != 0:
            raise ValueError("PROVIDER_CALLS_PRESENT_IN_CERTIFIED_REPORT")
        if gate.get("same_snapshot_parity") != "PASS":
            raise ValueError("CERTIFIED_SNAPSHOT_GATE_FAILED")
        contract_type = "LEGACY_RECOVERY"
        provider_call_proof_source = "CERTIFIED_REPORT"
        snapshot_identity_proof_source = "CERTIFIED_REPORT"
        backend_handoff_identity_match = None
        visual_same_snapshot_required = False
    else:
        if not evidence_snapshot_at or not universe_sha256:
            raise ValueError("CERTIFIED_CANDIDATE_SNAPSHOT_OR_UNIVERSE_MISSING")
        checkpoint = _load(report_root / "checkpoint_summary.json")
        _verify_fresh_artifact_contract(
            manifest=manifest, checkpoint=checkpoint, determinism=determinism,
            candidate_digest=candidate_digest, evidence_snapshot_at=evidence_snapshot_at,
            universe_sha256=universe_sha256,
        )
        handoff_path = getattr(args, "backend_handoff", None)
        if handoff_path is None:
            raise ValueError("FRESH_BACKEND_HANDOFF_REQUIRED")
        _verify_fresh_backend_handoff(
            handoff_path.resolve(), candidate_digest=candidate_digest,
            publication_digest=args.expected_publication_digest, source_sha=source_sha,
            evidence_snapshot_at=evidence_snapshot_at, universe_sha256=universe_sha256,
        )
        contract_type = "FRESH_FULL_UNIVERSE_PLUS_BACKEND_HANDOFF"
        provider_call_proof_source = "GOVERNED_BACKEND_HANDOFF"
        snapshot_identity_proof_source = "FRESH_ARTIFACT_PLUS_GOVERNED_BACKEND_HANDOFF"
        backend_handoff_identity_match = True
        visual_same_snapshot_required = True
    if inspector.get("status") != "PASS" or inspector.get("failures"):
        raise ValueError("CERTIFIED_EVIDENCE_GATE_FAILED")
    if gate.get("report_card_prospective_active") is not False:
        raise ValueError("REPORT_CARD_MUST_REMAIN_OFF")

    expected_hashes = manifest.get("artifact_hashes") or {}
    verified_hashes, digest_verification = _verify_publication_artifact_hashes(
        bundle, manifest, semantic_contract=not legacy_contract,
    )
    publication_digest = _canonical_digest({
        "artifact_hashes": expected_hashes,
        "candidate_digest": candidate_digest,
    })
    if publication_digest != args.expected_publication_digest:
        raise ValueError("CERTIFIED_PUBLICATION_DIGEST_MISMATCH")

    actions, selected, withheld, record_count, pool_inventory = _stream_pool(
        bundle / "full_evaluation_pool.json"
    )
    research_anchors = (
        LEGACY_RESEARCH_SMOKE_TICKERS if legacy_contract else FRESH_RESEARCH_ANCHOR_TICKERS
    )
    customer_rows, published_buy, market_duplicates = _stream_customer_rows(
        bundle / "market_full_scan.json", research_anchors,
    )
    leaked = sorted(set(withheld) & set(published_buy))
    if record_count != 6033:
        raise ValueError("CERTIFIED_PUBLICATION_COUNTS_MISMATCH")
    if legacy_contract:
        if actions.get("BUY_NOW") != 28 or len(published_buy) != 22:
            raise ValueError("CERTIFIED_PUBLICATION_COUNTS_MISMATCH")
        if len(withheld) != 6 or leaked:
            raise ValueError("WITHHELD_BUY_NOW_PUBLICATION_LEAK")
        inventory = {
            "canonical_buy_now_count": actions.get("BUY_NOW", 0),
            "customer_publishable_buy_now_count": len(published_buy),
            "withheld_buy_now_count": len(withheld),
            "customer_publishable_buy_now": published_buy,
            "withheld_buy_now": withheld,
            "withheld_publication_leaks": leaked,
            "authority": {"contract": "LEGACY_RECOVERY_FIXED_CERTIFIED_INVENTORY"},
        }
    else:
        inventory = _verify_fresh_inventory(
            action_distribution=_load(report_root / "action_distribution.json"),
            checkpoint=checkpoint,
            provenance=_load(report_root / "buy_now_provenance.json"),
            observed_actions=actions,
            pool_inventory=pool_inventory,
            market_publishable=published_buy,
            market_duplicates=market_duplicates,
            universe_sha256=universe_sha256,
        )
    if manifest.get("provider_status", {}).get("provider_calls") != 0:
        raise ValueError("PUBLICATION_PROVIDER_CALL_COUNT_NONZERO")

    research_tickers = tuple(research_anchors)
    if not legacy_contract:
        smaller_cap_representatives = sorted(
            set(inventory["customer_publishable_buy_now"]) - set(research_anchors)
        )
        if not smaller_cap_representatives:
            raise ValueError("FRESH_RESEARCH_REPRESENTATIVE_MISSING")
        research_tickers = (*research_tickers, smaller_cap_representatives[0])
    _copy_small_bundle(
        bundle, args.runtime_dir.resolve(), selected, customer_rows, research_tickers,
    )
    peak_rss_mib = _peak_rss_mib()
    result = {
        "status": "PASS",
        "candidate_digest": candidate_digest,
        "candidate_source_sha": source_sha,
        "publication_bundle_digest": publication_digest,
        "artifact_hashes_verified": verified_hashes,
        "artifact_digest_verification": digest_verification,
        "record_count": record_count,
        "action_distribution": actions,
        "canonical_buy_now_count": inventory["canonical_buy_now_count"],
        "customer_publishable_buy_now_count": inventory["customer_publishable_buy_now_count"],
        "customer_publishable_buy_now": inventory["customer_publishable_buy_now"],
        "withheld_buy_now_count": inventory["withheld_buy_now_count"],
        "withheld_buy_now": inventory["withheld_buy_now"],
        "withheld_publication_leaks": inventory["withheld_publication_leaks"],
        "inventory_authority": inventory["authority"],
        "evidence_inspector": inspector.get("status"),
        "same_snapshot_parity": gate.get("same_snapshot_parity"),
        "certification_contract_type": contract_type,
        "provider_call_proof_source": provider_call_proof_source,
        "snapshot_identity_proof_source": snapshot_identity_proof_source,
        "backend_handoff_identity_match": backend_handoff_identity_match,
        "visual_same_snapshot_required": visual_same_snapshot_required,
        "visual_same_snapshot_result": None if visual_same_snapshot_required else "PASS",
        "evidence_snapshot_at": evidence_snapshot_at,
        "universe_sha256": universe_sha256,
        "provider_calls": 0,
        "reacquisition": "none",
        "report_card_prospective_active": False,
        "runtime_seconds": round(time.monotonic() - started, 3),
        "peak_rss_mib": round(peak_rss_mib, 3),
        "bundle_bytes": sum((bundle / name).stat().st_size for name in (*PUBLICATION_FILES, "publication_manifest.json")),
        "runtime_projection_bytes": sum(path.stat().st_size for path in args.runtime_dir.resolve().iterdir()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--bundle", type=Path, required=True)
    result.add_argument("--report-root", type=Path, required=True)
    result.add_argument("--runtime-dir", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--expected-candidate-digest", required=True)
    result.add_argument("--expected-publication-digest", required=True)
    result.add_argument("--expected-source-sha", required=True)
    result.add_argument("--backend-handoff", type=Path)
    return result


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), sort_keys=True))
