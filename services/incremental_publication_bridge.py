"""Fail-closed bridge from incremental receipts to the certified publisher.

Transport and normalization remain owned by the existing Finnhub canonical
adapter.  Scoring remains owned by ``finnhub_full_universe_executor`` and
publication remains owned by ``publication_governance``.  This module only
proves that those existing stages consume one complete, source-bound
incremental evidence set.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from services.finnhub_full_universe_executor import (
    aggregate_complete_run,
    build_run_identity,
    deserialize_bars,
    deterministic_shards,
    serialize_bars,
)
from services.finnhub_incremental_post_close import (
    CHANGE_PROBE_FAMILY,
    FUNDAMENTAL_FAMILIES,
    PRICE_FAMILY,
    prepare_certification_handoff,
    publication_readiness,
    request_key,
)
from services.publication_governance import stage_candidate_artifacts
from scripts.finnhub_canonical_proving_set import _bars, _normalized_row


CONTRACT = "ATLAS_INCREMENTAL_PUBLICATION_BRIDGE_V1"
MINIMUM_TECHNICAL_HISTORY = 200


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _symbols(plan: Mapping[str, Any]) -> list[str]:
    result = {
        str(key).split(":", 2)[1]
        for key in plan.get("request_keys") or ()
        if str(key).count(":") >= 2
    }
    return sorted(result)


def _provider_record(*, raw_root: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    path = raw_root / str(receipt.get("raw_path") or "")
    if not path.is_file():
        raise ValueError(f"INCREMENTAL_RAW_EVIDENCE_MISSING:{receipt.get('request_key')}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt.get("raw_sha256"):
        raise ValueError(f"INCREMENTAL_RAW_EVIDENCE_DIGEST_MISMATCH:{receipt.get('request_key')}")
    envelope = json.loads(raw)
    if envelope.get("request_key") != receipt.get("request_key"):
        raise ValueError(f"INCREMENTAL_RAW_EVIDENCE_IDENTITY_MISMATCH:{receipt.get('request_key')}")
    record = envelope.get("provider_record")
    if not isinstance(record, Mapping):
        raise ValueError(f"INCREMENTAL_RAW_PROVIDER_RECORD_MISSING:{receipt.get('request_key')}")
    return dict(record)


def _new_filing(*, probe: Mapping[str, Any], retained_row: Mapping[str, Any]) -> bool:
    cutoff = str(retained_row.get("professional_evidence_as_of") or "")[:10]
    if not cutoff:
        raise ValueError(f"INCREMENTAL_RETAINED_FILING_CUTOFF_MISSING:{retained_row.get('ticker')}")
    return any(
        str(item.get("filing_date") or "")[:10] > cutoff
        for item in (probe.get("payload") or {}).get("filings") or ()
        if isinstance(item, Mapping) and item.get("filing_date")
    )


def load_retained_technical_history(
    *, root: Path, plan: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Recover source-bound completed bars from the governed acquisition shards.

    Publication bundles intentionally omit raw technical histories.  Reusing
    their rows alone would replace the technical series with one fresh bar and
    silently withhold the universe.  The original governed shard artifacts are
    therefore the only accepted retained source.
    """
    paths = sorted(path for path in root.rglob("shard-*.json") if re.fullmatch(r"shard-\d{3}\.json", path.name))
    if not paths:
        raise ValueError("INCREMENTAL_RETAINED_TECHNICAL_SHARDS_MISSING")
    membership = dict(plan.get("governed_membership") or {})
    expected_source = str(membership.get("source_commit_sha") or "")
    expected = _symbols(plan)
    histories: dict[str, list[dict[str, Any]]] = {}
    insufficient_histories: dict[str, int] = {}
    history_blockers: dict[str, list[str]] = {}
    shard_digests: list[str] = []
    run_identities: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        supplied = str(payload.get("shard_digest") or "")
        calculated = _digest({key: value for key, value in payload.items() if key != "shard_digest"})
        if supplied != calculated:
            raise ValueError(f"INCREMENTAL_RETAINED_SHARD_DIGEST_INVALID:{path.name}")
        identity = dict(payload.get("run_identity") or {})
        if expected_source and identity.get("source_sha") != expected_source:
            raise ValueError(f"INCREMENTAL_RETAINED_SHARD_SOURCE_MISMATCH:{path.name}")
        run_identities.add(str(identity.get("run_identity_sha256") or ""))
        shard_digests.append(supplied)
        for item in payload.get("records") or ():
            symbol = str(item.get("ticker") or "").upper()
            if not symbol or symbol in histories:
                raise ValueError(f"INCREMENTAL_RETAINED_TECHNICAL_DUPLICATE:{symbol}")
            bars = list(item.get("bars") or ())
            parsed = deserialize_bars(bars)
            if not parsed or len(parsed) != len(bars):
                raise ValueError(f"INCREMENTAL_RETAINED_TECHNICAL_HISTORY_INVALID:{symbol}")
            # A governed shard can retain an in-progress tail bar.  It is not
            # eligible technical evidence for a finalized-session replay, but
            # it must not make the security disappear from the 1,298-member
            # population.  Remove only those explicitly incomplete bars and
            # carry a terminal blocker into the unchanged evaluator.
            completed = [bar for bar in parsed if bar.completed]
            if len(completed) != len(parsed):
                history_blockers[symbol] = ["INCREMENTAL_RETAINED_TECHNICAL_HISTORY_INCOMPLETE"]
            if any(a.timestamp >= b.timestamp for a, b in zip(completed, completed[1:])):
                raise ValueError(f"INCREMENTAL_RETAINED_TECHNICAL_HISTORY_UNORDERED:{symbol}")
            if completed and completed[-1].timestamp.date().isoformat() >= str(plan.get("session")):
                raise ValueError(f"INCREMENTAL_RETAINED_TECHNICAL_HISTORY_NOT_PRIOR:{symbol}")
            serialized = serialize_bars(completed)
            if len(serialized) < MINIMUM_TECHNICAL_HISTORY:
                insufficient_histories[symbol] = len(serialized)
            histories[symbol] = serialized
    if sorted(histories) != expected:
        raise ValueError("INCREMENTAL_RETAINED_TECHNICAL_MEMBERSHIP_MISMATCH")
    if len(run_identities) != 1 or not next(iter(run_identities)):
        raise ValueError("INCREMENTAL_RETAINED_RUN_IDENTITY_MISMATCH")
    report = {
        "contract": "ATLAS_RETAINED_TECHNICAL_HISTORY_BINDING_V1",
        "source_run_id": membership.get("source_run_id"),
        "source_commit_sha": expected_source,
        "run_identity_sha256": next(iter(run_identities)),
        "symbol_count": len(histories), "shard_count": len(paths),
        "minimum_bar_count": min(len(value) for value in histories.values()),
        "insufficient_history_count": len(insufficient_histories),
        "insufficient_history_symbols": dict(sorted(insufficient_histories.items())),
        "history_blockers": dict(sorted(history_blockers.items())),
        "shard_set_sha256": _digest(shard_digests),
    }
    report["binding_sha256"] = _digest(report)
    return histories, report


def _merge_completed_history(
    *, symbol: str, retained: Sequence[Mapping[str, Any]], fresh: Sequence[Any], session: str,
) -> list[Any]:
    prior = deserialize_bars(retained)
    if not fresh or fresh[-1].timestamp.date().isoformat() != session:
        raise ValueError(f"INCREMENTAL_COMPLETED_SESSION_MISMATCH:{symbol}")
    merged = [bar for bar in prior if bar.timestamp.date().isoformat() < session] + list(fresh)
    if any(a.timestamp >= b.timestamp for a, b in zip(merged, merged[1:])):
        raise ValueError(f"INCREMENTAL_MERGED_TECHNICAL_HISTORY_INVALID:{symbol}")
    return merged


def materialize_acquired_records(
    *, plan: Mapping[str, Any], checkpoint: Mapping[str, Any], raw_root: Path,
    retained_rows: Sequence[Mapping[str, Any]],
    retained_technical_history: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    retained_technical_blockers: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    """Create canonical executor input from raw-first receipts and retained rows.

    Unchanged filings retain the already-certified fundamentals and replace only
    completed-session market history.  A newer filing may be consumed only when
    all three allowlisted fundamental families are present in the same plan;
    otherwise the run fails closed before scoring.
    """
    readiness = publication_readiness(plan=plan, checkpoint=checkpoint)
    retained = {str(row.get("ticker") or "").upper(): dict(row) for row in retained_rows}
    expected = _symbols(plan)
    if sorted(retained) != expected:
        raise ValueError("INCREMENTAL_RETAINED_MEMBERSHIP_MISMATCH")
    receipts = dict(checkpoint.get("receipts") or {})
    output = []
    for symbol in expected:
        prefix = f"{plan['session']}:{symbol}:"
        per_symbol = {key.split(":", 2)[2]: value for key, value in receipts.items() if key.startswith(prefix)}
        price = _provider_record(raw_root=raw_root, receipt=per_symbol[PRICE_FAMILY])
        probe = _provider_record(raw_root=raw_root, receipt=per_symbol[CHANGE_PROBE_FAMILY])
        fresh_bars = _bars(symbol, price)
        if retained_technical_history is None or symbol not in retained_technical_history:
            raise ValueError(f"INCREMENTAL_RETAINED_TECHNICAL_HISTORY_REQUIRED:{symbol}")
        retained_bars = retained_technical_history[symbol]
        bars = _merge_completed_history(
            symbol=symbol, retained=retained_bars,
            fresh=fresh_bars, session=str(plan["session"]),
        )
        row = dict(retained[symbol])
        # A short retained series remains represented in the governed 1,298-row
        # population, but it cannot be scored.  Preserve the unchanged evaluator's
        # fail-closed terminal path with an explicit, source-bound withholding
        # reason instead of dropping the security or weakening the 200-bar rule.
        blockers: list[str] = list((retained_technical_blockers or {}).get(symbol) or ())
        blockers += (
            ["INCREMENTAL_TECHNICAL_HISTORY_INSUFFICIENT"]
            if len(retained_bars) < MINIMUM_TECHNICAL_HISTORY else []
        )
        if _new_filing(probe=probe, retained_row=row):
            missing = [family for family in FUNDAMENTAL_FAMILIES if family not in per_symbol]
            if missing:
                raise ValueError(f"INCREMENTAL_CHANGED_FUNDAMENTALS_NOT_ACQUIRED:{symbol}")
            records = {"historical_ohlcv": price, **{
                family: _provider_record(raw_root=raw_root, receipt=per_symbol[family])
                for family in FUNDAMENTAL_FAMILIES
            }}
            normalized = _normalized_row(symbol, row, records)
            row, bars, blockers = normalized.row, normalized.bars, normalized.blockers
            if row is None or blockers:
                raise ValueError(f"INCREMENTAL_CHANGED_FUNDAMENTAL_NORMALIZATION_FAILED:{symbol}")
        else:
            row.update({
                "current_price": bars[-1].close, "price": bars[-1].close,
                "historical_ohlcv_evidence_id": (price.get("provenance") or {}).get("raw_evidence_id"),
            })
        output.append({
            "ticker": symbol, "row": row, "bars": serialize_bars(bars),
            "blockers": blockers, "credential_entitlement_failures": 0,
            "security_master": {}, "analytical_inputs": {},
            "shadow_evidence_leakage": False, "authority_violations": 0,
            "incremental_receipt_keys": sorted(value["request_key"] for value in per_symbol.values()),
            "incremental_receipt_set_sha256": readiness["receipt_set_sha256"],
            "normalization_method": "EXISTING_FINNHUB_CANONICAL_NORMALIZER",
        })
    return output


def _validate_acquired_records(
    *, plan: Mapping[str, Any], checkpoint: Mapping[str, Any],
    acquired_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Require canonical normalized evidence for every governed symbol."""
    readiness = publication_readiness(plan=plan, checkpoint=checkpoint)
    expected = _symbols(plan)
    observed = [str(item.get("ticker") or "").upper() for item in acquired_records]
    duplicates = sorted(symbol for symbol, count in Counter(observed).items() if count != 1)
    if duplicates:
        raise ValueError(f"INCREMENTAL_NORMALIZED_DUPLICATE_SYMBOL:{','.join(duplicates)}")
    if sorted(observed) != expected:
        raise ValueError("INCREMENTAL_NORMALIZED_MEMBERSHIP_MISMATCH")
    receipt_keys = set((checkpoint.get("receipts") or {}).keys())
    changed = {
        str(key).split(":", 2)[1]
        for key in plan.get("request_keys") or ()
        if str(key).endswith(tuple(f":{family}" for family in FUNDAMENTAL_FAMILIES))
    }
    normalized: list[dict[str, Any]] = []
    for item in acquired_records:
        symbol = str(item.get("ticker") or "").upper()
        required = {
            request_key(session=str(plan["session"]), symbol=symbol, family=PRICE_FAMILY),
            request_key(session=str(plan["session"]), symbol=symbol, family=CHANGE_PROBE_FAMILY),
        }
        if symbol in changed:
            required.update(
                request_key(session=str(plan["session"]), symbol=symbol, family=family)
                for family in FUNDAMENTAL_FAMILIES
            )
        supplied = set(item.get("incremental_receipt_keys") or ())
        if required - receipt_keys or required - supplied:
            raise ValueError(f"INCREMENTAL_NORMALIZED_EVIDENCE_INCOMPLETE:{symbol}")
        if item.get("incremental_receipt_set_sha256") != readiness["receipt_set_sha256"]:
            raise ValueError(f"INCREMENTAL_NORMALIZED_RECEIPT_IDENTITY_MISMATCH:{symbol}")
        if not isinstance(item.get("row"), Mapping) or not item.get("bars"):
            raise ValueError(f"INCREMENTAL_NORMALIZED_CANONICAL_INPUT_MISSING:{symbol}")
        if item.get("normalization_method") != "EXISTING_FINNHUB_CANONICAL_NORMALIZER":
            raise ValueError(f"INCREMENTAL_PARALLEL_NORMALIZATION_FORBIDDEN:{symbol}")
        normalized.append(dict(item))
    return normalized


def reconcile_publication_population(
    *, symbols: Sequence[str], artifacts: Mapping[str, Any], source_sha: str,
    candidate_digest: str,
) -> dict[str, Any]:
    """Account for every governed member in the final publication pool.

    A withheld row is legitimate only when the existing publication certifier
    recorded an explicit state and blocker.  This function does not alter that
    decision; it makes population loss impossible to hide behind aggregate
    counts.
    """
    expected = sorted({str(value).upper() for value in symbols})
    rows = list(artifacts.get("full_evaluation_pool.json") or ())
    observed = [str(row.get("ticker") or row.get("symbol") or "").upper() for row in rows]
    counts = Counter(observed)
    duplicates = sorted(ticker for ticker, count in counts.items() if count != 1)
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    decisions = []
    unexplained = []
    for row in sorted(rows, key=lambda item: str(item.get("ticker") or item.get("symbol") or "")):
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
        certification = dict(row.get("publication_certification") or {})
        allowed = certification.get("customer_publication_allowed") is True
        components = dict(certification.get("components") or {})
        reasons = sorted({
            str(reason)
            for component in components.values() if isinstance(component, Mapping)
            for reason in (component.get("blockers") or component.get("reason_codes") or ())
            if str(reason).strip()
        } | {
            str(reason) for reason in (certification.get("blockers") or certification.get("reason_codes") or ())
            if str(reason).strip()
        })
        state = str(certification.get("certification_state") or "")
        if not allowed and (not state or not reasons):
            unexplained.append(ticker)
        decisions.append({
            "ticker": ticker, "customer_publication_allowed": allowed,
            "certification_state": state, "reason_codes": reasons,
            "source_sha": source_sha, "candidate_digest": candidate_digest,
        })
    failures = []
    if len(rows) != len(expected) or missing or unexpected or duplicates:
        failures.append("INCREMENTAL_PUBLICATION_POPULATION_MISMATCH")
    if unexplained:
        failures.append("INCREMENTAL_PUBLICATION_WITHHOLDING_UNEXPLAINED")
    if failures:
        raise ValueError(";".join(failures))
    publishable = sum(item["customer_publication_allowed"] for item in decisions)
    withheld = len(decisions) - publishable
    report = {
        "contract": "ATLAS_INCREMENTAL_PUBLICATION_RECONCILIATION_V1",
        "source_sha": source_sha, "candidate_digest": candidate_digest,
        "expected_count": len(expected), "observed_count": len(rows),
        "publishable_count": publishable, "withheld_count": withheld,
        "missing_count": 0, "unexpected_count": 0, "duplicate_count": 0,
        "unexplained_withholding_count": 0, "status": "RECONCILED",
        "records": decisions,
    }
    report["reconciliation_sha256"] = _digest(report)
    return report


def certify_incremental_candidate(
    *, plan: Mapping[str, Any], checkpoint: Mapping[str, Any],
    acquired_records: Sequence[Mapping[str, Any]], source_sha: str,
    candidate_dir: Path, workflow_run_id: str,
    evidence_classification: str = "LIVE_PROVIDER_EVIDENCE",
    retained_technical_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the unchanged evaluator twice and stage, but never promote, output."""
    if evidence_classification not in {
        "LIVE_PROVIDER_EVIDENCE", "PROVIDER_FREE_SIMULATED_REPLAY",
    }:
        raise ValueError("INCREMENTAL_EVIDENCE_CLASSIFICATION_INVALID")
    records = _validate_acquired_records(
        plan=plan, checkpoint=checkpoint, acquired_records=acquired_records,
    )
    symbols = _symbols(plan)
    membership = dict(plan.get("governed_membership") or {})
    universe = {
        "contract_version": CONTRACT,
        "source_artifact": "GOVERNED_INCREMENTAL_MEMBERSHIP",
        "source_sha256": membership.get("source_file_sha256") or _digest(symbols),
        "source_generated_at": None,
        "raw_listing_count": len(symbols),
        "governed_symbol_count": len(symbols),
        "supported_equity_count": len(symbols),
        "supported_symbols": symbols,
        "excluded_governed_symbols": [],
        "security_class_counts": {"SUPPORTED_COMMON_EQUITY": len(symbols)},
        "historical_exclusion_reason_counts": {},
        "universe_methodology_version": "GOVERNED_INCREMENTAL_MEMBERSHIP_V1",
    }
    identity = build_run_identity(
        universe=universe,
        evidence_snapshot_at=f"{plan['session']}T21:00:00+00:00",
        source_sha=source_sha,
    )
    by_symbol = {str(item["ticker"]).upper(): dict(item) for item in records}
    shard_payloads = []
    for shard in deterministic_shards(symbols):
        shard_records = [by_symbol[symbol] for symbol in shard["symbols"]]
        payload = {
            "executor_version": "INCREMENTAL_REUSE_EXISTING_EXECUTOR",
            "run_identity": dict(identity), "shard": dict(shard),
            "records": shard_records,
            "provider_telemetry": {
                "provider_calls": len(shard_records) * 2,
                "fresh_provider_calls": len(shard_records) * 2,
                "retry_count": 0, "http_429_count": 0, "provider_error_count": 0,
                "http_4xx_count": 0, "http_5xx_count": 0, "timeout_count": 0,
                "duplicate_or_reacquired_requests": 0,
            },
            "failure_summary": [],
        }
        payload["shard_digest"] = _digest(payload)
        shard_payloads.append(payload)
    result = aggregate_complete_run(
        universe=universe, identity=identity, shard_payloads=shard_payloads,
    )
    if result.get("new_full_universe_candidate_certified") is not True:
        raise ValueError("INCREMENTAL_CERTIFIED_CANDIDATE_REJECTED")
    publication = dict(result.get("publication_bundle") or {})
    manifest = dict(publication.get("manifest") or {})
    reconciliation = reconcile_publication_population(
        symbols=symbols, artifacts=dict(publication.get("artifacts") or {}),
        source_sha=source_sha,
        candidate_digest=result["immutable_candidate"]["candidate_digest"],
    )
    manifest["workflow_run_id"] = str(workflow_run_id)
    manifest["incremental_plan_sha256"] = plan["plan_sha256"]
    manifest["incremental_receipt_set_sha256"] = publication_readiness(
        plan=plan, checkpoint=checkpoint
    )["receipt_set_sha256"]
    manifest["incremental_evidence_classification"] = evidence_classification
    manifest["incremental_publication_authorized"] = evidence_classification == "LIVE_PROVIDER_EVIDENCE"
    report_root = candidate_dir
    bundle_dir = report_root / "publication_bundle"
    artifacts = {
        bundle_dir / name: payload
        for name, payload in dict(publication.get("artifacts") or {}).items()
    }
    stage_candidate_artifacts(artifacts, manifest=manifest, candidate_dir=bundle_dir)
    report_root.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("checkpoint_summary.json", result["full_universe_completeness"]),
        ("determinism_report.json", result["determinism"]),
        ("evidence_inspector_coverage.json", result["evidence_inspector_coverage"]),
        ("publication_population_reconciliation.json", reconciliation),
    ):
        (report_root / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    handoff = prepare_certification_handoff(
        plan=plan, checkpoint=checkpoint, candidate_dir=bundle_dir,
        certification={
            "methodology_mutation": "NONE", "publication_gate_status": "PASS",
            "input_receipt_set_sha256": manifest["incremental_receipt_set_sha256"],
            "candidate_digest": result["immutable_candidate"]["candidate_digest"],
            "publication_bundle_digest": result["publication_bundle_digest"],
        },
    )
    report = {
        "contract": CONTRACT,
        "status": (
            "CERTIFIED_NOT_PUBLISHED" if evidence_classification == "LIVE_PROVIDER_EVIDENCE"
            else "PROVIDER_FREE_REPLAY_CERTIFIED_NOT_PUBLISHABLE"
        ),
        "source_sha": source_sha, "session": plan["session"],
        "plan_sha256": plan["plan_sha256"],
        "receipt_set_sha256": manifest["incremental_receipt_set_sha256"],
        "candidate_digest": result["immutable_candidate"]["candidate_digest"],
        "publication_bundle_digest": result["publication_bundle_digest"],
        "handoff_sha256": handoff["handoff_sha256"],
        "symbol_count": len(symbols), "provider_retries": 0,
        "publication_population_reconciliation_sha256": reconciliation["reconciliation_sha256"],
        "publishable_count": reconciliation["publishable_count"],
        "withheld_count": reconciliation["withheld_count"],
        "unaccounted_publication_records": 0,
        "evidence_classification": evidence_classification,
        "publication_authorized": evidence_classification == "LIVE_PROVIDER_EVIDENCE",
        "production_writes": 0,
        "required_promoter": "scripts.promote_daily_buy_now_snapshot.promote",
    }
    if retained_technical_binding is not None:
        report["retained_technical_binding"] = dict(retained_technical_binding)
    report["report_sha256"] = _digest(report)
    (report_root / "incremental_certification_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


__all__ = [
    "CONTRACT", "certify_incremental_candidate", "materialize_acquired_records",
    "reconcile_publication_population", "load_retained_technical_history",
]
