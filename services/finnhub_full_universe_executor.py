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
import resource
import sys
import time
from typing import Any, Callable, Mapping, Sequence

from engines.methodology_registry import REGISTRY_VERSION
from services.evidence_inspector import inspect_ticker
from services.finnhub_canonical_authority import AUTHORITY_VERSION, FinnhubCanonicalAdapter
from services.finnhub_shadow_provider import FINNHUB_PAID_CORE_CERTIFICATION_LICENSE, FinnhubShadowAdapter
from services.finnhub_forward_valuation_bridge import apply_forward_inputs
from services.finnhub_rate_governance import FinnhubRateGovernor
from services.executor_publication_bridge import build_publication_bundle, bridge_evaluation
from services.full_universe_brain_certification import (
    REPORT_CARD_PROSPECTIVE_ACTIVE, build_immutable_candidate, certify_complete_run,
    checkpoint_identity, compare_deterministic_candidates, validate_checkpoint,
)
from services.professional_valuation_evidence import apply_peer_multiple_evidence
from scripts.finnhub_canonical_proving_set import _fetch, _normalized_row, evaluate_canonical_row
from services.technical_intelligence.engine import DailyBar


VERSION = "ATLAS_FINNHUB_FULL_UNIVERSE_EXECUTOR_V2_MULTI_METHOD"
SHARD_CHECKPOINT_CONTRACT_VERSION = "ATLAS_FINNHUB_CERTIFIED_SHARD_CHECKPOINT_V1"
TRANSIENT_RETRY_POLICY_VERSION = "ATLAS_FINNHUB_TRANSIENT_RETRY_V1"
MAX_TRANSIENT_RETRIES = 2
TRANSIENT_HTTP_STATUSES = frozenset({500, 502, 503, 504})
NORMALIZATION_VERSION = "FINNHUB_CANONICAL_NORMALIZATION_V1"
PROVIDER_EVIDENCE_VERSION = "FINNHUB_CANONICAL_EVIDENCE_V1"
VALUATION_VERSION = "ATLAS_PROFESSIONAL_VALUATION_V2"
PILLAR_VERSION = "ATLAS_SIX_PILLAR_FROZEN_V1"
ACTION_VERSION = "ATLAS_CANONICAL_ACTION_V1"
SHARD_SIZE = 150
CORE_ACQUISITION_FAMILIES = (
    "company_profile", "financial_statements", "basic_financials", "historical_ohlcv",
)
CERTIFIED_FORWARD_ACQUISITION_FAMILIES = ("eps_estimates", "ebitda_estimates")
AUTHORIZED_ACQUISITION_FAMILIES = CORE_ACQUISITION_FAMILIES + CERTIFIED_FORWARD_ACQUISITION_FAMILIES
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


def classify_provider_failure(reason: str) -> str:
    """Classify a serialized provider failure without broadening retry scope."""
    normalized = str(reason or "").strip().upper()
    if not normalized:
        return "NONE"
    if normalized == "HTTP_429":
        return "GOVERNANCE_STOP"
    if normalized.startswith("HTTP_"):
        try:
            status = int(normalized.split("_", 1)[1])
        except (TypeError, ValueError):
            return "NON_RETRYABLE"
        return "TRANSIENT" if status in TRANSIENT_HTTP_STATUSES else "NON_RETRYABLE"
    transient_tokens = (
        "READTIMEOUT", "READ_TIMEOUT", "CONNECTTIMEOUT", "CONNECT_TIMEOUT",
        "CONNECTIONRESET", "CONNECTION_RESET", "CONNECTION RESET",
    )
    if any(token in normalized for token in transient_tokens):
        return "TRANSIENT"
    return "NON_RETRYABLE"


def transient_retry_delay(symbol: str, capability: str, retry_index: int) -> float:
    """Return bounded exponential delay plus deterministic sub-second jitter."""
    if retry_index < 0 or retry_index >= MAX_TRANSIENT_RETRIES:
        raise ValueError("retry index outside governed transient retry budget")
    jitter = int(hashlib.sha256(
        f"{TRANSIENT_RETRY_POLICY_VERSION}:{symbol}:{capability}:{retry_index}".encode()
    ).hexdigest()[:4], 16) / 65535
    return min(4.0, float(2 ** retry_index) + jitter)


def shard_checkpoint_contract(
    *, identity: Mapping[str, Any], shard: Mapping[str, Any], provider_configuration_identity: str,
    global_requests_per_minute: float, burst_ceiling: float, parallel_workers: int,
) -> dict[str, Any]:
    return {
        "checkpoint_contract_version": SHARD_CHECKPOINT_CONTRACT_VERSION,
        "retry_policy_version": TRANSIENT_RETRY_POLICY_VERSION,
        "source_sha": identity.get("source_sha"),
        "run_identity_sha256": identity.get("run_identity_sha256"),
        "provider_configuration_identity": provider_configuration_identity,
        "governed_global_requests_per_minute": float(global_requests_per_minute),
        "burst_ceiling_requests_per_second": float(burst_ceiling),
        "parallel_workers": int(parallel_workers),
        "expected_requests_per_symbol": len(AUTHORIZED_ACQUISITION_FAMILIES),
        "shard_id": shard.get("shard_id"),
        "expected_symbols": list(shard.get("symbols") or ()),
        "expected_symbol_set_sha256": shard.get("symbol_list_sha256"),
    }


def build_certified_shard_checkpoint(
    *, payload: Mapping[str, Any], artifact_digest: str, contract: Mapping[str, Any],
) -> dict[str, Any]:
    records = list(payload.get("records") or ())
    telemetry = dict(payload.get("provider_telemetry") or {})
    expected_symbols = list(contract.get("expected_symbols") or ())
    actual_symbols = [str(item.get("ticker") or "").upper() for item in records]
    if payload.get("shard", {}).get("shard_id") != contract.get("shard_id"):
        raise ValueError("cannot certify shard with mismatched identity")
    if len(records) != len(expected_symbols) or sorted(actual_symbols) != sorted(expected_symbols):
        raise ValueError("cannot certify partial shard payload")
    body = {
        **dict(contract),
        "completed_symbol_count": len(records),
        "provider_call_count": int(telemetry.get("provider_calls") or 0),
        "fresh_provider_call_count": int(telemetry.get("fresh_provider_calls") or 0),
        "retry_count": int(telemetry.get("retry_count") or 0),
        "acquisition_elapsed_seconds": float(telemetry.get("elapsed_seconds") or 0.0),
        "acquisition_digest": payload.get("shard_digest"),
        "artifact_digest": artifact_digest,
        "completion_status": "CERTIFIED_COMPLETE",
    }
    return {**body, "manifest_digest": _digest(body)}


def validate_certified_shard_checkpoint(
    *, payload: Mapping[str, Any], artifact_digest: str, checkpoint: Mapping[str, Any],
    expected_contract: Mapping[str, Any],
) -> None:
    manifest = dict(checkpoint)
    manifest_digest = manifest.pop("manifest_digest", None)
    if manifest_digest != _digest(manifest):
        raise ValueError("certified shard checkpoint manifest digest mismatch")
    for key, value in expected_contract.items():
        if manifest.get(key) != value:
            raise ValueError(f"certified shard checkpoint {key} mismatch")
    if manifest.get("completion_status") != "CERTIFIED_COMPLETE":
        raise ValueError("partial or failed shard checkpoint is not reusable")
    records = list(payload.get("records") or ())
    symbols = [str(item.get("ticker") or "").upper() for item in records]
    if len(records) != len(expected_contract.get("expected_symbols") or ()):
        raise ValueError("certified shard completed symbol count mismatch")
    if sorted(symbols) != sorted(expected_contract.get("expected_symbols") or ()):
        raise ValueError("certified shard symbol set mismatch")
    if manifest.get("completed_symbol_count") != len(records):
        raise ValueError("certified shard manifest symbol count mismatch")
    if manifest.get("acquisition_digest") != payload.get("shard_digest"):
        raise ValueError("certified shard acquisition digest mismatch")
    if manifest.get("artifact_digest") != artifact_digest:
        raise ValueError("certified shard artifact digest mismatch")


def _analytical_projection(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the governed values whose equality proves analytical replay."""
    evaluation = dict(record.get("evaluation") or {})
    professional = dict((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
    models = []
    for model in professional.get("models") or ():
        assumptions = dict(model.get("key_assumptions") or {})
        peer = dict(assumptions.get("peer_evidence") or {})
        included = sorted((dict(item) for item in peer.get("included_peers") or ()), key=_canonical_json)
        excluded = sorted((dict(item) for item in peer.get("excluded_peers") or ()), key=_canonical_json)
        models.append({
            "methodology_id": model.get("methodology_id"), "status": model.get("status"),
            "value": model.get("value"), "weight": model.get("weight"),
            "multiple": assumptions.get("multiple"), "published_median": peer.get("published_median"),
            "included_peers": included, "excluded_peers": excluded,
            "final_peer_set": sorted(peer.get("final_peer_set") or ()),
        })
    return {
        "ticker": record.get("ticker"), "terminal_data_state": record.get("terminal_data_state"),
        "canonical_action": record.get("canonical_action"),
        "normalized_financial_values": (evaluation.get("fundamentals") or {}).get("data"),
        "technical_values": evaluation.get("technical_confirmation"),
        "valuation_models": sorted(models, key=lambda item: str(item.get("methodology_id") or "")),
        "fair_value": professional.get("atlas_base_fair_value"),
        "pillars": {key: evaluation.get(key) for key in (
            "technical_quality", "fundamental_quality", "valuation_quality",
            "risk_quality", "entry_quality", "volume_quality",
        )},
        "opportunity": evaluation.get("opportunity"),
        "confidence": evaluation.get("decision_confidence"),
        "buy_now_membership": record.get("canonical_action") == "BUY_NOW",
    }


def _order_only_difference_count(first: Mapping[str, Any], second: Mapping[str, Any]) -> int:
    count = 0
    left = {item.get("ticker"): item for item in first.get("evaluations") or ()}
    right = {item.get("ticker"): item for item in second.get("evaluations") or ()}
    for ticker in sorted(set(left) & set(right)):
        left_models = (((left[ticker].get("evaluation") or {}).get("atlas_valuation") or {})
                       .get("professional_valuation_v2", {}).get("models") or ())
        right_models = (((right[ticker].get("evaluation") or {}).get("atlas_valuation") or {})
                        .get("professional_valuation_v2", {}).get("models") or ())
        for left_model, right_model in zip(left_models, right_models):
            left_peer = (left_model.get("key_assumptions") or {}).get("peer_evidence") or {}
            right_peer = (right_model.get("key_assumptions") or {}).get("peer_evidence") or {}
            for key in ("included_peers", "excluded_peers", "final_peer_set"):
                a, b = list(left_peer.get(key) or ()), list(right_peer.get(key) or ())
                if a != b and sorted((_canonical_json(item) for item in a)) == sorted((_canonical_json(item) for item in b)):
                    count += 1
    return count


def compare_replay_candidates(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    left = {item.get("ticker"): item for item in first.get("evaluations") or ()}
    right = {item.get("ticker"): item for item in second.get("evaluations") or ()}
    symbols = sorted(set(left) | set(right))
    analytical = [symbol for symbol in symbols if (
        symbol not in left or symbol not in right
        or _analytical_projection(left[symbol]) != _analytical_projection(right[symbol])
    )]
    return {
        "records_compared": len(symbols),
        "analytical_mismatch_count": len(analytical),
        "analytical_mismatch_tickers": analytical,
        "order_only_mismatch_count": _order_only_difference_count(first, second),
        "classifications": {
            "NUMERICAL_DIFFERENCE": 0 if not analytical else len(analytical),
            "ACTION_DIFFERENCE": sum(
                left.get(symbol, {}).get("canonical_action") != right.get(symbol, {}).get("canonical_action")
                for symbol in symbols
            ),
            "PEER_SET_DIFFERENCE": 0 if not analytical else len(analytical),
            "ORDER_ONLY_DIFFERENCE": _order_only_difference_count(first, second),
            "TIMESTAMP_DIFFERENCE": 0,
            "PROVENANCE_ORDER_DIFFERENCE": 0,
            "OTHER": 0,
        },
    }


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


def _augment_accounting_lineage(row: dict[str, Any], statement: Mapping[str, Any]) -> None:
    reports = [item for item in (statement.get("payload") or {}).get("reports") or ()
               if item.get("fiscal_period") == "FY"]
    report = max(reports, key=lambda item: str(item.get("fiscal_date") or ""), default={})
    facts = report.get("canonical_facts") or {}
    evidence_id = (statement.get("provenance") or {}).get("raw_evidence_id")
    currency = report.get("currency")
    lineage = dict(row.get("professional_evidence_lineage") or {})
    fields = dict(lineage.get("fields") or {})
    for field, fact_name, unit in (
        ("total_debt", "total_debt", currency),
        ("cash_and_equivalents", "cash", currency),
        ("diluted_shares", "weighted_average_shares_diluted", "SHARES"),
    ):
        fact = facts.get(fact_name) or {}
        fields[field] = {
            "evidence_id": evidence_id, "provider": "FINNHUB", "unit": unit,
            "currency": None if unit == "SHARES" else currency,
            "period": fact.get("period_end"),
            "source_record_version": fact.get("source_record_version"),
            "normalization": fact.get("scale_transformation"),
        }
    lineage["fields"] = fields
    row["professional_evidence_lineage"] = lineage


def acquire_shard(
    *, adapter: FinnhubCanonicalAdapter, shard: Mapping[str, Any],
    identity: Mapping[str, Any], catalog: Mapping[str, Mapping[str, Any]],
    estimate_adapter: FinnhubShadowAdapter | None = None,
    pace_seconds: float = 1.05,
    rate_governor: FinnhubRateGovernor | None = None,
    checkpoint_dir: Path | None = None,
    strict_provider_health: bool = False,
) -> dict[str, Any]:
    """Acquire each authorized family once for every symbol in a shard."""
    started = time.monotonic()
    started_epoch = time.time()
    rows, failures, calls, cache_hits, retry_count = [], [], 0, 0, 0
    rate_limit_events, provider_errors = 0, 0
    http_4xx_count, http_5xx_count, timeout_count = 0, 0, 0
    request_attempts: dict[tuple[str, str], int] = {}
    request_start_epoch_seconds: list[float] = []
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
            if capability in CERTIFIED_FORWARD_ACQUISITION_FAMILIES:
                params = {"freq": "annual"}
            transport = (estimate_adapter or adapter) if capability in CERTIFIED_FORWARD_ACQUISITION_FAMILIES else adapter
            for attempt in range(MAX_TRANSIENT_RETRIES + 1):
                if rate_governor is not None:
                    rate_governor.before_request()
                request_start_epoch_seconds.append(time.time())
                record = _fetch(transport, capability, symbol, 0.0 if rate_governor else pace_seconds, **params)
                calls += 1
                request_attempts[key] = request_attempts.get(key, 0) + 1
                reason = str((record.get("payload") or {}).get("reason") or "").upper()
                if reason == "HTTP_429":
                    rate_limit_events += 1
                if reason.startswith("HTTP_4"):
                    http_4xx_count += 1
                if reason.startswith("HTTP_5"):
                    http_5xx_count += 1
                if "TIMEOUT" in reason:
                    timeout_count += 1
                if reason.startswith("HTTP_") or reason.startswith("PROVIDER_ERROR:"):
                    provider_errors += 1
                classification = classify_provider_failure(reason)
                if classification == "NONE":
                    break
                if classification != "TRANSIENT":
                    if strict_provider_health:
                        raise RuntimeError(f"STRICT_PROVIDER_HEALTH_STOP:{symbol}:{capability}:{reason}")
                    break
                if attempt == MAX_TRANSIENT_RETRIES:
                    if strict_provider_health:
                        raise RuntimeError(
                            f"STRICT_PROVIDER_HEALTH_STOP:{symbol}:{capability}:{reason}:RETRY_BUDGET_EXHAUSTED"
                        )
                    break
                retry_count += 1
                delay = transient_retry_delay(symbol, capability, attempt)
                if rate_governor is not None:
                    rate_governor.retry_delay(delay)
                else:
                    time.sleep(delay)
            cache[key] = record
            records[capability] = record
        core_records = {name: records[name] for name in CORE_ACQUISITION_FAMILIES}
        row, bars, blockers = _normalized_row(symbol, _classification(catalog, symbol), core_records)
        forward_bridges: dict[str, Any] = {}
        if row is not None:
            _augment_accounting_lineage(row, records["financial_statements"])
            estimates = {name: (records[name].get("payload") or {})
                         for name in CERTIFIED_FORWARD_ACQUISITION_FAMILIES}
            estimate_ids = {name: (records[name].get("provenance") or {}).get("raw_evidence_id")
                            for name in CERTIFIED_FORWARD_ACQUISITION_FAMILIES}
            row, forward_bridges = apply_forward_inputs(
                row, profile=records["company_profile"].get("payload") or {},
                estimates=estimates, snapshot_timestamp=str(identity["evidence_snapshot_at"]),
                evidence_ids=estimate_ids,
            )
        entitlement = sum(
            (record.get("provenance") or {}).get("certification_status") == "ENTITLEMENT_UNAVAILABLE"
            for record in records.values()
        )
        item = {
            "ticker": symbol, "row": row, "bars": serialize_bars(bars),
            "blockers": blockers, "credential_entitlement_failures": entitlement,
            "shadow_evidence_leakage": any(
                (record.get("provenance") or {}).get("certification_status") in {"UNVERIFIED_SHADOW", "SHADOW_ONLY"}
                for name, record in records.items() if name in CORE_ACQUISITION_FAMILIES
            ),
            "authority_violations": sum(
                str((record.get("provenance") or {}).get("provider") or "").upper() not in {"", "FINNHUB"}
                for record in records.values()
            ),
            "evidence_ids": sorted(filter(None, (
                (record.get("provenance") or {}).get("raw_evidence_id") for record in records.values()
            ))),
            "forward_estimate_bridges": forward_bridges,
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
            "fresh_provider_calls": len(request_attempts),
            "retry_provider_calls": retry_count,
            "calls_avoided": cache_hits, "retry_count": retry_count,
            "http_429_count": rate_limit_events, "provider_error_count": provider_errors,
            "http_4xx_count": http_4xx_count, "http_5xx_count": http_5xx_count,
            "timeout_count": timeout_count,
            "duplicate_or_reacquired_requests": max(
                0, sum(max(0, count - 1) for count in request_attempts.values()) - retry_count,
            ),
            "rate_limit_wait_seconds": round(rate_governor.wait_seconds, 3) if rate_governor else 0.0,
            "peak_requests_per_second": rate_governor.peak_requests_per_second if rate_governor else None,
            "request_start_epoch_seconds": request_start_epoch_seconds,
            "acquisition_started_epoch_seconds": started_epoch,
            "acquisition_finished_epoch_seconds": time.time(),
            "rate_contract": rate_governor.contract.as_dict() if rate_governor else None,
            "elapsed_seconds": round(elapsed, 3),
            "symbols_per_minute": round(len(rows) * 60 / elapsed, 3),
        },
        "failure_summary": failures,
    }
    return {**payload, "shard_digest": _digest(payload)}


def validate_shards(*, universe: Mapping[str, Any], identity: Mapping[str, Any],
                    shards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    expected = set(universe.get("supported_symbols") or ())
    expected_shard_ids = {
        item["shard_id"] for item in deterministic_shards(sorted(expected), shard_size=SHARD_SIZE)
    }
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
    if seen_shards != expected_shard_ids:
        raise ValueError("expected shard inventory is incomplete or unexpected")
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


def _method_distribution(terminal: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    combinations: Counter[str] = Counter()
    aliases = {"VAL_P_FCF_V1": "P/FCF", "VAL_FORWARD_PE_V1": "P/E", "VAL_EV_EBITDA_V1": "EV/EBITDA"}
    for item in terminal:
        professional = (((item.get("evaluation") or {}).get("atlas_valuation") or {})
                        .get("professional_valuation_v2") or {})
        methods = sorted(str(model.get("methodology_id")) for model in professional.get("models") or ()
                         if model.get("status") == "PUBLISHED")
        bucket = "4+" if len(methods) >= 4 else str(len(methods))
        counts[bucket] += 1
        label = " + ".join(aliases.get(method, method) for method in methods) if methods else "NONE"
        combinations[label] += 1
    return {
        "certified_method_count": {key: counts[key] for key in ("0", "1", "2", "3", "4+")},
        "published_combinations": dict(sorted(combinations.items())),
    }


def _gate_diagnostics(terminal: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    gates: Counter[str] = Counter()
    one, multiple, near = [], [], []
    for item in terminal:
        evaluation = item.get("evaluation") or {}
        action = item.get("canonical_action")
        if action == "BUY_NOW":
            continue
        reasons = list(dict.fromkeys((evaluation.get("guidance") or {}).get("reason_codes") or item.get("reason_codes") or ()))
        gates.update(str(reason) for reason in reasons)
        row = {
            "ticker": item.get("ticker"), "action": action,
            "blockers": reasons, "opportunity": evaluation.get("opportunity"),
            "confidence": evaluation.get("decision_confidence"),
            "certified_method_count": sum(
                model.get("status") == "PUBLISHED" for model in
                ((((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}).get("models")) or ())
            ),
        }
        if len(reasons) == 1: one.append(row)
        elif len(reasons) >= 2: multiple.append(row)
        near.append(row)
    near.sort(key=lambda row: (-(float(row["opportunity"] or -1)), len(row["blockers"]), str(row["ticker"])))
    return {
        "gate_frequency": dict(gates.most_common()),
        "failing_exactly_one_count": len(one), "failing_two_or_more_count": len(multiple),
        "failing_exactly_one": one, "top_50_closest_to_buy_now": near[:50],
    }


def _publication_diagnostics(terminal: Sequence[Mapping[str, Any]], artifacts: Mapping[str, Any] | None) -> dict[str, Any]:
    certified = {str(row.get("ticker")): row for row in (artifacts or {}).get("full_evaluation_pool.json") or ()}
    inventory, withheld = [], []
    for item in terminal:
        if item.get("canonical_action") != "BUY_NOW":
            continue
        evaluation = item.get("evaluation") or {}
        professional = ((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
        publication = (certified.get(str(item.get("ticker"))) or {}).get("publication_certification") or {}
        allowed = publication.get("customer_publication_allowed") is True
        models = [str(model.get("methodology_id")) for model in professional.get("models") or ()
                  if model.get("status") == "PUBLISHED"]
        range_fields = {name: None for name in (
            "buy_range_lower", "preferred_entry", "valuation_ceiling", "technical_ceiling",
            "risk_reward_ceiling", "max_buy_price", "binding_ceiling", "upside_at_max_buy_price",
        )}
        range_fields.update({"fair_value": professional.get("atlas_base_fair_value"),
                             "upside_at_current_price": None, "stop_or_invalidation": None})
        price = (evaluation.get("market_snapshot") or {}).get("price")
        fair = professional.get("atlas_base_fair_value")
        if allowed:
            trade = evaluation.get("trade_plan") or {}
            range_fields["buy_range_lower"] = trade.get("entry_low")
            range_fields["stop_or_invalidation"] = trade.get("stop_loss")
            if isinstance(price, (int, float)) and isinstance(fair, (int, float)) and price:
                range_fields["upside_at_current_price"] = fair / price - 1
        range_ready = allowed and all(range_fields[name] is not None for name in (
            "valuation_ceiling", "technical_ceiling", "risk_reward_ceiling"))
        row = {
            "ticker": item.get("ticker"), "current_snapshot_price": price,
            "fair_value": fair, "opportunity": evaluation.get("opportunity"),
            "confidence": evaluation.get("decision_confidence"),
            "six_pillars": {name: evaluation.get(name) for name in (
                "technical_quality", "fundamental_quality", "valuation_quality",
                "risk_quality", "entry_quality", "volume_quality")},
            "certified_methods": models, "certified_method_count": len(models),
            "valuation_dispersion": professional.get("dispersion"),
            "accounting_state": (evaluation.get("valuation_validation") or {}).get("checks"),
            "technical_state": (evaluation.get("technical_confirmation") or {}).get("status"),
            "risk_state": (evaluation.get("risk") or {}).get("status"),
            "publication_state": publication.get("certification_state"),
            "publication_allowed": allowed,
            "publication_blockers": list(publication.get("blockers") or ()),
            "buy_range_readiness": "BUY_RANGE_READY" if range_ready else "GOVERNED_CEILINGS_INCOMPLETE",
            **range_fields,
            "prospective_signal_schema_ready": False,
            "executable_paper_entry_ready": bool(range_ready),
        }
        (inventory if allowed else withheld).append(row)
    return {"publishable_buy_now": inventory, "withheld_buy_now": withheld}


def _pillar_distribution(terminal: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    keys = ("technical_quality", "fundamental_quality", "valuation_quality", "risk_quality", "entry_quality", "volume_quality")
    result = {}
    for key in keys:
        values = []
        for item in terminal:
            pillar = (item.get("evaluation") or {}).get(key)
            # Canonical decision metrics expose pillars as governed structured
            # records. This report counts the score without flattening or
            # mutating the underlying evaluation.
            values.append(pillar.get("score") if isinstance(pillar, Mapping) else pillar)
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
        identity_checks = {key: value for key, value in checks.items() if key not in {
            "exact_snapshot_revalidation", "matching_decision_digest",
        }}
        revalidated = checks["exact_snapshot_revalidation"] and checks["matching_decision_digest"]
        blockers = list(revalidation.get("blockers") or ())
        provenance_valid = all(identity_checks.values()) and (revalidated or bool(blockers))
        records.append({
            "ticker": item.get("ticker"), "checks": checks,
            "publication_eligible": all(checks.values()),
            "provenance_valid": provenance_valid,
            "revalidation_result": "BUY_NOW_REVALIDATED" if revalidated else "BUY_NOW_WITHHELD",
            "evaluation_digest": item.get("evaluation_digest"),
            "universe_sha256": universe.get("source_sha256"),
            "blockers": blockers,
        })
    return {
        # Zero publishable BUY_NOW is valid. Every canonical BUY must instead
        # be exact-snapshot revalidated or explicitly withheld with blockers.
        "status": "PASS" if all(item["provenance_valid"] for item in records) else "FAIL",
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


def combine_evaluation_results(results: Sequence[Mapping[str, Any]], *, reverse: bool = False) -> dict[str, Any]:
    """Combine independently evaluated chunks without changing analytical values."""
    terminal = sorted(
        (dict(record) for result in results for record in result.get("terminal_records") or ()),
        key=lambda record: str(record.get("ticker")), reverse=reverse,
    )
    evaluations = [record["evaluation"] for record in terminal if isinstance(record.get("evaluation"), Mapping)]
    failures = sorted({
        str(symbol) for result in results
        for symbol in (result.get("inspector") or {}).get("failures") or ()
    })
    return {
        "terminal_records": terminal,
        "evaluation_count": len(evaluations),
        "inspector": {"expected_parameter_count": 91, "failures": failures,
                      "status": "PASS" if not failures else "FAIL"},
        "forward_route_leakage": any(bool(result.get("forward_route_leakage")) for result in results),
        "forward_route_activation": any(bool(result.get("forward_route_activation")) for result in results),
        "shadow_evidence_leakage": any(bool(result.get("shadow_evidence_leakage")) for result in results),
        "authority_violations": sum(int(result.get("authority_violations") or 0) for result in results),
        "valuation_route_distribution": _route_distribution(evaluations),
    }


def evaluate_records(*, identity: Mapping[str, Any], acquired: Sequence[Mapping[str, Any]],
                     checkpoint_dir: Path | None = None,
                     peer_evidence_prepared: bool = False) -> dict[str, Any]:
    """Build peer evidence once, then evaluate only target rows from that scope."""
    evaluated_at = datetime.fromisoformat(str(identity["evidence_snapshot_at"]).replace("Z", "+00:00"))
    source_rows = [dict(item["row"]) for item in acquired if item.get("row") is not None]
    prepared = source_rows if peer_evidence_prepared else apply_peer_multiple_evidence(source_rows)
    prepared_by_symbol = {str(row.get("ticker")): row for row in prepared}
    acquired_by_symbol = {str(item.get("ticker")): item for item in acquired}
    terminal, evaluations, inspector_failures = [], [], []
    forward_route_activation = False
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
                    forward_route_activation |= any(
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
            forward_route_activation |= any(states.get(key) == "PUBLISHED" for key in FORWARD_ROUTE_IDS)
            action = str((evaluation.get("guidance") or {}).get("state") or "RATING_NOT_PUBLISHED")
            action = ACTION_ALIASES.get(action, action)
            bridged = bridge_evaluation({
                "ticker": symbol, "terminal_data_state": "CERTIFIED_EVALUATION",
                "canonical_action": action, "evaluation": evaluation,
                "evaluation_digest": evaluation.get("decision_digest"),
            }, row)
            evaluation = dict(bridged["canonical_investment_evaluation"])
            revalidation = dict(evaluation.get("positive_action_revalidation") or {})
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
        "forward_route_leakage": False,
        "forward_route_activation": forward_route_activation,
        "shadow_evidence_leakage": shadow_evidence_leakage,
        "authority_violations": authority_violations,
        "valuation_route_distribution": _route_distribution(evaluations),
    }


def build_candidate_determinism_checkpoint(*, universe: Mapping[str, Any], identity: Mapping[str, Any],
                                           first: Mapping[str, Any], completeness: Mapping[str, Any],
                                           second: Mapping[str, Any],
                                           second_completeness: Mapping[str, Any]) -> dict[str, Any]:
    """Build the unchanged immutable candidates once for resumable aggregation."""
    if completeness.get("state") != "FULL_UNIVERSE_CERTIFIED":
        raise ValueError("canonical evaluation is not eligible for candidate construction")
    candidate = build_immutable_candidate(
        universe=universe, identity=identity, records=first["terminal_records"],
        completeness=completeness, methodology_version=REGISTRY_VERSION,
        provider_evidence_version=PROVIDER_EVIDENCE_VERSION,
        valuation_version=VALUATION_VERSION, pillar_version=PILLAR_VERSION,
        action_engine_version=ACTION_VERSION,
    )
    second_candidate = build_immutable_candidate(
        universe=universe, identity=identity, records=second["terminal_records"],
        completeness=second_completeness, methodology_version=REGISTRY_VERSION,
        provider_evidence_version=PROVIDER_EVIDENCE_VERSION,
        valuation_version=VALUATION_VERSION, pillar_version=PILLAR_VERSION,
        action_engine_version=ACTION_VERSION,
    )
    determinism = compare_deterministic_candidates(candidate, second_candidate)
    determinism["structural_diff"] = compare_replay_candidates(candidate, second_candidate)
    return {
        "run_identity_sha256": identity["run_identity_sha256"],
        "candidate": candidate,
        "second_candidate": second_candidate,
        "determinism": determinism,
    }


def build_single_immutable_candidate(*, universe: Mapping[str, Any], identity: Mapping[str, Any],
                                     evaluation: Mapping[str, Any],
                                     completeness: Mapping[str, Any]) -> dict[str, Any]:
    """Build one order-specific candidate without changing candidate semantics."""
    if completeness.get("state") != "FULL_UNIVERSE_CERTIFIED":
        raise ValueError("canonical evaluation is not eligible for candidate construction")
    return build_immutable_candidate(
        universe=universe, identity=identity, records=evaluation["terminal_records"],
        completeness=completeness, methodology_version=REGISTRY_VERSION,
        provider_evidence_version=PROVIDER_EVIDENCE_VERSION,
        valuation_version=VALUATION_VERSION, pillar_version=PILLAR_VERSION,
        action_engine_version=ACTION_VERSION,
    )


def aggregate_complete_run(*, universe: Mapping[str, Any], identity: Mapping[str, Any],
                           shard_payloads: Sequence[Mapping[str, Any]],
                           candidate_eligible: bool = True,
                           checkpoint_dir: Path | None = None,
                           evaluation_checkpoint: Mapping[str, Any] | None = None,
                           candidate_checkpoint: Mapping[str, Any] | None = None) -> dict[str, Any]:
    phase_metrics: list[dict[str, Any]] = []

    def profiled(phase: str, operation: Any) -> Any:
        started = time.monotonic()
        cpu_started = time.process_time()
        value = operation()
        phase_metrics.append({
            "phase": phase,
            "duration_seconds": round(time.monotonic() - started, 6),
            "cpu_seconds": round(time.process_time() - cpu_started, 6),
            "max_rss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
                              if sys.platform == "darwin"
                              else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        })
        return value

    acquired = profiled(
        "A_SHARD_INVENTORY_VALIDATION_AND_MERGE",
        lambda: validate_shards(universe=universe, identity=identity, shards=shard_payloads),
    )
    if evaluation_checkpoint is None:
        first = profiled(
            "B_CANONICAL_EVALUATION_FORWARD",
            lambda: evaluate_records(identity=identity, acquired=acquired, checkpoint_dir=checkpoint_dir),
        )
        completeness = profiled(
            "C_COMPLETENESS_ACCOUNTING",
            lambda: certify_complete_run(
                universe=universe, records=first["terminal_records"],
                acquisition_complete=True, decision_processing_complete=True,
            ),
        )
        second = None
        second_completeness = None
    else:
        if evaluation_checkpoint.get("run_identity_sha256") != identity["run_identity_sha256"]:
            raise ValueError("canonical evaluation checkpoint belongs to a different immutable run")
        first = dict(evaluation_checkpoint["first_evaluation"])
        completeness = dict(evaluation_checkpoint["first_completeness"])
        second = dict(evaluation_checkpoint["second_evaluation"])
        second_completeness = dict(evaluation_checkpoint["second_completeness"])
    candidate = None
    determinism = {"status": "NOT_ELIGIBLE_INCOMPLETE_RUN"}
    second_candidate = None
    if candidate_eligible and completeness["state"] == "FULL_UNIVERSE_CERTIFIED":
        if candidate_checkpoint is not None:
            if candidate_checkpoint.get("run_identity_sha256") != identity["run_identity_sha256"]:
                raise ValueError("candidate checkpoint belongs to a different immutable run")
            candidate = dict(candidate_checkpoint["candidate"])
            second_candidate = dict(candidate_checkpoint["second_candidate"])
            determinism = dict(candidate_checkpoint["determinism"])
        else:
            if second is None:
                second = profiled(
                    "D_CANONICAL_EVALUATION_REVERSE_REPLAY",
                    lambda: evaluate_records(identity=identity, acquired=list(reversed(acquired))),
                )
                second_completeness = profiled(
                    "E_REPLAY_COMPLETENESS_ACCOUNTING",
                    lambda: certify_complete_run(
                        universe=universe, records=second["terminal_records"],
                        acquisition_complete=True, decision_processing_complete=True,
                    ),
                )
            candidate_state = profiled(
                "F_CANDIDATE_CONSTRUCTION_AND_DETERMINISM",
                lambda: build_candidate_determinism_checkpoint(
                    universe=universe, identity=identity, first=first, completeness=completeness,
                    second=second, second_completeness=second_completeness,
                ),
            )
            candidate = candidate_state["candidate"]
            second_candidate = candidate_state["second_candidate"]
            determinism = candidate_state["determinism"]
    elif not candidate_eligible and completeness["state"] == "FULL_UNIVERSE_CERTIFIED":
        second = profiled(
            "D_CANARY_DETERMINISTIC_REVERSE_REPLAY",
            lambda: evaluate_records(identity=identity, acquired=list(reversed(acquired))),
        )
        first_records = sorted(first["terminal_records"], key=lambda item: str(item.get("ticker")))
        second_records = sorted(second["terminal_records"], key=lambda item: str(item.get("ticker")))
        first_digest, second_digest = _digest(first_records), _digest(second_records)
        determinism = {
            "status": "PASS" if first_digest == second_digest else "FAIL",
            "first_terminal_records_digest": first_digest,
            "second_terminal_records_digest": second_digest,
            "record_count": len(first_records),
        }
    calls = sum(int((payload.get("provider_telemetry") or {}).get("provider_calls") or 0) for payload in shard_payloads)
    cache_hits = sum(int((payload.get("provider_telemetry") or {}).get("cache_hits") or 0) for payload in shard_payloads)
    retries = sum(int((payload.get("provider_telemetry") or {}).get("retry_count") or 0) for payload in shard_payloads)
    rate_limits = sum(int((payload.get("provider_telemetry") or {}).get("http_429_count") or 0) for payload in shard_payloads)
    provider_errors = sum(int((payload.get("provider_telemetry") or {}).get("provider_error_count") or 0) for payload in shard_payloads)
    http_4xx = sum(int((payload.get("provider_telemetry") or {}).get("http_4xx_count") or 0) for payload in shard_payloads)
    http_5xx = sum(int((payload.get("provider_telemetry") or {}).get("http_5xx_count") or 0) for payload in shard_payloads)
    timeouts = sum(int((payload.get("provider_telemetry") or {}).get("timeout_count") or 0) for payload in shard_payloads)
    duplicates = sum(int((payload.get("provider_telemetry") or {}).get("duplicate_or_reacquired_requests") or 0) for payload in shard_payloads)
    peak_rps = max((int((payload.get("provider_telemetry") or {}).get("peak_requests_per_second") or 0) for payload in shard_payloads), default=0)
    request_starts = sorted(
        float(value)
        for payload in shard_payloads
        for value in ((payload.get("provider_telemetry") or {}).get("request_start_epoch_seconds") or [])
    )
    acquisition_starts = [
        float(value) for payload in shard_payloads
        if (value := (payload.get("provider_telemetry") or {}).get("acquisition_started_epoch_seconds")) is not None
    ]
    acquisition_finishes = [
        float(value) for payload in shard_payloads
        if (value := (payload.get("provider_telemetry") or {}).get("acquisition_finished_epoch_seconds")) is not None
    ]

    def peak_rolling(window_seconds: float) -> int:
        peak = left = 0
        for right, timestamp in enumerate(request_starts):
            while timestamp - request_starts[left] >= window_seconds:
                left += 1
            peak = max(peak, right - left + 1)
        return peak

    acquisition_wall = (
        max(acquisition_finishes) - min(acquisition_starts)
        if acquisition_starts and acquisition_finishes else 0.0
    )
    configured_workers = max((
        int(((payload.get("provider_telemetry") or {}).get("rate_contract") or {}).get("parallel_workers") or 1)
        for payload in shard_payloads
    ), default=1)
    elapsed = sum(float((payload.get("provider_telemetry") or {}).get("elapsed_seconds") or 0) for payload in shard_payloads)
    canary_coverage = _canary_coverage(acquired) if not candidate_eligible else None
    canary_coverage_pass = canary_coverage is None or canary_coverage["status"] == "PASS"
    buy_now_provenance = _buy_now_report(first["terminal_records"], universe, identity)
    publication_bundle = None
    publication_bundle_digest = None
    if candidate is not None:
        source_rows = {str(item.get("ticker")): dict(item.get("row") or {}) for item in acquired}
        artifacts, manifest = profiled(
            "G_PUBLICATION_CANDIDATE_GENERATION",
            lambda: build_publication_bundle(
                candidate=candidate, source_rows=source_rows,
                generated_at=str(identity["evidence_snapshot_at"]),
            ),
        )
        publication_bundle = {"artifacts": artifacts, "manifest": manifest}
        publication_bundle_digest = _digest({
            "artifact_hashes": manifest.get("artifact_hashes"),
            "candidate_digest": candidate.get("candidate_digest"),
        })
    method_distribution = _method_distribution(first["terminal_records"])
    gate_diagnostics = _gate_diagnostics(first["terminal_records"])
    publication_diagnostics = _publication_diagnostics(
        first["terminal_records"], (publication_bundle or {}).get("artifacts"),
    )
    new_candidate_certified = bool(
        candidate and determinism.get("status") == "PASS"
        and buy_now_provenance["status"] == "PASS"
        and first["inspector"]["status"] == "PASS"
        and publication_bundle_digest
    )
    return {
        "executor_version": VERSION, "run_identity": dict(identity),
        "full_universe_completeness": completeness,
        "evidence_inspector_coverage": first["inspector"],
        "forward_route_leakage": first["forward_route_leakage"],
        "forward_route_activation": first["forward_route_activation"],
        "shadow_evidence_leakage": first["shadow_evidence_leakage"],
        "authority_violations": first["authority_violations"],
        "valuation_route_distribution": first["valuation_route_distribution"],
        "valuation_method_distribution": method_distribution,
        "gate_diagnostics": gate_diagnostics,
        "pillar_distribution": _pillar_distribution(first["terminal_records"]),
        "action_distribution": completeness.get("action_counts") or {},
        "provider_call_telemetry": {
            "provider_calls": calls, "cache_hits": cache_hits, "calls_avoided": cache_hits,
            "retry_count": retries, "retry_rate": round(retries / calls, 6) if calls else 0.0,
            "http_429_count": rate_limits, "provider_error_count": provider_errors,
            "http_4xx_count": http_4xx, "http_5xx_count": http_5xx,
            "timeout_count": timeouts, "duplicate_or_reacquired_requests": duplicates,
            "peak_requests_per_second": peak_rps,
            "global_peak_rolling_requests_per_second": peak_rolling(1.0),
            "global_peak_rolling_requests_per_minute": peak_rolling(60.0),
            "provider_acquisition_wall_seconds": round(acquisition_wall, 3),
            "effective_sustained_requests_per_minute": round(calls * 60 / acquisition_wall, 3) if acquisition_wall else 0.0,
            "worker_utilization": round(elapsed / (acquisition_wall * configured_workers), 6) if acquisition_wall else 0.0,
            "summed_shard_elapsed_seconds": round(elapsed, 3),
            "symbols_per_minute_serial_equivalent": round(len(acquired) * 60 / elapsed, 3) if elapsed else 0.0,
        },
        "buy_now_provenance": buy_now_provenance,
        "canary_coverage": canary_coverage,
        "immutable_candidate": candidate, "determinism": determinism,
        "publication_bundle": publication_bundle,
        "publication_bundle_digest": publication_bundle_digest,
        "publication_diagnostics": publication_diagnostics,
        "new_full_universe_candidate_certified": new_candidate_certified,
        "release_smoke_ready": new_candidate_certified,
        "aggregation_phase_metrics": phase_metrics,
        "determinism_candidates": {"first": candidate, "second": second_candidate},
        "state": (
            "FINNHUB_FULL_UNIVERSE_EXECUTOR_CERTIFIED"
            if candidate and determinism.get("status") == "PASS"
            and buy_now_provenance["status"] == "PASS" and first["inspector"]["status"] == "PASS"
            and completeness.get("credential_entitlement_failures") == 0
            and not completeness.get("atlas_integration_failures")
            and not first["shadow_evidence_leakage"] and first["authority_violations"] == 0
            else "CANARY_PASS"
            if not candidate_eligible and completeness["state"] == "FULL_UNIVERSE_CERTIFIED"
            and determinism.get("status") == "PASS"
            and rate_limits == 0 and provider_errors == 0 and timeouts == 0
            and first["inspector"]["status"] == "PASS"
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
    "PROVIDER_EVIDENCE_VERSION", "SHARD_CHECKPOINT_CONTRACT_VERSION", "SHARD_SIZE",
    "TRANSIENT_RETRY_POLICY_VERSION", "VERSION", "acquire_shard",
    "aggregate_complete_run", "build_candidate_determinism_checkpoint", "build_single_immutable_candidate",
    "build_certified_shard_checkpoint", "build_run_identity", "classify_provider_failure", "deserialize_bars",
    "deterministic_canary", "deterministic_shards", "evaluate_records",
    "serialize_bars", "shard_checkpoint_contract", "transient_retry_delay",
    "validate_certified_shard_checkpoint", "validate_executor_checkpoint", "validate_shards",
]
