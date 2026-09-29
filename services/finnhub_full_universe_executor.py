"""Production-shaped, non-publishing Finnhub full-universe certification executor.

The executor owns orchestration only. Provider normalization and analytical
evaluation are delegated to the already-proven canonical path. Shards persist
acquired canonical rows and completed bars; the aggregator constructs peer
evidence once and evaluates every target from one immutable snapshot.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

from engines.methodology_registry import REGISTRY_VERSION
from services.evidence_inspector import inspect_ticker
from services.finnhub_canonical_authority import AUTHORITY_VERSION, FinnhubCanonicalAdapter
from services.full_universe_brain_certification import (
    REPORT_CARD_PROSPECTIVE_ACTIVE, build_immutable_candidate, certify_complete_run,
    checkpoint_identity, compare_deterministic_candidates, validate_checkpoint,
)
from services.professional_valuation_evidence import apply_peer_multiple_evidence
from services.positive_action_revalidation import revalidate_buy_now
from scripts.finnhub_canonical_proving_set import _fetch, _normalized_row, evaluate_canonical_row
from services.technical_intelligence.engine import DailyBar


VERSION = "ATLAS_FINNHUB_FULL_UNIVERSE_EXECUTOR_V1"
NORMALIZATION_VERSION = "FINNHUB_CANONICAL_NORMALIZATION_V1"
PROVIDER_EVIDENCE_VERSION = "FINNHUB_CANONICAL_EVIDENCE_V1"
VALUATION_VERSION = "ATLAS_PROFESSIONAL_VALUATION_V2"
PILLAR_VERSION = "ATLAS_SIX_PILLAR_FROZEN_V1"
ACTION_VERSION = "ATLAS_CANONICAL_ACTION_V1"
SHARD_SIZE = 150
AUTHORIZED_ACQUISITION_FAMILIES = (
    "company_profile", "financial_statements", "basic_financials", "historical_ohlcv",
)
FORWARD_ROUTE_IDS = frozenset(("VAL_FORWARD_PE_V1", "VAL_EV_EBITDA_V1", "VAL_FCFF_DCF_V1"))
ACTION_ALIASES = {
    "ACCUMULATE": "BUILD_A_POSITION",
    "WAIT_FOR_ENTRY": "WAIT_FOR_BETTER_ENTRY",
    "WAIT": "WAIT_FOR_CONFIRMATION",
    # DATA_LIMITED is an internal fail-closed engine state, not a customer
    # Action. Preserve the withheld decision as the governed terminal Action.
    "DATA_LIMITED": "RATING_NOT_PUBLISHED",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def build_run_identity(*, universe: Mapping[str, Any], evidence_snapshot_at: str,
                       source_sha: str) -> dict[str, Any]:
    base = checkpoint_identity(
        universe=universe, evidence_snapshot_at=evidence_snapshot_at,
        source_sha=source_sha, provider_authority_version=AUTHORITY_VERSION,
    )
    extended = {
        **base, "executor_version": VERSION, "normalization_version": NORMALIZATION_VERSION,
        "methodology_version": REGISTRY_VERSION, "report_card_prospective_active": False,
    }
    return {**extended, "run_identity_sha256": _digest(extended)}


def validate_executor_checkpoint(record: Mapping[str, Any], identity: Mapping[str, Any]) -> None:
    """Require both the base checkpoint and every executor identity dimension."""
    validate_checkpoint(record, identity)
    if record.get("run_identity_sha256") != identity.get("run_identity_sha256"):
        raise ValueError("checkpoint belongs to a different executor run identity")


def deterministic_shards(symbols: Sequence[str], *, shard_size: int = SHARD_SIZE) -> list[dict[str, Any]]:
    ordered = sorted({str(symbol).upper().strip() for symbol in symbols if str(symbol).strip()})
    if shard_size < 1:
        raise ValueError("shard_size must be positive")
    result = []
    for index, start in enumerate(range(0, len(ordered), shard_size)):
        values = ordered[start:start + shard_size]
        result.append({
            "shard_id": f"shard-{index:03d}", "index": index,
            "symbols": values, "symbol_count": len(values),
            "symbol_list_sha256": _digest(values),
        })
    return result


def deterministic_canary(symbols: Sequence[str], size: int) -> list[str]:
    """Select an order-independent, non-hand-picked canary from the frozen universe."""
    ranked = sorted(
        {str(symbol).upper().strip() for symbol in symbols if str(symbol).strip()},
        key=lambda symbol: (hashlib.sha256(f"{VERSION}:{size}:{symbol}".encode()).hexdigest(), symbol),
    )
    if len(ranked) < size:
        raise ValueError("canary exceeds frozen universe")
    return sorted(ranked[:size])


def serialize_bars(bars: Sequence[DailyBar]) -> list[dict[str, Any]]:
    return [{
        "symbol": item.ticker, "timestamp": item.timestamp.isoformat(),
        "open": item.open, "high": item.high, "low": item.low,
        "close": item.close, "volume": item.volume, "completed": item.completed,
    } for item in bars]


def deserialize_bars(items: Sequence[Mapping[str, Any]]) -> list[DailyBar]:
    return [DailyBar(
        str(item["symbol"]), datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")),
        float(item["open"]), float(item["high"]), float(item["low"]),
        float(item["close"]), float(item["volume"]), bool(item.get("completed", True)),
    ) for item in items]


def _classification(catalog: Mapping[str, Mapping[str, Any]], symbol: str) -> dict[str, Any]:
    return dict(catalog.get(symbol) or {"ticker": symbol})


def acquire_shard(
    *, adapter: FinnhubCanonicalAdapter, shard: Mapping[str, Any],
    identity: Mapping[str, Any], catalog: Mapping[str, Mapping[str, Any]],
    pace_seconds: float = 1.05,
    checkpoint_dir: Path | None = None,
) -> dict[str, Any]:
    """Acquire each authorized family once for every symbol in a shard."""
    started = time.monotonic()
    rows, failures, calls, cache_hits, retry_count = [], [], 0, 0, 0
    cache: dict[tuple[str, str], dict[str, Any]] = {}
    for symbol in shard["symbols"]:
        checkpoint_path = checkpoint_dir / f"{symbol}.json" if checkpoint_dir else None
        if checkpoint_path and checkpoint_path.exists():
            saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if saved.get("run_identity_sha256") == identity.get("run_identity_sha256"):
                rows.append(saved["acquisition"])
                cache_hits += len(AUTHORIZED_ACQUISITION_FAMILIES)
                continue
        records: dict[str, dict[str, Any]] = {}
        for capability in AUTHORIZED_ACQUISITION_FAMILIES:
            key = (symbol, capability)
            if key in cache:
                cache_hits += 1
                records[capability] = cache[key]
                continue
            params: dict[str, Any] = {}
            if capability == "historical_ohlcv":
                snapshot = datetime.fromisoformat(str(identity["evidence_snapshot_at"]).replace("Z", "+00:00"))
                params = {"resolution": "D", "from": int(snapshot.timestamp()) - 400 * 86400,
                          "to": int(snapshot.timestamp())}
            record = {}
            for attempt in range(3):
                record = _fetch(adapter, capability, symbol, pace_seconds, **params)
                calls += 1
                reason = str((record.get("payload") or {}).get("reason") or "").upper()
                retryable = reason == "HTTP_429" or any(reason == f"HTTP_{status}" for status in range(500, 600))
                if not retryable or attempt == 2:
                    break
                retry_count += 1
                # Deterministic jitter prevents shard lockstep without changing
                # analytical results or immutable evidence identity.
                jitter = int(hashlib.sha256(f"{symbol}:{capability}:{attempt}".encode()).hexdigest()[:4], 16) / 65535
                time.sleep((2 ** attempt) + jitter)
            cache[key] = record
            records[capability] = record
        row, bars, blockers = _normalized_row(symbol, _classification(catalog, symbol), records)
        entitlement = sum(
            (record.get("provenance") or {}).get("certification_status") == "ENTITLEMENT_UNAVAILABLE"
            for record in records.values()
        )
        item = {
            "ticker": symbol, "row": row, "bars": serialize_bars(bars),
            "blockers": blockers, "credential_entitlement_failures": entitlement,
            "shadow_evidence_leakage": any(
                (record.get("provenance") or {}).get("certification_status") in {"UNVERIFIED_SHADOW", "SHADOW_ONLY"}
                for record in records.values()
            ),
            "authority_violations": sum(
                str((record.get("provenance") or {}).get("provider") or "").upper() not in {"", "FINNHUB"}
                for record in records.values()
            ),
            "evidence_ids": sorted(filter(None, (
                (record.get("provenance") or {}).get("raw_evidence_id") for record in records.values()
            ))),
        }
        rows.append(item)
        if checkpoint_path:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "run_identity_sha256": identity["run_identity_sha256"],
                "acquisition": item,
            }, sort_keys=True, default=str), encoding="utf-8")
            temporary.replace(checkpoint_path)
        if blockers:
            failures.append({"ticker": symbol, "blockers": blockers})
    elapsed = max(time.monotonic() - started, 1e-9)
    payload = {
        "executor_version": VERSION, "run_identity": dict(identity),
        "shard": dict(shard), "records": rows,
        "provider_telemetry": {
            "provider_calls": calls, "cache_hits": cache_hits,
            "calls_avoided": cache_hits, "retry_count": retry_count,
            "elapsed_seconds": round(elapsed, 3),
            "symbols_per_minute": round(len(rows) * 60 / elapsed, 3),
        },
        "failure_summary": failures,
    }
    return {**payload, "shard_digest": _digest(payload)}


def validate_shards(*, universe: Mapping[str, Any], identity: Mapping[str, Any],
                    shards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    expected = set(universe.get("supported_symbols") or ())
    records, seen_shards = [], set()
    for payload in shards:
        if (payload.get("run_identity") or {}).get("run_identity_sha256") != identity.get("run_identity_sha256"):
            raise ValueError("shard belongs to a different immutable run identity")
        shard_id = (payload.get("shard") or {}).get("shard_id")
        if not shard_id or shard_id in seen_shards:
            raise ValueError("missing or duplicate shard identity")
        seen_shards.add(shard_id)
        values = list(payload.get("records") or ())
        symbols = [str(item.get("ticker") or "").upper() for item in values]
        if _digest(sorted(symbols)) != (payload.get("shard") or {}).get("symbol_list_sha256"):
            raise ValueError("shard symbol digest mismatch")
        records.extend(values)
    symbols = [str(item.get("ticker") or "").upper() for item in records]
    duplicates = [symbol for symbol, count in Counter(symbols).items() if count != 1]
    if duplicates or set(symbols) != expected:
        raise ValueError("full-universe shard accounting mismatch")
    return records


def _route_distribution(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, Counter[str]] = {}
    for evaluation in evaluations:
        professional = (evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}
        for model in professional.get("models") or ():
            result.setdefault(str(model.get("methodology_id")), Counter())[str(model.get("status"))] += 1
    return {key: dict(sorted(value.items())) for key, value in sorted(result.items())}


def _pillar_distribution(terminal: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    keys = ("technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality")
    result = {}
    for key in keys:
        values = [(item.get("evaluation") or {}).get(key) for item in terminal]
        result[key] = {
            "available": sum(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in values),
            "unavailable": sum(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values),
        }
    return result


def _buy_now_report(terminal: Sequence[Mapping[str, Any]], universe: Mapping[str, Any],
                    identity: Mapping[str, Any]) -> dict[str, Any]:
    records = []
    supported = set(universe.get("supported_symbols") or ())
    for item in terminal:
        if item.get("canonical_action") != "BUY_NOW":
            continue
        evaluation = item.get("evaluation") or {}
        revalidation = item.get("buy_now_revalidation") or {}
        checks = {
            "frozen_universe_member": item.get("ticker") in supported,
            "immutable_run_identity": item.get("run_identity_sha256") == identity.get("run_identity_sha256"),
            "canonical_evidence": bool(evaluation.get("evidence_ids")),
            "canonical_action": ((evaluation.get("guidance") or {}).get("state") == "BUY_NOW"),
            "decision_digest": bool(evaluation.get("decision_digest")),
            "exact_snapshot_revalidation": revalidation.get("status") == "BUY_NOW_REVALIDATED",
            "matching_decision_digest": revalidation.get("source_decision_digest") == evaluation.get("decision_digest"),
        }
        records.append({
            "ticker": item.get("ticker"), "checks": checks,
            "publication_eligible": all(checks.values()),
            "evaluation_digest": item.get("evaluation_digest"),
            "universe_sha256": universe.get("source_sha256"),
            "blockers": list(revalidation.get("blockers") or ()),
        })
    return {
        "status": "PASS" if all(item["publication_eligible"] for item in records) else "FAIL",
        "canonical_buy_now_count": len(records),
        "publishable_buy_now_count": sum(item["publication_eligible"] for item in records),
        "records": records,
    }


def _terminal_from_acquisition(item: Mapping[str, Any], identity: Mapping[str, Any]) -> dict[str, Any]:
    blockers = list(item.get("blockers") or ())
    if item.get("credential_entitlement_failures"):
        state = "PROVIDER_DATA_UNAVAILABLE"
    elif any("CLASSIFICATION" in value for value in blockers):
        state = "CLASSIFICATION_UNRESOLVED"
    elif any("TECHNICAL_HISTORY" in value for value in blockers):
        state = "TECHNICAL_INPUT_INCOMPLETE"
    elif blockers:
        state = "PROVIDER_DATA_UNAVAILABLE"
    else:
        state = "ATLAS_INTEGRATION_FAILURE"
        blockers = ["ACQUISITION_ROW_UNEXPECTEDLY_MISSING"]
    return {
        "ticker": item["ticker"], "terminal_data_state": state,
        "canonical_action": "RATING_NOT_PUBLISHED",
        "valuation_routes": {"P_FCF": "EVIDENCE_INSUFFICIENT"},
        "reason_codes": blockers, "credential_entitlement_failures": int(item.get("credential_entitlement_failures") or 0),
        "checkpoint_identity_sha256": identity["checkpoint_identity_sha256"],
        "run_identity_sha256": identity["run_identity_sha256"],
    }


def evaluate_records(*, identity: Mapping[str, Any], acquired: Sequence[Mapping[str, Any]],
                     checkpoint_dir: Path | None = None) -> dict[str, Any]:
    """Build peer evidence once, then evaluate only target rows from that scope."""
    evaluated_at = datetime.fromisoformat(str(identity["evidence_snapshot_at"]).replace("Z", "+00:00"))
    source_rows = [dict(item["row"]) for item in acquired if item.get("row") is not None]
    prepared = apply_peer_multiple_evidence(source_rows)
    prepared_by_symbol = {str(row.get("ticker")): row for row in prepared}
    acquired_by_symbol = {str(item.get("ticker")): item for item in acquired}
    terminal, evaluations, inspector_failures = [], [], []
    forward_route_leakage = False
    shadow_evidence_leakage = any(bool(item.get("shadow_evidence_leakage")) for item in acquired)
    authority_violations = sum(int(item.get("authority_violations") or 0) for item in acquired)
    for symbol in sorted(acquired_by_symbol):
        item = acquired_by_symbol[symbol]
        checkpoint_path = checkpoint_dir / f"{symbol}.json" if checkpoint_dir else None
        if checkpoint_path and checkpoint_path.exists():
            saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            try:
                validate_executor_checkpoint(saved, identity)
                terminal.append(saved)
                if isinstance(saved.get("evaluation"), Mapping):
                    evaluation = saved["evaluation"]
                    evaluations.append(evaluation)
                    professional = (evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}
                    forward_route_leakage |= any(
                        model.get("methodology_id") in FORWARD_ROUTE_IDS and model.get("status") == "PUBLISHED"
                        for model in professional.get("models") or ()
                    )
                continue
            except ValueError:
                pass
        row = prepared_by_symbol.get(symbol)
        if row is None:
            terminal_record = _terminal_from_acquisition(item, identity)
            terminal.append(terminal_record)
            if checkpoint_path:
                checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = checkpoint_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(terminal_record, sort_keys=True, default=str), encoding="utf-8")
                temporary.replace(checkpoint_path)
            continue
        try:
            evaluation, diagnostics = evaluate_canonical_row(
                row, deserialize_bars(item.get("bars") or ()), evaluated_at=evaluated_at,
            )
            traceability = diagnostics.get("inspector_traceability") or {}
            if traceability.get("status") != "PASS":
                inspector_failures.append(symbol)
                raise ValueError("UNTRACEABLE_ANALYTICAL_INPUT")
            states = diagnostics.get("valuation_route_states") or {}
            forward_route_leakage |= any(states.get(key) == "PUBLISHED" for key in FORWARD_ROUTE_IDS)
            action = str((evaluation.get("guidance") or {}).get("state") or "RATING_NOT_PUBLISHED")
            action = ACTION_ALIASES.get(action, action)
            revalidation = revalidate_buy_now(evaluation)
            buy_now_eligible = action != "BUY_NOW" or (
                revalidation.get("status") == "BUY_NOW_REVALIDATED"
                and revalidation.get("source_decision_digest") == evaluation.get("decision_digest")
            )
            professional = (evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}
            p_fcf = next((model for model in professional.get("models") or () if model.get("methodology_id") == "VAL_P_FCF_V1"), {})
            terminal_record = {
                "ticker": symbol, "terminal_data_state": "CERTIFIED_EVALUATION",
                "canonical_action": action,
                "valuation_routes": {"P_FCF": "CERTIFIED" if p_fcf.get("status") == "PUBLISHED" else "EVIDENCE_INSUFFICIENT"},
                "reason_codes": [], "credential_entitlement_failures": 0,
                "buy_now_publication_eligible": buy_now_eligible,
                "buy_now_revalidation": revalidation,
                "checkpoint_identity_sha256": identity["checkpoint_identity_sha256"],
                "run_identity_sha256": identity["run_identity_sha256"],
                "evaluation": evaluation, "evaluation_digest": _digest(evaluation),
            }
            validate_executor_checkpoint(terminal_record, identity)
            terminal.append(terminal_record); evaluations.append(evaluation)
        except Exception as exc:
            terminal.append({
                "ticker": symbol, "terminal_data_state": "ATLAS_INTEGRATION_FAILURE",
                "canonical_action": "RATING_NOT_PUBLISHED",
                "valuation_routes": {"P_FCF": "EVIDENCE_INSUFFICIENT"},
                "reason_codes": [str(exc)[:160]], "credential_entitlement_failures": 0,
                "checkpoint_identity_sha256": identity["checkpoint_identity_sha256"],
                "run_identity_sha256": identity["run_identity_sha256"],
            })
        if checkpoint_path:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(terminal[-1], sort_keys=True, default=str), encoding="utf-8")
            temporary.replace(checkpoint_path)
    for record in terminal:
        validate_executor_checkpoint(record, identity)
    return {
        "terminal_records": terminal, "evaluation_count": len(evaluations),
        "inspector": {"expected_parameter_count": 91, "failures": inspector_failures,
                      "status": "PASS" if not inspector_failures else "FAIL"},
        "forward_route_leakage": forward_route_leakage,
        "shadow_evidence_leakage": shadow_evidence_leakage,
        "authority_violations": authority_violations,
        "valuation_route_distribution": _route_distribution(evaluations),
    }


def aggregate_complete_run(*, universe: Mapping[str, Any], identity: Mapping[str, Any],
                           shard_payloads: Sequence[Mapping[str, Any]],
                           candidate_eligible: bool = True,
                           checkpoint_dir: Path | None = None) -> dict[str, Any]:
    acquired = validate_shards(universe=universe, identity=identity, shards=shard_payloads)
    first = evaluate_records(identity=identity, acquired=acquired, checkpoint_dir=checkpoint_dir)
    completeness = certify_complete_run(
        universe=universe, records=first["terminal_records"],
        acquisition_complete=True, decision_processing_complete=True,
    )
    candidate = None
    determinism = {"status": "NOT_ELIGIBLE_INCOMPLETE_RUN"}
    if candidate_eligible and completeness["state"] == "FULL_UNIVERSE_CERTIFIED" and not first["forward_route_leakage"]:
        candidate = build_immutable_candidate(
            universe=universe, identity=identity, records=first["terminal_records"],
            completeness=completeness, methodology_version=REGISTRY_VERSION,
            provider_evidence_version=PROVIDER_EVIDENCE_VERSION,
            valuation_version=VALUATION_VERSION, pillar_version=PILLAR_VERSION,
            action_engine_version=ACTION_VERSION,
        )
        second = evaluate_records(identity=identity, acquired=list(reversed(acquired)))
        second_completeness = certify_complete_run(
            universe=universe, records=second["terminal_records"],
            acquisition_complete=True, decision_processing_complete=True,
        )
        second_candidate = build_immutable_candidate(
            universe=universe, identity=identity, records=second["terminal_records"],
            completeness=second_completeness, methodology_version=REGISTRY_VERSION,
            provider_evidence_version=PROVIDER_EVIDENCE_VERSION,
            valuation_version=VALUATION_VERSION, pillar_version=PILLAR_VERSION,
            action_engine_version=ACTION_VERSION,
        )
        determinism = compare_deterministic_candidates(candidate, second_candidate)
    calls = sum(int((payload.get("provider_telemetry") or {}).get("provider_calls") or 0) for payload in shard_payloads)
    cache_hits = sum(int((payload.get("provider_telemetry") or {}).get("cache_hits") or 0) for payload in shard_payloads)
    retries = sum(int((payload.get("provider_telemetry") or {}).get("retry_count") or 0) for payload in shard_payloads)
    elapsed = sum(float((payload.get("provider_telemetry") or {}).get("elapsed_seconds") or 0) for payload in shard_payloads)
    canary_coverage = _canary_coverage(acquired) if not candidate_eligible else None
    canary_coverage_pass = canary_coverage is None or canary_coverage["status"] == "PASS"
    buy_now_provenance = _buy_now_report(first["terminal_records"], universe, identity)
    return {
        "executor_version": VERSION, "run_identity": dict(identity),
        "full_universe_completeness": completeness,
        "evidence_inspector_coverage": first["inspector"],
        "forward_route_leakage": first["forward_route_leakage"],
        "shadow_evidence_leakage": first["shadow_evidence_leakage"],
        "authority_violations": first["authority_violations"],
        "valuation_route_distribution": first["valuation_route_distribution"],
        "pillar_distribution": _pillar_distribution(first["terminal_records"]),
        "action_distribution": completeness.get("action_counts") or {},
        "provider_call_telemetry": {
            "provider_calls": calls, "cache_hits": cache_hits, "calls_avoided": cache_hits,
            "retry_count": retries, "retry_rate": round(retries / calls, 6) if calls else 0.0,
            "summed_shard_elapsed_seconds": round(elapsed, 3),
            "symbols_per_minute_serial_equivalent": round(len(acquired) * 60 / elapsed, 3) if elapsed else 0.0,
        },
        "buy_now_provenance": buy_now_provenance,
        "canary_coverage": canary_coverage,
        "immutable_candidate": candidate, "determinism": determinism,
        "state": (
            "FINNHUB_FULL_UNIVERSE_EXECUTOR_CERTIFIED"
            if candidate and determinism.get("status") == "PASS" and not first["forward_route_leakage"]
            and buy_now_provenance["status"] == "PASS" and first["inspector"]["status"] == "PASS"
            and completeness.get("credential_entitlement_failures") == 0
            and not completeness.get("atlas_integration_failures")
            and not first["shadow_evidence_leakage"] and first["authority_violations"] == 0
            else "CANARY_PASS"
            if not candidate_eligible and completeness["state"] == "FULL_UNIVERSE_CERTIFIED"
            and not first["forward_route_leakage"] and first["inspector"]["status"] == "PASS"
            and completeness.get("credential_entitlement_failures") == 0
            and not completeness.get("atlas_integration_failures")
            and not first["shadow_evidence_leakage"] and first["authority_violations"] == 0
            and canary_coverage_pass
            else "FULL_UNIVERSE_RUN_INCOMPLETE"
        ),
        "report_card_prospective_active": REPORT_CARD_PROSPECTIVE_ACTIVE,
        "production_schedule_cutover": False,
    }


def _canary_coverage(acquired: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [item.get("row") for item in acquired if isinstance(item.get("row"), Mapping)]
    sectors = {str(row.get("sector")) for row in rows if row.get("sector")}
    industries = {str(row.get("industry")) for row in rows if row.get("industry")}
    cap_buckets, price_buckets, profit_states = set(), set(), set()
    for row in rows:
        cap, price, fcf = row.get("market_cap"), row.get("current_price"), row.get("normalized_fcf")
        if isinstance(cap, (int, float)):
            cap_buckets.add("SMALL" if cap < 2e9 else "MID" if cap < 10e9 else "LARGE")
        if isinstance(price, (int, float)):
            price_buckets.add("LOW" if price < 10 else "MID" if price < 100 else "HIGH")
        if isinstance(fcf, (int, float)):
            profit_states.add("POSITIVE_FCF" if fcf > 0 else "NONPOSITIVE_FCF")
    incomplete = sum(item.get("row") is None for item in acquired)
    checks = {
        "multiple_sectors": len(sectors) >= 3, "multiple_industries": len(industries) >= 5,
        "multiple_market_cap_ranges": len(cap_buckets) >= 2,
        "multiple_price_ranges": len(price_buckets) >= 2,
        "profitable_and_loss_making": len(profit_states) >= 2,
        "complete_and_incomplete_evidence": bool(rows) and incomplete > 0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
        "sector_count": len(sectors), "industry_count": len(industries),
        "market_cap_ranges": sorted(cap_buckets), "price_ranges": sorted(price_buckets),
        "profit_states": sorted(profit_states), "complete_count": len(rows),
        "incomplete_count": incomplete,
    }


__all__ = [
    "ACTION_VERSION", "AUTHORIZED_ACQUISITION_FAMILIES", "NORMALIZATION_VERSION",
    "PROVIDER_EVIDENCE_VERSION", "SHARD_SIZE", "VERSION", "acquire_shard",
    "aggregate_complete_run", "build_run_identity", "deserialize_bars",
    "deterministic_canary", "deterministic_shards", "evaluate_records",
    "serialize_bars", "validate_executor_checkpoint", "validate_shards",
]
