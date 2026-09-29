"""Fail-closed contracts for an immutable ATLAS full-universe decision run.

This module is deliberately provider- and methodology-neutral.  It does not
grant provider authority and it does not calculate scores or valuations.  It
governs the boundary around the existing engines: frozen universe identity,
one terminal record per supported symbol, resumable acquisition identity,
complete-run publication eligibility, and deterministic package digests.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


VERSION = "ATLAS_FULL_UNIVERSE_BRAIN_CERTIFICATION_V1"
SUPPORTED_SECURITY_STATES = ("SUPPORTED_COMMON_EQUITY", "SUPPORTED_ADR_IF_ALREADY_GOVERNED")
UNSUPPORTED_SECURITY_STATES = (
    "ETF", "PREFERRED", "WARRANT", "UNIT", "OTC", "FUND", "SPAC/SHELL",
    "DUPLICATE_SHARE_CLASS", "UNRESOLVED_SECURITY_TYPE", "OTHER_UNSUPPORTED",
)
TERMINAL_DATA_STATES = (
    "CERTIFIED_EVALUATION", "PARTIAL_EVIDENCE", "PROVIDER_DATA_UNAVAILABLE",
    "VALUATION_INPUT_INCOMPLETE", "TECHNICAL_INPUT_INCOMPLETE",
    "CLASSIFICATION_UNRESOLVED", "RATING_NOT_PUBLISHED", "ATLAS_INTEGRATION_FAILURE",
)
VALUATION_ROUTE_STATES = (
    "CERTIFIED", "NOT_APPLICABLE", "EVIDENCE_INSUFFICIENT",
    "COMPARABLE_PEERS_INSUFFICIENT", "CONTRACT_PENDING",
)
VALUATION_METHODS = ("FCFF_DCF", "FORWARD_PE", "EV_EBITDA", "P_FCF", "DDM")
CANONICAL_ACTIONS = (
    "BUY_NOW", "BUILD_A_POSITION", "WAIT_FOR_BETTER_ENTRY", "WAIT_FOR_CONFIRMATION",
    "WATCH_NOT_READY", "AVOID", "RATING_NOT_PUBLISHED",
)
PILLAR_WEIGHTS = {
    "technical_quality": 0.25, "fundamental_quality": 0.20,
    "atlas_valuation": 0.20, "risk_quality": 0.15,
    "entry_trade_plan": 0.10, "volume_quality": 0.10,
}
REPORT_CARD_PROSPECTIVE_ACTIVE = False


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _reason_class(reason: str) -> str:
    value = str(reason or "").upper()
    if "OTC" in value:
        return "OTC"
    if "WARRANT" in value:
        return "WARRANT"
    if "PREFERRED" in value:
        return "PREFERRED"
    if "UNIT" in value:
        return "UNIT"
    if "FUND" in value or "ETF" in value:
        return "FUND"
    if "SPAC" in value or "SHELL" in value:
        return "SPAC/SHELL"
    if "DUPLICATE" in value or "SHARE_CLASS" in value:
        return "DUPLICATE_SHARE_CLASS"
    if "UNRESOLVED" in value or "INVALID_SYMBOL_IDENTITY" in value:
        return "UNRESOLVED_SECURITY_TYPE"
    return "OTHER_UNSUPPORTED"


def load_frozen_universe(path: Path) -> dict[str, Any]:
    """Load the existing governed artifact without reacquiring or rerouting it."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    symbols = tuple(_symbol(item) for item in payload.get("symbols") or () if _symbol(item))
    mappings = payload.get("symbol_mappings") or {}
    if len(symbols) != int(payload.get("count") or -1) or len(set(symbols)) != len(symbols):
        raise ValueError("frozen universe count/identity is inconsistent")
    stock_symbols, etf_symbols = [], []
    for symbol in symbols:
        mapping = mappings.get(symbol) if isinstance(mappings, Mapping) else None
        source = str((mapping or {}).get("listing_source_endpoint") or "").lower()
        (etf_symbols if source.startswith("etfs") else stock_symbols).append(symbol)
    summary = payload.get("governed_pre_acquisition_summary") or {}
    if int(summary.get("us_stock_universe_count") or -1) != len(stock_symbols):
        raise ValueError("frozen stock count does not match governed summary")
    if int(summary.get("us_etf_universe_count") or -1) != len(etf_symbols):
        raise ValueError("frozen ETF count does not match governed summary")

    exclusions = payload.get("eligibility", {}).get("exclusions") or ()
    classified = Counter(_reason_class(item.get("reason")) for item in exclusions if isinstance(item, Mapping))
    classified["ETF"] += len(etf_symbols)
    return {
        "contract_version": VERSION,
        "source_artifact": str(path),
        "source_sha256": sha256_file(path),
        "source_generated_at": payload.get("generated_at"),
        "raw_listing_count": int(summary.get("raw_global_master_count") or 0),
        "governed_symbol_count": len(symbols),
        "supported_equity_count": len(stock_symbols),
        "supported_symbols": sorted(stock_symbols),
        "excluded_governed_symbols": sorted(etf_symbols),
        "security_class_counts": {
            "SUPPORTED_COMMON_EQUITY": len(stock_symbols),
            "SUPPORTED_ADR_IF_ALREADY_GOVERNED": 0,
            **{key: int(classified.get(key, 0)) for key in UNSUPPORTED_SECURITY_STATES},
        },
        "historical_exclusion_reason_counts": dict(
            sorted((payload.get("eligibility", {}).get("exclusion_reason_counts") or {}).items())
        ),
        "universe_methodology_version": "GOVERNED_US_STOCK_UNIVERSE_EXISTING_ARTIFACT_V1",
        "identity_note": (
            "Stock/ETF identity is frozen from the existing artifact. The artifact's prior-run "
            "eligible_count is not reused as current-run eligibility."
        ),
    }


def checkpoint_identity(*, universe: Mapping[str, Any], evidence_snapshot_at: str,
                        source_sha: str, provider_authority_version: str) -> dict[str, Any]:
    datetime.fromisoformat(str(evidence_snapshot_at).replace("Z", "+00:00"))
    identity = {
        "contract_version": VERSION,
        "universe_sha256": universe["source_sha256"],
        "supported_equity_count": universe["supported_equity_count"],
        "evidence_snapshot_at": evidence_snapshot_at,
        "source_sha": source_sha,
        "provider_authority_version": provider_authority_version,
    }
    return {**identity, "checkpoint_identity_sha256": hashlib.sha256(_canonical_json(identity)).hexdigest()}


def validate_checkpoint(record: Mapping[str, Any], identity: Mapping[str, Any]) -> None:
    if record.get("checkpoint_identity_sha256") != identity.get("checkpoint_identity_sha256"):
        raise ValueError("checkpoint belongs to a different immutable run")
    symbol = _symbol(record.get("ticker"))
    if not symbol or record.get("terminal_data_state") not in TERMINAL_DATA_STATES:
        raise ValueError("checkpoint is not a terminal per-symbol record")


def _method_states(record: Mapping[str, Any]) -> dict[str, str]:
    supplied = record.get("valuation_routes") if isinstance(record.get("valuation_routes"), Mapping) else {}
    return {method: str(supplied.get(method) or "EVIDENCE_INSUFFICIENT") for method in VALUATION_METHODS}


def normalize_terminal_record(record: Mapping[str, Any]) -> dict[str, Any]:
    state = str(record.get("terminal_data_state") or "")
    if state not in TERMINAL_DATA_STATES:
        raise ValueError(f"invalid terminal data state: {state}")
    routes = _method_states(record)
    if any(value not in VALUATION_ROUTE_STATES for value in routes.values()):
        raise ValueError("invalid valuation route state")
    action = str(record.get("canonical_action") or "RATING_NOT_PUBLISHED")
    if action not in CANONICAL_ACTIONS:
        raise ValueError("invalid canonical action")
    return {
        **dict(record), "ticker": _symbol(record.get("ticker")),
        "terminal_data_state": state, "valuation_routes": routes,
        "canonical_action": action,
    }


def certify_complete_run(*, universe: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
                         acquisition_complete: bool, decision_processing_complete: bool) -> dict[str, Any]:
    expected = tuple(universe.get("supported_symbols") or ())
    normalized = [normalize_terminal_record(item) for item in records]
    symbols = [_symbol(item.get("ticker")) for item in normalized]
    counts = Counter(symbols)
    duplicates = sorted(symbol for symbol, count in counts.items() if count != 1)
    missing = sorted(set(expected) - set(symbols))
    unexpected = sorted(set(symbols) - set(expected))
    entitlement_failures = sum(int(item.get("credential_entitlement_failures") or 0) for item in normalized)
    integration_failures = [
        item["ticker"] for item in normalized if item["terminal_data_state"] == "ATLAS_INTEGRATION_FAILURE"
    ]
    unexplained = [
        item["ticker"] for item in normalized
        if item["terminal_data_state"] == "PROVIDER_DATA_UNAVAILABLE" and not item.get("reason_codes")
    ]
    complete = all((
        acquisition_complete, decision_processing_complete,
        len(normalized) == len(expected), not missing, not unexpected, not duplicates,
        entitlement_failures == 0, not integration_failures, not unexplained,
    ))
    return {
        "state": "FULL_UNIVERSE_CERTIFIED" if complete else "FULL_UNIVERSE_RUN_INCOMPLETE",
        "customer_publishable": bool(complete),
        "expected_supported_symbol_count": len(expected),
        "terminal_record_count": len(normalized),
        "missing_symbols": missing, "unexpected_symbols": unexpected,
        "duplicate_symbols": duplicates,
        "credential_entitlement_failures": entitlement_failures,
        "atlas_integration_failures": sorted(integration_failures),
        "unexplained_provider_absence": sorted(unexplained),
        "terminal_state_counts": dict(sorted(Counter(item["terminal_data_state"] for item in normalized).items())),
        "valuation_route_counts": {
            method: dict(sorted(Counter(item["valuation_routes"][method] for item in normalized).items()))
            for method in VALUATION_METHODS
        },
        "action_counts": dict(sorted(Counter(item["canonical_action"] for item in normalized).items())),
        "buy_now_tickers": sorted(
            item["ticker"] for item in normalized if item["canonical_action"] == "BUY_NOW"
        ) if complete else [],
        "failure_rule": "INCOMPLETE_RUN_CANNOT_PUBLISH_NEW_BUY_NOW",
    }


def build_immutable_candidate(*, universe: Mapping[str, Any], identity: Mapping[str, Any],
                              records: Sequence[Mapping[str, Any]], completeness: Mapping[str, Any],
                              methodology_version: str, provider_evidence_version: str,
                              valuation_version: str, pillar_version: str,
                              action_engine_version: str) -> dict[str, Any]:
    if completeness.get("state") != "FULL_UNIVERSE_CERTIFIED":
        raise ValueError("FULL_UNIVERSE_RUN_INCOMPLETE cannot produce a release candidate")
    ordered = sorted((normalize_terminal_record(item) for item in records), key=lambda item: item["ticker"])
    payload = {
        "package_version": VERSION,
        "universe_version": universe["universe_methodology_version"],
        "universe_sha256": universe["source_sha256"],
        "supported_symbol_count": universe["supported_equity_count"],
        "evidence_snapshot_at": identity["evidence_snapshot_at"],
        "methodology_version": methodology_version,
        "provider_authority_version": identity["provider_authority_version"],
        "provider_evidence_version": provider_evidence_version,
        "valuation_version": valuation_version,
        "six_pillar_version": pillar_version,
        "action_engine_version": action_engine_version,
        "source_sha": identity["source_sha"],
        "evaluations": ordered,
        "buy_now_inventory": list(completeness.get("buy_now_tickers") or ()),
        "report_card_prospective_active": REPORT_CARD_PROSPECTIVE_ACTIVE,
    }
    return {**payload, "candidate_digest": hashlib.sha256(_canonical_json(payload)).hexdigest()}


def compare_deterministic_candidates(first: Mapping[str, Any], second: Mapping[str, Any]) -> dict[str, Any]:
    left, right = first.get("candidate_digest"), second.get("candidate_digest")
    return {"status": "PASS" if left and left == right else "FAIL", "first_digest": left, "second_digest": right}


__all__ = [
    "CANONICAL_ACTIONS", "PILLAR_WEIGHTS", "REPORT_CARD_PROSPECTIVE_ACTIVE",
    "TERMINAL_DATA_STATES", "VALUATION_METHODS", "VALUATION_ROUTE_STATES", "VERSION",
    "build_immutable_candidate", "certify_complete_run", "checkpoint_identity",
    "compare_deterministic_candidates", "load_frozen_universe", "normalize_terminal_record",
    "validate_checkpoint",
]
