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
from services.finnhub_shadow_provider import FinnhubShadowAdapter
from services.professional_valuation_evidence import apply_peer_multiple_evidence
from services.valuation_evidence_strength import certify_peer_multiple


VERSION = "ATLAS_FINNHUB_P_FCF_PEER_CERTIFICATION_V1"
TARGETS = ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA")
CLASSIFICATION_PATH = Path("discovery_candidate_pool.json")
SUPPLEMENTAL_CLASSIFICATION_PATH = Path("analysis/phase8b_calibration/universe_v1.json")
MAX_INDUSTRY_CANDIDATES = 14
MAX_SECTOR_CANDIDATES = 22
GOVERNED_SECTOR_EQUIVALENCE = {
    # The supplemental calibration universe uses the GICS label while the
    # discovery classification artifact uses the equivalent customer taxonomy.
    # This is identity normalization only; it does not alter peer eligibility.
    "Consumer Staples": "Consumer Defensive",
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
    rows, acquisition = [], {}
    for symbol in acquisition_symbols:
        classification = catalog.get(symbol) or {}
        if not classification.get("sector") or not classification.get("industry"):
            acquisition[symbol] = {"ticker": symbol, "unresolved_fields": ["sector_or_industry"]}
            continue
        row, diagnostic = acquire_row(adapter, symbol, classification, pace_seconds)
        acquisition[symbol] = diagnostic
        if row is not None:
            rows.append(row)

    prepared = apply_peer_multiple_evidence(rows)
    by_symbol = {_ticker(row): row for row in prepared}
    target_results = {}
    for symbol in TARGETS:
        row = by_symbol.get(symbol)
        if not row:
            target_results[symbol] = {"status": "FAIL_PROVIDER_DATA", "blocker": "TARGET_EVIDENCE_INCOMPLETE"}
            continue
        evidence = row.get("justified_p_fcf_peer_evidence") or {}
        valuation = value_company(row)
        model = next((m for m in valuation.get("models") or () if m.get("methodology_id") == "VAL_P_FCF_V1"), {})
        peer_certification = certify_peer_multiple(model) if model else {"status": "NOT_EVALUATED"}
        route_certified = model.get("status") == "PUBLISHED" and peer_certification.get("status") == "CERTIFIED"
        downstream_blockers = []
        if route_certified:
            downstream_blockers.extend((
                "OTHER_REQUIRED_PILLAR_EVIDENCE_NOT_ACQUIRED",
                "SINGLE_METHOD_VALUATION_NOT_SUFFICIENT_FOR_BUY_NOW",
                "ACTION_NOT_EXECUTED_IN_SHADOW_CERTIFICATION",
            ))
        target_results[symbol] = {
            "status": "CERTIFIED_P_FCF" if route_certified else "FAIL_P_FCF_CERTIFICATION",
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
    certified = sum(result.get("status") == "CERTIFIED_P_FCF" for result in target_results.values())
    exclusions: dict[str, int] = {}
    for result in target_results.values():
        for item in result.get("excluded_peers") or ():
            reason = str(item.get("exclusion_reason") or "UNKNOWN")
            exclusions[reason] = exclusions.get(reason, 0) + 1
    return {
        "version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "FINNHUB_ONLY_SHADOW_P_FCF_CERTIFICATION",
        "production_authority_changed": False, "methodology_changed": False,
        "classification_provenance": classification_provenance,
        "peer_universe": {
            "classification_catalog_size": len(catalog), "bounded_acquisition_symbol_count": len(acquisition_symbols),
            "complete_certified_row_count": len(rows), "targets": list(TARGETS),
            "candidate_derivation": candidate_diagnostics,
        },
        "acquisition_diagnostics": acquisition,
        "peer_certification_statistics": {
            "certified_target_count": certified, "failed_target_count": len(TARGETS) - certified,
            "exclusion_reason_counts": dict(sorted(exclusions.items())),
        },
        "target_results": target_results,
        "certified_p_fcf_count": certified,
        "certified_fair_value_count": sum(bool(r.get("fair_value")) and r.get("status") == "CERTIFIED_P_FCF" for r in target_results.values()),
        "certified_action_count": 0,
        "launch_readiness": {
            "historical_p_fcf": "PASS" if certified >= 5 else "PASS_WITH_LIMITATIONS" if certified else "FAIL",
            "limited_method_launch": "NOT_PROVEN" if certified < 5 else "P_FCF_ONLY_REMAINS_INSUFFICIENT_FOR_BUY_NOW",
            "third_provider": "REQUIRED_FOR_BROADER_FORWARD_METHOD_COVERAGE; NOT_PROVEN_REQUIRED_FOR_HISTORICAL_P_FCF",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="audit_results/finnhub_certification/finnhub_p_fcf_peer_certification.json")
    parser.add_argument("--pace-seconds", type=float, default=1.05)
    args = parser.parse_args()
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
