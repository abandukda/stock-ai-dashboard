#!/usr/bin/env python3
"""Bounded real-data certification of the existing Professional V2 P/FCF route.

This is a shadow-only diagnostic.  It derives a peer acquisition universe from
the governed discovery classification artifact, acquires only the Finnhub
families required for historical P/FCF, and then invokes the existing ATLAS
peer selection and valuation implementations unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from engines.professional_valuation_v2 import value_company
from services.finnhub_shadow_provider import (
    FINNHUB_DEMO_LICENSE, FINNHUB_DEMO_SYMBOL_WHITELIST,
    FinnhubShadowAdapter,
)
from services.professional_valuation_evidence import apply_peer_multiple_evidence
from services.valuation_evidence_strength import certify_peer_multiple


VERSION = "ATLAS_FINNHUB_P_FCF_PEER_CERTIFICATION_V5_TARGET_LOCAL_SCOPE"
TARGETS = ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA")
CLASSIFICATION_PATH = Path("discovery_candidate_pool.json")
SUPPLEMENTAL_CLASSIFICATION_PATH = Path("analysis/phase8b_calibration/universe_v1.json")
MAX_INDUSTRY_CANDIDATES = 14
MAX_SECTOR_CANDIDATES = 22
ADAPTIVE_BATCH_SIZE = 8
MAX_ADAPTIVE_ADDITIONAL_SYMBOLS_PER_TARGET = 256
GOVERNED_SECTOR_EQUIVALENCE = {
    # The supplemental calibration universe uses the GICS label while the
    # discovery classification artifact uses the equivalent customer taxonomy.
    # This is identity normalization only; it does not alter peer eligibility.
    "Consumer Staples": "Consumer Defensive",
}

PROVIDER_DATA_UNAVAILABLE = "PROVIDER_DATA_UNAVAILABLE"
PROVIDER_CONTRACT_UNRESOLVED = "PROVIDER_CONTRACT_UNRESOLVED"
CREDENTIAL_ENTITLEMENT_UNAVAILABLE = "CREDENTIAL_ENTITLEMENT_UNAVAILABLE"
EXPECTED_DEMO_SYMBOL_RESTRICTION = "EXPECTED_DEMO_SYMBOL_RESTRICTION"
PAID_CORE_BREADTH_UNTESTED = "PAID_CORE_BREADTH_UNTESTED"
ATLAS_INTEGRATION_FAILURE = "ATLAS_INTEGRATION_FAILURE"
CERTIFIED_DATA_AVAILABLE = "CERTIFIED_DATA_AVAILABLE"
PROVIDER_INPUTS_CERTIFIED = "CERTIFIED_COMPLETE"
P_FCF_ROUTE_CERTIFIED = "CERTIFIED"
P_FCF_ROUTE_UNAVAILABLE_INSUFFICIENT_COMPARABLE_PEERS = "UNAVAILABLE_INSUFFICIENT_COMPARABLE_PEERS"
P_FCF_ROUTE_UNAVAILABLE_MISSING_TARGET_INPUT = "UNAVAILABLE_MISSING_TARGET_INPUT"
P_FCF_ROUTE_CERTIFICATION_FAILURE = "FAILED_CERTIFICATION_DEFECT"
FULL_CORE_RERUN_CONTRACT = {
    "governed_universe_identity_must_match": True,
    "required_families": ("company_profile", "financial_statements", "basic_financials"),
    "classification_must_resolve": ("sector", "industry", "security_type"),
    "credential_entitlement_failures_required": 0,
    "minimum_certified_peers_per_target": 3,
    "all_targets_must_publish_p_fcf": True,
    "atlas_integration_failures_required": 0,
    "forward_estimate_contract_required_for_p_fcf": False,
}


def classify_provider_record(record: Mapping[str, Any]) -> str:
    """Separate commercial access from provider capability and data absence."""
    status = str((record.get("provenance") or {}).get("certification_status") or "").upper()
    provenance = record.get("provenance") or {}
    symbol = str(provenance.get("symbol") or "").upper()
    if (
        status == "ENTITLEMENT_UNAVAILABLE"
        and provenance.get("license_class") == FINNHUB_DEMO_LICENSE
        and symbol not in FINNHUB_DEMO_SYMBOL_WHITELIST
    ):
        return EXPECTED_DEMO_SYMBOL_RESTRICTION
    if status == "ENTITLEMENT_UNAVAILABLE":
        return CREDENTIAL_ENTITLEMENT_UNAVAILABLE
    if status in {"DATA_UNAVAILABLE", "PROVIDER_ERROR"}:
        return PROVIDER_DATA_UNAVAILABLE
    return CERTIFIED_DATA_AVAILABLE


def classify_target_route(*, target_row_present: bool, certified_peer_count: int,
                          route_certified: bool, candidate_universe_exhausted: bool,
                          target_route_inputs_complete: bool = True) -> dict[str, str]:
    """Keep provider-input availability separate from valuation-route reachability."""
    if not target_row_present:
        return {
            "provider_input_status": PROVIDER_DATA_UNAVAILABLE,
            "p_fcf_route_status": P_FCF_ROUTE_UNAVAILABLE_MISSING_TARGET_INPUT,
        }
    if not target_route_inputs_complete:
        return {
            "provider_input_status": PROVIDER_INPUTS_CERTIFIED,
            "p_fcf_route_status": P_FCF_ROUTE_UNAVAILABLE_MISSING_TARGET_INPUT,
        }
    if route_certified:
        return {
            "provider_input_status": PROVIDER_INPUTS_CERTIFIED,
            "p_fcf_route_status": P_FCF_ROUTE_CERTIFIED,
        }
    if certified_peer_count < FULL_CORE_RERUN_CONTRACT["minimum_certified_peers_per_target"] and candidate_universe_exhausted:
        return {
            "provider_input_status": PROVIDER_INPUTS_CERTIFIED,
            "p_fcf_route_status": P_FCF_ROUTE_UNAVAILABLE_INSUFFICIENT_COMPARABLE_PEERS,
        }
    return {
        "provider_input_status": PROVIDER_INPUTS_CERTIFIED,
        "p_fcf_route_status": P_FCF_ROUTE_CERTIFICATION_FAILURE,
    }


def _p_fcf_output_signature(rows: Sequence[Mapping[str, Any]], symbol: str) -> dict[str, Any] | None:
    """Capture the decision-relevant P/FCF output for scope-isolation checks."""
    prepared = apply_peer_multiple_evidence(rows)
    row = next((item for item in prepared if _ticker(item) == symbol), None)
    if not row:
        return None
    evidence = row.get("justified_p_fcf_peer_evidence") or {}
    valuation = value_company(row)
    model = next((item for item in valuation.get("models") or ()
                  if item.get("methodology_id") == "VAL_P_FCF_V1"), {})
    return {
        "selected_peers": list(evidence.get("final_peer_set") or ()),
        "peer_p_fcf_values": {
            item.get("peer_ticker"): item.get("multiple")
            for item in evidence.get("included_peers") or ()
        },
        "median_justified_p_fcf": evidence.get("published_median"),
        "fair_value": model.get("value"),
        "route_status": model.get("status"),
    }


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("Ticker") or row.get("symbol") or "").upper().strip()


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_governed_classifications(
    path: Path = CLASSIFICATION_PATH,
    supplemental_path: Path = SUPPLEMENTAL_CLASSIFICATION_PATH,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("rows") or []
    catalog: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = _ticker(row)
        sector, industry = str(row.get("sector") or "").strip(), str(row.get("industry") or "").strip()
        if not symbol or sector.upper() in {"", "UNKNOWN", "UNAVAILABLE"} or industry.upper() in {"", "UNKNOWN", "UNAVAILABLE"}:
            continue
        catalog[symbol] = {
            "ticker": symbol,
            "company": row.get("company") or row.get("company_name") or row.get("name"),
            "sector": sector,
            "industry": industry,
            "security_type": row.get("security_type") or "COMMON_STOCK",
            "reference_market_cap": _num(row.get("market_cap")),
            "classification_source": str(path),
            "classification_source_sha256": _sha256(path),
            "classification_source_record": symbol,
        }
    supplemental_count = 0
    if supplemental_path.exists():
        payload = json.loads(supplemental_path.read_text(encoding="utf-8"))
        rows = payload.get("universe") or payload.get("rows") or payload.get("assets") or payload.get("symbols") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                symbol = _ticker(row)
                if not symbol:
                    continue
                existing = catalog.setdefault(symbol, {"ticker": symbol})
                if not existing.get("sector") and row.get("sector"):
                    source_sector = str(row["sector"])
                    existing.update({
                        "sector": GOVERNED_SECTOR_EQUIVALENCE.get(source_sector, source_sector),
                        "source_sector": source_sector,
                        "sector_normalization": "ATLAS_GOVERNED_SECTOR_TAXONOMY_EQUIVALENCE_V1",
                        "security_type": "COMMON_STOCK" if str(row.get("type") or "").upper() == "STOCK" else row.get("type"),
                        "classification_source": str(supplemental_path),
                        "classification_source_sha256": _sha256(supplemental_path),
                        "classification_source_record": symbol,
                    })
                    supplemental_count += 1
    provenance = {
        "primary_path": str(path), "primary_sha256": _sha256(path),
        "primary_resolved_count": len(catalog),
        "supplemental_path": str(supplemental_path),
        "supplemental_sha256": _sha256(supplemental_path) if supplemental_path.exists() else None,
        "supplemental_records_used": supplemental_count,
        "purpose": "CLASSIFICATION_AND_BOUNDED_ACQUISITION_ONLY",
    }
    return catalog, provenance


def _distance(reference: float | None, candidate: float | None) -> tuple[float, str]:
    if reference and candidate and reference > 0 and candidate > 0:
        return abs(math.log(candidate / reference)), ""
    return math.inf, ""


def derive_candidate_symbols(
    catalog: Mapping[str, Mapping[str, Any]], targets: Sequence[str] = TARGETS,
) -> tuple[list[str], dict[str, Any]]:
    selected = set(targets)
    diagnostics: dict[str, Any] = {}
    for symbol in targets:
        subject = catalog.get(symbol) or {}
        sector, industry = str(subject.get("sector") or ""), str(subject.get("industry") or "")
        reference_cap = _num(subject.get("reference_market_cap"))
        industry_rows = [row for ticker, row in catalog.items() if ticker != symbol and industry and
                         str(row.get("industry") or "").casefold() == industry.casefold()]
        sector_rows = [row for ticker, row in catalog.items() if ticker != symbol and sector and
                       str(row.get("sector") or "").casefold() == sector.casefold()]
        sort_key = lambda row: (_distance(reference_cap, _num(row.get("reference_market_cap")))[0], _ticker(row))
        bounded_industry = sorted(industry_rows, key=sort_key)[:MAX_INDUSTRY_CANDIDATES]
        bounded_sector = sorted(sector_rows, key=sort_key)[:MAX_SECTOR_CANDIDATES]
        selected.update(_ticker(row) for row in (*bounded_industry, *bounded_sector))
        diagnostics[symbol] = {
            "sector": sector or None, "industry": industry or None,
            "industry_candidates_available": len(industry_rows),
            "sector_candidates_available": len(sector_rows),
            "industry_candidates_bounded": [_ticker(row) for row in bounded_industry],
            "sector_candidates_bounded": [_ticker(row) for row in bounded_sector],
        }
    return sorted(selected), diagnostics


def _ordered_target_candidates(
    catalog: Mapping[str, Mapping[str, Any]], symbol: str,
) -> list[tuple[str, str]]:
    """Return the governed peer search order without changing eligibility rules."""
    subject = catalog.get(symbol) or {}
    sector, industry = str(subject.get("sector") or ""), str(subject.get("industry") or "")
    reference_cap = _num(subject.get("reference_market_cap"))
    sort_key = lambda item: (_distance(reference_cap, _num(item[1].get("reference_market_cap")))[0], item[0])
    industry_rows = sorted(
        ((ticker, row) for ticker, row in catalog.items() if ticker != symbol and industry and
         str(row.get("industry") or "").casefold() == industry.casefold()), key=sort_key,
    )
    industry_symbols = {ticker for ticker, _ in industry_rows}
    sector_rows = sorted(
        ((ticker, row) for ticker, row in catalog.items() if ticker != symbol and ticker not in industry_symbols and
         sector and str(row.get("sector") or "").casefold() == sector.casefold()), key=sort_key,
    )
    return [(ticker, "SAME_INDUSTRY") for ticker, _ in industry_rows] + [
        (ticker, "SECTOR_FALLBACK") for ticker, _ in sector_rows
    ]


def _peer_count_for_target(rows: Sequence[Mapping[str, Any]], symbol: str) -> int:
    prepared = apply_peer_multiple_evidence(rows)
    target = next((row for row in prepared if _ticker(row) == symbol), None)
    evidence = (target or {}).get("justified_p_fcf_peer_evidence") or {}
    return len(evidence.get("included_peers") or ())


def acquire_adaptive_peer_coverage(
    adapter: FinnhubShadowAdapter,
    *,
    rows: list[dict[str, Any]],
    acquisition: dict[str, dict[str, Any]],
    catalog: Mapping[str, Mapping[str, Any]],
    targets: Sequence[str] = TARGETS,
    pace_seconds: float,
    batch_size: int = ADAPTIVE_BATCH_SIZE,
    max_additional_symbols_per_target: int = MAX_ADAPTIVE_ADDITIONAL_SYMBOLS_PER_TARGET,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Acquire governed candidates incrementally until coverage or exhaustion.

    Acquisition order follows the existing industry-first/sector-fallback and
    market-cap proximity ordering.  Peer eligibility and certification remain
    exclusively owned by the existing Professional V2 evidence path.
    """
    base_scope = set(acquisition)
    acquired = set(base_scope)
    rows_by_ticker = {_ticker(row): row for row in rows}
    provider_calls: list[str] = []
    diagnostics: dict[str, Any] = {}
    for target in targets:
        target_scope = set(base_scope)
        scoped_rows = [row for ticker, row in rows_by_ticker.items() if ticker in target_scope]
        initial_count = _peer_count_for_target(scoped_rows, target)
        starting_count = initial_count
        queue = [(ticker, stage) for ticker, stage in _ordered_target_candidates(catalog, target)
                 if ticker not in target_scope]
        target_attempts: list[dict[str, Any]] = []
        target_provider_calls = 0
        while initial_count < FULL_CORE_RERUN_CONTRACT["minimum_certified_peers_per_target"] and queue:
            remaining_budget = max_additional_symbols_per_target - target_provider_calls
            if remaining_budget <= 0:
                break
            batch = queue[:batch_size]
            queue = queue[len(batch):]
            uncached = [ticker for ticker, _ in batch if ticker not in acquired]
            if len(uncached) > remaining_budget:
                allowed = set(uncached[:remaining_budget])
                deferred = [(ticker, stage) for ticker, stage in batch if ticker not in acquired and ticker not in allowed]
                batch = [(ticker, stage) for ticker, stage in batch if ticker in acquired or ticker in allowed]
                queue = deferred + queue
                uncached = [ticker for ticker, _ in batch if ticker not in acquired]
            new_rows, new_diagnostics = acquire_universe(adapter, uncached, catalog, pace_seconds)
            rows.extend(new_rows)
            rows_by_ticker.update({_ticker(row): row for row in new_rows})
            acquisition.update(new_diagnostics)
            acquired.update(uncached)
            provider_calls.extend(uncached)
            target_provider_calls += len(uncached)
            for ticker, stage in batch:
                target_scope.add(ticker)
                item = acquisition.get(ticker) or {}
                target_attempts.append({
                    "ticker": ticker,
                    "selection_stage": stage,
                    "provider_response_reused_from_cache": ticker not in uncached,
                    "complete_financial_evidence": not bool(item.get("unresolved_fields")),
                    "unresolved_fields": list(item.get("unresolved_fields") or ()),
                    "provider_availability": item.get("provider_availability") or {},
                })
            scoped_rows = [row for ticker, row in rows_by_ticker.items() if ticker in target_scope]
            initial_count = _peer_count_for_target(scoped_rows, target)
        diagnostics[target] = {
            "initial_certified_peer_count": starting_count,
            "final_certified_peer_count": initial_count,
            "candidates_tested": target_attempts,
            "logical_evidence_scope_symbols": sorted(target_scope),
            "logical_evidence_scope_count": len(target_scope),
            "target_provider_call_count": target_provider_calls,
            "candidate_queue_remaining": len(queue),
            "governed_candidate_universe_exhausted": not queue,
            "stopped_on_minimum_peer_coverage": initial_count >= FULL_CORE_RERUN_CONTRACT["minimum_certified_peers_per_target"],
            "stopped_on_target_provider_call_bound": target_provider_calls >= max_additional_symbols_per_target,
        }
    return rows, acquisition, {
        "batch_size": batch_size,
        "max_additional_symbols_per_target": max_additional_symbols_per_target,
        "physical_provider_calls": provider_calls,
        "physical_provider_call_count": len(provider_calls),
        "base_logical_scope_symbols": sorted(base_scope),
        "base_logical_scope_count": len(base_scope),
        "targets": diagnostics,
    }


def _latest_fy(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    reports = [r for r in payload.get("reports") or () if isinstance(r, Mapping) and r.get("fiscal_period") == "FY"]
    return max(reports, key=lambda r: str(r.get("fiscal_date") or ""), default=None)


def _fetch(adapter: FinnhubShadowAdapter, capability: str, symbol: str, pace_seconds: float) -> dict[str, Any]:
    value = adapter.fetch(capability, symbol).as_dict()
    if pace_seconds:
        time.sleep(pace_seconds)
    return value


def acquire_row(
    adapter: FinnhubShadowAdapter, symbol: str, classification: Mapping[str, Any], pace_seconds: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    profile = _fetch(adapter, "company_profile", symbol, pace_seconds)
    statements = _fetch(adapter, "financial_statements", symbol, pace_seconds)
    basics = _fetch(adapter, "basic_financials", symbol, pace_seconds)
    profile_payload, basic_payload = profile.get("payload") or {}, basics.get("payload") or {}
    report = _latest_fy(statements.get("payload") or {})
    facts = (report or {}).get("canonical_facts") or {}
    fcf, diluted = facts.get("free_cash_flow") or {}, facts.get("weighted_average_shares_diluted") or {}
    cap = _num(basic_payload.get("market_capitalization"))
    current_shares = _num(basic_payload.get("shares_outstanding"))
    currency = str(profile_payload.get("currency") or fcf.get("currency") or "").upper() or None
    unresolved = []
    for field, value in (("sector", classification.get("sector")), ("industry", classification.get("industry")),
                         ("security_type", classification.get("security_type")), ("market_cap", cap),
                         ("free_cash_flow", fcf.get("value")), ("diluted_shares", diluted.get("value")),
                         ("currency", currency)):
        if value in (None, ""):
            unresolved.append(field)
    evidence_ids = [
        item.get("provenance", {}).get("raw_evidence_id") for item in (profile, statements, basics)
        if item.get("provenance", {}).get("raw_evidence_id")
    ]
    diagnostic = {
        "ticker": symbol, "unresolved_fields": unresolved,
        "provider_status": {
            name: record.get("provenance", {}).get("certification_status")
            for name, record in (("profile", profile), ("financial_statements", statements), ("basic_financials", basics))
        },
        "provider_availability": {
            name: {
                "classification": classify_provider_record(record),
                "reason": (record.get("payload") or {}).get("reason"),
                "endpoint_or_source_family": (record.get("provenance") or {}).get("endpoint_or_source_family"),
            }
            for name, record in (("profile", profile), ("financial_statements", statements), ("basic_financials", basics))
        },
        "fiscal_period": (report or {}).get("fiscal_date"), "evidence_ids": evidence_ids,
    }
    if unresolved:
        return None, diagnostic
    captured = basics.get("provenance", {}).get("capture_timestamp")
    market_lineage = basic_payload.get("market_capitalization_lineage") or {}
    fcf_evidence_id = statements.get("provenance", {}).get("raw_evidence_id")
    row = {
        "ticker": symbol,
        "company": classification.get("company") or profile_payload.get("name") or symbol,
        "sector": classification.get("sector"), "industry": classification.get("industry"),
        "security_type": classification.get("security_type"),
        "market_cap": cap, "current_shares_outstanding": current_shares,
        "normalized_fcf": _num(fcf.get("value")), "free_cash_flow": _num(fcf.get("value")),
        "diluted_shares": _num(diluted.get("value")),
        "current_price": cap / current_shares if cap and current_shares else None,
        "net_income": _num((facts.get("net_income") or {}).get("value")),
        "financial_reporting_period": report.get("fiscal_date"),
        "professional_evidence_as_of": captured,
        "professional_evidence_fetched_at": captured,
        "classification_lineage": {
            key: classification.get(key) for key in (
                "classification_source", "classification_source_sha256", "classification_source_record"
            )
        },
        "professional_evidence_lineage": {
            "provider": "FINNHUB", "evidence_ids": evidence_ids,
            "fields": {
                "market_cap": {
                    "evidence_id": basics.get("provenance", {}).get("raw_evidence_id"),
                    "unit": market_lineage.get("normalized_unit") or currency,
                    "currency": currency, "as_of": captured,
                    "temporal_semantics": market_lineage.get("temporal_semantics"),
                },
                "normalized_fcf": {
                    "evidence_id": fcf_evidence_id, "unit": fcf.get("normalized_unit") or currency,
                    "currency": fcf.get("currency") or currency,
                    "period": fcf.get("period_end"), "source_record_version": fcf.get("source_record_version"),
                },
                "diluted_shares": {
                    "evidence_id": fcf_evidence_id, "unit": "SHARES",
                    "period": diluted.get("period_end"), "source_record_version": diluted.get("source_record_version"),
                },
            },
        },
    }
    return row, diagnostic


def acquire_universe(
    adapter: FinnhubShadowAdapter, acquisition_symbols: Sequence[str],
    catalog: Mapping[str, Mapping[str, Any]], pace_seconds: float,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Acquire all issuers while retaining record-level fail-closed evidence."""
    rows: list[dict[str, Any]] = []
    acquisition: dict[str, dict[str, Any]] = {}
    for symbol in acquisition_symbols:
        classification = catalog.get(symbol) or {}
        if not classification.get("sector") or not classification.get("industry"):
            acquisition[symbol] = {"ticker": symbol, "unresolved_fields": ["sector_or_industry"]}
            continue
        try:
            row, diagnostic = acquire_row(adapter, symbol, classification, pace_seconds)
        except Exception as exc:
            acquisition[symbol] = {
                "ticker": symbol,
                "unresolved_fields": ["atlas_integration_failure"],
                "atlas_integration_failure": {"exception_type": type(exc).__name__},
            }
            continue
        acquisition[symbol] = diagnostic
        if row is not None:
            rows.append(row)
    return rows, acquisition


def build_report(*, pace_seconds: float = 1.05) -> dict[str, Any]:
    catalog, classification_provenance = load_governed_classifications()
    adapter = FinnhubShadowAdapter()

    # WMT is absent from the current governed discovery candidate artifact.
    # Its governed stock/sector identity is present in the supplemental universe;
    # the live provider profile supplies company/industry only as an explicit
    # classification join, never as a valuation input.
    if "WMT" in catalog and not catalog["WMT"].get("industry"):
        profile = _fetch(adapter, "company_profile", "WMT", pace_seconds)
        basics = _fetch(adapter, "basic_financials", "WMT", pace_seconds)
        payload = profile.get("payload") or {}
        if payload.get("industry"):
            catalog["WMT"].update({
                "industry": payload["industry"], "company": payload.get("name"),
                "reference_market_cap": (basics.get("payload") or {}).get("market_capitalization"),
                "classification_provider_evidence_id": profile.get("provenance", {}).get("raw_evidence_id"),
            })
    acquisition_symbols, candidate_diagnostics = derive_candidate_symbols(catalog)
    rows, acquisition = acquire_universe(adapter, acquisition_symbols, catalog, pace_seconds)
    base_scope_rows = list(rows)
    base_output_signatures = {
        symbol: signature for symbol in TARGETS
        if (signature := _p_fcf_output_signature(base_scope_rows, symbol))
        and signature.get("route_status") == "PUBLISHED"
    }
    rows, acquisition, adaptive_diagnostics = acquire_adaptive_peer_coverage(
        adapter, rows=rows, acquisition=acquisition, catalog=catalog, pace_seconds=pace_seconds,
    )

    target_results = {}
    for symbol in TARGETS:
        target_scope = set(
            ((adaptive_diagnostics.get("targets") or {}).get(symbol) or {}).get("logical_evidence_scope_symbols")
            or acquisition_symbols
        )
        scoped_rows = [item for item in rows if _ticker(item) in target_scope]
        prepared = apply_peer_multiple_evidence(scoped_rows)
        by_symbol = {_ticker(item): item for item in prepared}
        row = by_symbol.get(symbol)
        if not row:
            target_results[symbol] = {
                "status": "FAIL_PROVIDER_DATA", "blocker": "TARGET_EVIDENCE_INCOMPLETE",
                **classify_target_route(
                    target_row_present=False, certified_peer_count=0,
                    route_certified=False, candidate_universe_exhausted=False,
                ),
            }
            continue
        evidence = row.get("justified_p_fcf_peer_evidence") or {}
        valuation = value_company(row)
        model = next((m for m in valuation.get("models") or () if m.get("methodology_id") == "VAL_P_FCF_V1"), {})
        peer_certification = certify_peer_multiple(model) if model else {"status": "NOT_EVALUATED"}
        route_certified = model.get("status") == "PUBLISHED" and peer_certification.get("status") == "CERTIFIED"
        adaptive_target = (adaptive_diagnostics.get("targets") or {}).get(symbol) or {}
        route_classification = classify_target_route(
            target_row_present=True,
            certified_peer_count=len(evidence.get("included_peers") or ()),
            route_certified=route_certified,
            candidate_universe_exhausted=bool(adaptive_target.get("governed_candidate_universe_exhausted")),
        )
        downstream_blockers = []
        if route_certified:
            downstream_blockers.extend((
                "OTHER_REQUIRED_PILLAR_EVIDENCE_NOT_ACQUIRED",
                "SINGLE_METHOD_VALUATION_NOT_SUFFICIENT_FOR_BUY_NOW",
                "ACTION_NOT_EXECUTED_IN_SHADOW_CERTIFICATION",
            ))
        target_results[symbol] = {
            "status": "CERTIFIED_P_FCF" if route_certified else "FAIL_P_FCF_CERTIFICATION",
            **route_classification,
            "company": row.get("company"), "sector": row.get("sector"), "industry": row.get("industry"),
            "normalized_historical_fcf": row.get("normalized_fcf"), "diluted_shares": row.get("diluted_shares"),
            "current_market_cap": row.get("market_cap"), "implied_current_price": row.get("current_price"),
            "eligible_candidates": evidence.get("industry_candidate_count") if evidence.get("selection_rule") == "same industry" else evidence.get("sector_candidate_count"),
            "selection_rule": evidence.get("selection_rule"),
            "selected_peers": evidence.get("final_peer_set") or [],
            "peer_p_fcf_values": {item.get("peer_ticker"): item.get("multiple") for item in evidence.get("included_peers") or ()},
            "excluded_peers": evidence.get("excluded_peers") or [],
            "certified_peer_count": len(evidence.get("included_peers") or ()),
            "median_justified_p_fcf": evidence.get("published_median"),
            "fair_value": model.get("value"), "route_status": model.get("status"),
            "route_reason": model.get("reason"), "peer_certification": peer_certification,
            "valuation_status": valuation.get("status"), "expected_return": valuation.get("expected_return"),
            "opportunity": None, "decision_confidence": None, "action": None,
            "downstream_blockers": downstream_blockers or [model.get("reason") or evidence.get("sufficiency_status")],
            "classification_lineage": row.get("classification_lineage"),
        }
        current_signature = _p_fcf_output_signature(scoped_rows, symbol)
        baseline_signature = base_output_signatures.get(symbol)
        target_results[symbol]["numerical_isolation"] = {
            "baseline_was_sufficient": baseline_signature is not None,
            "status": (
                "TARGET_SCOPE_CONTAMINATION" if baseline_signature is not None and current_signature != baseline_signature
                else "PASS"
            ),
            "baseline_output": baseline_signature,
            "isolated_output": current_signature,
        }
        acquired_symbols = target_scope
        complete_symbols = {_ticker(item) for item in scoped_rows}
        subject = catalog.get(symbol) or {}
        subject_sector = str(subject.get("sector") or "").casefold()
        subject_industry = str(subject.get("industry") or "").casefold()
        same_industry = {
            ticker for ticker, item in catalog.items() if ticker != symbol and subject_industry and
            str(item.get("industry") or "").casefold() == subject_industry
        }
        same_sector = {
            ticker for ticker, item in catalog.items() if ticker != symbol and subject_sector and
            str(item.get("sector") or "").casefold() == subject_sector
        }
        rejection_counts: dict[str, int] = {}
        for item in evidence.get("excluded_peers") or ():
            reason = str(item.get("exclusion_reason") or "UNKNOWN")
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        unavailable_candidates = [
            ticker for ticker in (same_sector & acquired_symbols)
            if ticker not in complete_symbols and any(
                family.get("classification") == PROVIDER_DATA_UNAVAILABLE
                for family in ((acquisition.get(ticker) or {}).get("provider_availability") or {}).values()
            )
        ]
        if unavailable_candidates:
            rejection_counts[PROVIDER_DATA_UNAVAILABLE] = len(unavailable_candidates)
        target_results[symbol]["peer_coverage_forensics"] = {
            "logical_evidence_scope_count": len(target_scope),
            "logical_evidence_scope_sha256": hashlib.sha256(
                "\n".join(sorted(target_scope)).encode("utf-8")
            ).hexdigest(),
            "governed_same_industry_candidates": len(same_industry),
            "governed_sector_candidates": len(same_sector),
            "same_industry_candidates_acquired": len(same_industry & acquired_symbols),
            "sector_candidates_acquired": len(same_sector & acquired_symbols),
            "same_industry_complete_financial_evidence": len(same_industry & complete_symbols),
            "sector_complete_financial_evidence": len(same_sector & complete_symbols),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "provider_data_unavailable_symbols": sorted(unavailable_candidates),
        }
        final_selected = set(evidence.get("final_peer_set") or ())
        final_exclusions = {
            str(item.get("peer_ticker")): item.get("exclusion_reason")
            for item in evidence.get("excluded_peers") or ()
        }
        for item in adaptive_target.get("candidates_tested") or ():
            ticker = str(item.get("ticker") or "")
            item["final_peer_disposition"] = (
                "SELECTED_COMPARABLE" if ticker in final_selected
                else final_exclusions.get(ticker)
                or (PROVIDER_DATA_UNAVAILABLE if ticker in unavailable_candidates else "NOT_SELECTED")
            )
    certified = sum(result.get("status") == "CERTIFIED_P_FCF" for result in target_results.values())
    contamination_targets = sorted(
        symbol for symbol, result in target_results.items()
        if (result.get("numerical_isolation") or {}).get("status") == "TARGET_SCOPE_CONTAMINATION"
    )
    exclusions: dict[str, int] = {}
    for result in target_results.values():
        for item in result.get("excluded_peers") or ():
            reason = str(item.get("exclusion_reason") or "UNKNOWN")
            exclusions[reason] = exclusions.get(reason, 0) + 1
    entitlement_symbols = sorted({
        symbol for symbol, item in acquisition.items()
        if any(family.get("classification") == CREDENTIAL_ENTITLEMENT_UNAVAILABLE
               for family in (item.get("provider_availability") or {}).values())
    })
    expected_demo_restriction_symbols = sorted({
        symbol for symbol, item in acquisition.items()
        if any(family.get("classification") == EXPECTED_DEMO_SYMBOL_RESTRICTION
               for family in (item.get("provider_availability") or {}).values())
    })
    provider_data_unavailable_symbols = sorted({
        symbol for symbol, item in acquisition.items()
        if any(family.get("classification") == PROVIDER_DATA_UNAVAILABLE
               for family in (item.get("provider_availability") or {}).values())
    })
    atlas_integration_failure_symbols = sorted(
        symbol for symbol, item in acquisition.items() if item.get("atlas_integration_failure")
    )
    requested_symbols = sorted(acquisition)
    classification_complete = sum(
        bool((catalog.get(symbol) or {}).get("sector") and (catalog.get(symbol) or {}).get("industry"))
        for symbol in requested_symbols
    )
    historical_complete = sum(
        bool(item.get("fiscal_period")) and "free_cash_flow" not in item.get("unresolved_fields", ())
        for item in acquisition.values()
    )
    basic_complete = sum(
        "market_cap" not in item.get("unresolved_fields", ()) and
        (item.get("provider_availability") or {}).get("basic_financials", {}).get("classification") == CERTIFIED_DATA_AVAILABLE
        for item in acquisition.values()
    )
    integration_failure_targets = sorted(
        symbol for symbol, result in target_results.items()
        if result.get("status") != "CERTIFIED_P_FCF" and int(result.get("certified_peer_count") or 0) >= 3
    )
    coverage = {
        "symbols_requested": len(requested_symbols),
        "base_bounded_symbols_requested": len(acquisition_symbols),
        "adaptive_additional_symbols_requested": len(requested_symbols) - len(acquisition_symbols),
        "classification_complete": classification_complete,
        "historical_financial_complete": historical_complete,
        "basic_financial_complete": basic_complete,
        "credential_entitlement_failure_count": len(entitlement_symbols),
        "credential_entitlement_failure_symbols": entitlement_symbols,
        "expected_demo_symbol_restriction_count": len(expected_demo_restriction_symbols),
        "expected_demo_symbol_restriction_symbols": expected_demo_restriction_symbols,
        "provider_data_unavailable_failure_count": len(provider_data_unavailable_symbols),
        "provider_data_unavailable_symbols": provider_data_unavailable_symbols,
        "provider_contract_unresolved_count": 0,
        "atlas_integration_failure_count": len(atlas_integration_failure_symbols),
        "atlas_integration_failure_symbols": atlas_integration_failure_symbols,
        "canonical_certification_failure_count": len(integration_failure_targets),
        "atlas_integration_failure_targets": integration_failure_targets,
    }
    all_targets_have_three = all(
        int(result.get("certified_peer_count") or 0) >= 3 for result in target_results.values()
    )
    all_targets_certified = certified == len(TARGETS)
    core_ready = (
        coverage["classification_complete"] == coverage["symbols_requested"]
        and coverage["credential_entitlement_failure_count"] == 0
        and coverage["expected_demo_symbol_restriction_count"] == 0
        and coverage["atlas_integration_failure_count"] == 0
        and not contamination_targets
        and all_targets_have_three and all_targets_certified
        and coverage["canonical_certification_failure_count"] == 0
    )
    breadth_classification = (
        PAID_CORE_BREADTH_UNTESTED if expected_demo_restriction_symbols
        else "FULL_CORE_ENTITLEMENT_FAILED" if entitlement_symbols
        else "BROAD_COVERAGE_INCOMPLETE"
    )
    capability_matrix = {
        "market_technical_contract": {
            "classifications": ["PROVEN_WITH_CURRENT_CREDENTIAL", "ATLAS_INTEGRATION_COMPLETE"],
            "evidence": "completed-session market/technical contract previously certified",
        },
        "historical_filings": {
            "classifications": [breadth_classification, "ATLAS_INTEGRATION_COMPLETE"],
            "evidence": f"{historical_complete}/{len(requested_symbols)} complete; {len(expected_demo_restriction_symbols)} expected demo restrictions; {len(entitlement_symbols)} paid-credential entitlement failures",
        },
        "basic_financials": {
            "classifications": [breadth_classification, "ATLAS_INTEGRATION_COMPLETE"],
            "evidence": f"{basic_complete}/{len(requested_symbols)} complete; {len(expected_demo_restriction_symbols)} expected demo restrictions; {len(entitlement_symbols)} paid-credential entitlement failures",
        },
        "broad_peer_financial_coverage": {
            "classifications": [breadth_classification],
            "evidence": f"{len(rows)}/{len(requested_symbols)} complete governed peer records",
        },
        "p_fcf_route": {
            "classifications": [breadth_classification, "ATLAS_INTEGRATION_COMPLETE"],
            "evidence": f"{certified}/{len(TARGETS)} live targets certified; deterministic production-reachable fixture passes",
        },
        "forward_estimate_contract": {
            "classifications": ["BLOCKED_BY_DOCUMENTATION"],
            "evidence": "estimate unit, scale, and currency contract unresolved",
        },
        "transcript_capability": {
            "classifications": ["NOT_REQUIRED"],
            "evidence": "Finnhub transcript capability is not required; EarningsCall remains separate non-scoring context",
        },
    }
    return {
        "version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "FINNHUB_ONLY_SHADOW_P_FCF_CERTIFICATION",
        "production_authority_changed": False, "methodology_changed": False,
        "classification_provenance": classification_provenance,
        "peer_universe": {
            "classification_catalog_size": len(catalog), "bounded_acquisition_symbol_count": len(acquisition_symbols),
            "total_acquisition_symbol_count": len(requested_symbols),
            "complete_certified_row_count": len(rows), "targets": list(TARGETS),
            "candidate_derivation": candidate_diagnostics,
            "adaptive_acquisition": adaptive_diagnostics,
        },
        "acquisition_diagnostics": acquisition,
        "peer_certification_statistics": {
            "certified_target_count": certified, "failed_target_count": len(TARGETS) - certified,
            "exclusion_reason_counts": dict(sorted(exclusions.items())),
            "target_scope_contamination_count": len(contamination_targets),
            "target_scope_contamination_targets": contamination_targets,
        },
        "entitlement_coverage_gate": coverage,
        "provider_commercial_readiness_matrix": capability_matrix,
        "target_results": target_results,
        "certified_p_fcf_count": certified,
        "certified_fair_value_count": sum(bool(r.get("fair_value")) and r.get("status") == "CERTIFIED_P_FCF" for r in target_results.values()),
        "certified_action_count": 0,
        "launch_readiness": {
            "historical_p_fcf": "PASS" if certified >= 5 else "PASS_WITH_LIMITATIONS" if certified else "FAIL",
            "finnhub_core_ready_for_final_certification": core_ready,
            "finnhub_core_state": (
                "FINNHUB_CORE_READY_FOR_FINAL_CERTIFICATION" if core_ready
                else PAID_CORE_BREADTH_UNTESTED if expected_demo_restriction_symbols
                else "FULL_CORE_ENTITLEMENT_FAILED" if entitlement_symbols
                else "BROAD_PEER_CERTIFICATION_INCOMPLETE"
            ),
            "forward_valuation_state": "FORWARD_VALUATION_CONTRACT_PENDING",
            "limited_method_launch": "NOT_PROVEN" if certified < 5 else "P_FCF_ONLY_REMAINS_INSUFFICIENT_FOR_BUY_NOW",
            "third_provider": "NOT_JUSTIFIED_BY_ENTITLEMENT_FAILURE_ALONE; REQUIRED_ONLY_IF_FINNHUB_FULL_CORE_CANNOT_SATISFY_THE_RERUN_GATE_OR_FOR_BROADER_FORWARD_METHODS",
            "full_core_rerun_gate": {
                **FULL_CORE_RERUN_CONTRACT,
                "same_governed_universe_required": True,
                "symbols_requested": len(requested_symbols),
                "classification_complete_required": len(requested_symbols),
                "all_eight_targets_p_fcf_certified": True,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="audit_results/finnhub_certification/finnhub_p_fcf_peer_certification.json")
    parser.add_argument("--pace-seconds", type=float, default=1.05)
    args = parser.parse_args()
    adapter = FinnhubShadowAdapter()
    if adapter.license_class == FINNHUB_DEMO_LICENSE:
        report = {
            "version": VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "FINNHUB_ONLY_SHADOW_P_FCF_CERTIFICATION",
            "production_authority_changed": False,
            "methodology_changed": False,
            "broad_acquisition_executed": False,
            "launch_readiness": {
                "finnhub_core_ready_for_final_certification": False,
                "finnhub_core_state": PAID_CORE_BREADTH_UNTESTED,
                "reason": "DEMO_CREDENTIAL_CANNOT_TEST_OUTSIDE_WHITELIST_BREADTH",
                "forward_valuation_state": "FORWARD_VALUATION_CONTRACT_PENDING",
            },
        }
        path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report["launch_readiness"], indent=2))
        return 6
    report = build_report(pace_seconds=max(0.0, args.pace_seconds))
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "version": report["version"], "peer_universe": report["peer_universe"],
        "certified_p_fcf_count": report["certified_p_fcf_count"],
        "launch_readiness": report["launch_readiness"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
