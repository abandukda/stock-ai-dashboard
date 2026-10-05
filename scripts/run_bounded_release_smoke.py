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
import time
from pathlib import Path
from typing import Any, Iterable

import ijson


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


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _action(row: dict[str, Any]) -> str:
    evaluation = row.get("canonical_investment_evaluation") or {}
    return str(((evaluation.get("guidance") or {}).get("state") or "RATING_NOT_PUBLISHED"))


def _allowed(row: dict[str, Any]) -> bool:
    return (row.get("publication_certification") or {}).get("customer_publication_allowed") is True


def _stream_pool(path: Path) -> tuple[dict[str, int], list[dict[str, Any]], list[str], int]:
    actions: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    withheld: list[str] = []
    count = 0
    with path.open("rb") as handle:
        for row in ijson.items(handle, "item", use_float=True):
            count += 1
            action = _action(row)
            actions[action] = actions.get(action, 0) + 1
            if action == "BUY_NOW" and not _allowed(row):
                withheld.append(str(row.get("ticker") or row.get("symbol") or ""))
            # Browser smoke needs only customer-visible records plus a bounded
            # representative set for Research state coverage.
            if (action == "BUY_NOW" and _allowed(row)) or len(selected) < 24:
                selected.append(row)
    return actions, selected, sorted(withheld), count


RESEARCH_SMOKE_TICKERS = ("NVDA", "REGN")


def _stream_customer_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect only published BUY_NOW and bounded Research rows from the UI pool."""
    selected: dict[str, dict[str, Any]] = {}
    published_buy: list[str] = []
    with path.open("rb") as handle:
        for row in ijson.items(handle, "item", use_float=True):
            ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
            if _action(row) == "BUY_NOW" and _allowed(row):
                published_buy.append(ticker)
                selected[ticker] = row
            elif ticker in RESEARCH_SMOKE_TICKERS:
                selected[ticker] = row
    return list(selected.values()), sorted(published_buy)


def _write_canonical(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str),
        encoding="utf-8",
    )


def _copy_small_bundle(
    bundle: Path, runtime: Path, selected: Iterable[dict[str, Any]],
    customer_rows: Iterable[dict[str, Any]],
) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    rows_by_ticker = {
        str(row.get("ticker") or row.get("symbol") or "").upper(): row
        for row in selected if isinstance(row, dict)
    }
    for row in customer_rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
        if ticker in RESEARCH_SMOKE_TICKERS:
            rows_by_ticker[ticker] = row
    rows = list(rows_by_ticker.values())
    missing = sorted(set(RESEARCH_SMOKE_TICKERS) - set(rows_by_ticker))
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
        "research_tickers": list(RESEARCH_SMOKE_TICKERS),
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
    gate = _load(report_root / "full_universe_gate_report.json")
    determinism = _load(report_root / "determinism_report.json")
    inspector = _load(report_root / "evidence_inspector_coverage.json")
    if determinism.get("status") != "PASS" or (determinism.get("structural_diff") or {}).get(
            "analytical_mismatch_count") != 0:
        raise ValueError("CANDIDATE_DETERMINISM_NOT_CERTIFIED")
    if gate.get("provider_calls_during_aggregation") != 0:
        raise ValueError("PROVIDER_CALLS_PRESENT_IN_CERTIFIED_REPORT")
    if inspector.get("status") != "PASS" or gate.get("same_snapshot_parity") != "PASS":
        raise ValueError("CERTIFIED_EVIDENCE_OR_SNAPSHOT_GATE_FAILED")
    if gate.get("report_card_prospective_active") is not False:
        raise ValueError("REPORT_CARD_MUST_REMAIN_OFF")

    expected_hashes = manifest.get("artifact_hashes") or {}
    verified_hashes: dict[str, str] = {}
    for name in PUBLICATION_FILES:
        actual = _sha256(bundle / name)
        expected = expected_hashes.get(name)
        if actual != expected:
            raise ValueError(f"PUBLICATION_ARTIFACT_DIGEST_MISMATCH:{name}")
        verified_hashes[name] = actual
    publication_digest = _canonical_digest({
        "artifact_hashes": expected_hashes,
        "candidate_digest": candidate_digest,
    })
    if publication_digest != args.expected_publication_digest:
        raise ValueError("CERTIFIED_PUBLICATION_DIGEST_MISMATCH")

    actions, selected, withheld, record_count = _stream_pool(bundle / "full_evaluation_pool.json")
    customer_rows, published_buy = _stream_customer_rows(bundle / "market_full_scan.json")
    leaked = sorted(set(withheld) & set(published_buy))
    if record_count != 6033 or actions.get("BUY_NOW") != 28 or len(published_buy) != 22:
        raise ValueError("CERTIFIED_PUBLICATION_COUNTS_MISMATCH")
    if len(withheld) != 6 or leaked:
        raise ValueError("WITHHELD_BUY_NOW_PUBLICATION_LEAK")
    if manifest.get("provider_status", {}).get("provider_calls") != 0:
        raise ValueError("PUBLICATION_PROVIDER_CALL_COUNT_NONZERO")

    _copy_small_bundle(bundle, args.runtime_dir.resolve(), selected, customer_rows)
    peak_rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_mib = peak_rss_raw / 1024.0 if peak_rss_raw > 1024 * 1024 else peak_rss_raw
    result = {
        "status": "PASS",
        "candidate_digest": candidate_digest,
        "candidate_source_sha": source_sha,
        "publication_bundle_digest": publication_digest,
        "artifact_hashes_verified": verified_hashes,
        "record_count": record_count,
        "action_distribution": actions,
        "canonical_buy_now_count": actions.get("BUY_NOW", 0),
        "customer_publishable_buy_now_count": len(published_buy),
        "customer_publishable_buy_now": published_buy,
        "withheld_buy_now_count": len(withheld),
        "withheld_buy_now": withheld,
        "withheld_publication_leaks": leaked,
        "evidence_inspector": inspector.get("status"),
        "same_snapshot_parity": gate.get("same_snapshot_parity"),
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
    return result


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), sort_keys=True))
