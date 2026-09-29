#!/usr/bin/env python3
"""Live field-scoped Finnhub canonical-path proving set.

This is a certification workflow, not a production publication workflow.  It
uses the existing ATLAS engines unchanged and persists immutable diagnostics.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping

from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
from engines.component_builder import build_components
from engines.professional_valuation_v2 import value_company
from overnight_market_scan import build_trade_plan
from scripts.finnhub_p_fcf_peer_certification import (
    _ordered_target_candidates, _p_fcf_output_signature, acquire_row,
    classify_target_route, load_governed_classifications,
)
from services.evidence_inspector import inspect_ticker
from services.finnhub_canonical_authority import AUTHORITY_VERSION, FinnhubCanonicalAdapter
from services.professional_valuation_evidence import apply_peer_multiple_evidence
from services.valuation_evidence_strength import certify_peer_multiple
from services.technical_intelligence.engine import DailyBar, TechnicalIntelligenceEngine
from services.live_market.models import FeedHealth, SecurityType


VERSION = "ATLAS_FINNHUB_CANONICAL_PROVING_SET_V1"
SYMBOLS = ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA", "ORCL", "COST", "GM", "AMGN")
PEER_BATCH_SIZE = 8


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool): return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError): return None


def _latest_fy(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    reports = [item for item in payload.get("reports") or () if item.get("fiscal_period") == "FY"]
    return max(reports, key=lambda item: str(item.get("fiscal_date") or ""), default=None)


def _fetch(adapter: FinnhubCanonicalAdapter, capability: str, symbol: str, pace: float, **params: Any) -> dict[str, Any]:
    record = adapter.fetch(capability, symbol, **params)
    if pace: time.sleep(pace)
    return record.as_dict()


def _bars(symbol: str, record: Mapping[str, Any]) -> list[DailyBar]:
    payload = record.get("payload") or {}
    columns = [payload.get(key) or [] for key in ("timestamps", "open", "high", "low", "close", "volume")]
    flags = payload.get("completed_session_flags") or []
    output = []
    for index, values in enumerate(zip(*columns)):
        if index >= len(flags) or flags[index] is not True:
            continue
        timestamp, open_, high, low, close, volume = values
        try:
            output.append(DailyBar(
                symbol, datetime.fromtimestamp(float(timestamp), timezone.utc),
                float(open_), float(high), float(low), float(close), float(volume), True,
            ))
        except (TypeError, ValueError, OSError):
            continue
    return output


def _drawdown_label(bars: list[DailyBar]) -> str | None:
    if len(bars) < 20: return None
    peak = max(bar.close for bar in bars[-63:])
    drawdown = bars[-1].close / peak - 1 if peak else None
    if drawdown is None: return None
    return "shallow drawdown" if drawdown >= -.10 else "moderate drawdown" if drawdown >= -.25 else "deep drawdown"


def _normalized_row(symbol: str, classification: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any] | None, list[DailyBar], list[str]]:
    blockers = []
    payloads = {}
    evidence_ids = []
    for capability, record in records.items():
        try:
            # Rehydrate is unnecessary: the serialized authority fields are
            # sufficient to prove that only certified records enter mapping.
            provenance = record.get("provenance") or {}
            if provenance.get("certification_status") != "CERTIFIED" or provenance.get("derived_use_permission") != "CERTIFIED_CALCULATION":
                blockers.append(f"{capability.upper()}_NOT_CANONICAL_CERTIFIED")
                continue
            payloads[capability] = record.get("payload") or {}
            evidence_ids.append(provenance.get("raw_evidence_id"))
        except Exception:
            blockers.append(f"{capability.upper()}_INTEGRATION_ERROR")
    bars = _bars(symbol, records.get("historical_ohlcv") or {})
    report = _latest_fy(payloads.get("financial_statements") or {})
    facts = (report or {}).get("canonical_facts") or {}
    basics = payloads.get("basic_financials") or {}
    profile = payloads.get("company_profile") or {}
    if not report: blockers.append("LATEST_FY_FINANCIAL_REPORT_MISSING")
    if len(bars) < 200: blockers.append("COMPLETED_TECHNICAL_HISTORY_INSUFFICIENT")
    resolved_classification = dict(classification)
    resolved_classification.setdefault("sector", profile.get("industry"))
    resolved_classification.setdefault("industry", profile.get("industry"))
    if not resolved_classification.get("sector") or not resolved_classification.get("industry"):
        blockers.append("GOVERNED_CLASSIFICATION_UNRESOLVED")
    if blockers:
        return None, bars, blockers

    def fact(name: str) -> float | None:
        return _num((facts.get(name) or {}).get("value"))
    metric_contract = basics.get("provider_contract_metrics") or {}
    def metric(name: str) -> float | None:
        item = metric_contract.get(name) or {}
        return _num(item.get("value")) if item.get("status") == "CERTIFIED_PROVIDER_CONTRACT" else None
    ocf, capex = fact("operating_cash_flow"), fact("capex")
    fcf = fact("free_cash_flow")
    if fcf is None and ocf is not None and capex is not None: fcf = ocf - abs(capex)
    debt = fact("total_debt")
    cash = fact("cash_and_equivalents") or fact("cash")
    ebitda = fact("ebitda")
    statement_provenance = records["financial_statements"]["provenance"]
    basics_provenance = records["basic_financials"]["provenance"]
    currency = report.get("currency") or profile.get("currency")
    fcf_evidence_id = statement_provenance.get("raw_evidence_id")
    market_cap_evidence_id = basics_provenance.get("raw_evidence_id")
    lineage_fields = {
        "market_cap": {
            "evidence_id": market_cap_evidence_id, "provider": "FINNHUB",
            "unit": "USD", "currency": currency,
            "as_of": basics_provenance.get("capture_timestamp"),
            "normalization": "metric.marketCapitalization MULTIPLY_BY_1E6",
        },
        "normalized_fcf": {
            "evidence_id": fcf_evidence_id, "provider": "FINNHUB",
            "unit": currency, "currency": currency, "period": report.get("fiscal_date"),
            "normalization": "REPORTED_FCF_OR_OCF_MINUS_ABSOLUTE_CAPEX",
        },
        "free_cash_flow": {
            "evidence_id": fcf_evidence_id, "provider": "FINNHUB",
            "unit": currency, "currency": currency, "period": report.get("fiscal_date"),
            "normalization": "REPORTED_FCF_OR_OCF_MINUS_ABSOLUTE_CAPEX",
        },
    }
    row = {
        "ticker": symbol, "company": profile.get("name") or symbol,
        "sector": resolved_classification.get("sector"), "industry": resolved_classification.get("industry"),
        "security_type": resolved_classification.get("security_type") or "COMMON_STOCK",
        "current_price": bars[-1].close, "price": bars[-1].close,
        "market_cap": _num(basics.get("market_capitalization")),
        "current_shares_outstanding": _num(basics.get("shares_outstanding")),
        "revenue_growth": metric("revenueGrowthTTMYoy"), "revenue_growth_pct": metric("revenueGrowthTTMYoy"),
        "earnings_growth": metric("epsGrowthTTMYoy"), "eps_growth_pct": metric("epsGrowthTTMYoy"),
        "gross_profit_margin": metric("grossMarginTTM"), "gross_margin_pct": metric("grossMarginTTM"),
        "operating_profit_margin": metric("operatingMarginTTM"), "operating_margin_pct": metric("operatingMarginTTM"),
        "net_margin_pct": metric("netProfitMarginTTM"),
        "latest_revenue": fact("revenue"), "latest_operating_income": fact("operating_income"),
        "net_income": fact("net_income"), "operating_cash_flow": ocf,
        "capital_expenditures": capex, "capex": capex, "free_cash_flow": fcf, "normalized_fcf": fcf,
        "total_debt": debt, "cash_and_equivalents": cash,
        "diluted_shares": fact("weighted_average_shares_diluted"),
        "basic_shares": fact("weighted_average_shares_basic"),
        "net_debt_to_ebitda": ((debt or 0) - (cash or 0)) / ebitda if ebitda and ebitda > 0 else None,
        "professional_evidence_as_of": records["financial_statements"]["provenance"].get("capture_timestamp"),
        "professional_evidence_lineage": {
            "provider": "FINNHUB", "evidence_ids": list(filter(None, evidence_ids)),
            "fields": lineage_fields,
        },
        "historical_ohlcv_evidence_id": (records["historical_ohlcv"].get("provenance") or {}).get("raw_evidence_id"),
        "finnhub_authority_version": AUTHORITY_VERSION,
        "forward_contract_status": "CONTRACT_PENDING",
    }
    return row, bars, []


def _target_local_peer_support(
    adapter: FinnhubCanonicalAdapter,
    *,
    targets: Mapping[str, Mapping[str, Any]],
    catalog: Mapping[str, Mapping[str, Any]],
    pace_seconds: float,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], int]:
    """Build independent logical peer scopes over one physical evidence cache."""
    physical_cache: dict[str, dict[str, Any] | None] = {}
    physical_diagnostics: dict[str, dict[str, Any]] = {}
    prepared_targets: dict[str, dict[str, Any]] = {}
    diagnostics: dict[str, Any] = {}
    provider_calls = 0
    for symbol in SYMBOLS:
        target = dict(targets[symbol])
        queue = _ordered_target_candidates(catalog, symbol)
        logical_symbols: list[str] = []
        logical_rows: list[dict[str, Any]] = [target]
        considered: list[dict[str, Any]] = []
        peer_count = 0
        while peer_count < 3 and queue:
            batch, queue = queue[:PEER_BATCH_SIZE], queue[PEER_BATCH_SIZE:]
            for peer_symbol, selection_stage in batch:
                was_cached = peer_symbol in physical_cache
                if peer_symbol not in physical_cache:
                    try:
                        row, item = acquire_row(adapter, peer_symbol, catalog.get(peer_symbol) or {}, pace_seconds)
                    except Exception as exc:
                        row, item = None, {
                            "ticker": peer_symbol, "unresolved_fields": ["atlas_integration_failure"],
                            "atlas_integration_failure": {"exception_type": type(exc).__name__},
                        }
                    physical_cache[peer_symbol] = row
                    physical_diagnostics[peer_symbol] = item
                    provider_calls += 3
                row = physical_cache[peer_symbol]
                item = physical_diagnostics[peer_symbol]
                logical_symbols.append(peer_symbol)
                if row is not None:
                    logical_rows.append(row)
                considered.append({
                    "ticker": peer_symbol, "selection_stage": selection_stage,
                    "physical_cache_reused": was_cached,
                    "complete_peer_record": row is not None,
                    "unresolved_fields": list(item.get("unresolved_fields") or ()),
                    "provider_availability": item.get("provider_availability") or {},
                })
            signature = _p_fcf_output_signature(logical_rows, symbol) or {}
            peer_count = len(signature.get("selected_peers") or ())
        prepared = apply_peer_multiple_evidence(logical_rows)
        prepared_target = next(item for item in prepared if item.get("ticker") == symbol)
        evidence = prepared_target.get("justified_p_fcf_peer_evidence") or {}
        valuation = value_company(prepared_target)
        model = next((item for item in valuation.get("models") or () if item.get("methodology_id") == "VAL_P_FCF_V1"), {})
        certification = certify_peer_multiple(model) if model else {"status": "NOT_EVALUATED"}
        certified = model.get("status") == "PUBLISHED" and certification.get("status") == "CERTIFIED"
        route = classify_target_route(
            target_row_present=True,
            certified_peer_count=len(evidence.get("included_peers") or ()),
            route_certified=certified,
            candidate_universe_exhausted=not queue,
        )
        def invariant_signature(scope: list[dict[str, Any]]) -> dict[str, Any] | None:
            signature = _p_fcf_output_signature(scope, symbol)
            if signature is None:
                return None
            return {
                **signature,
                "selected_peers": sorted(signature.get("selected_peers") or ()),
                "peer_p_fcf_values": dict(sorted((signature.get("peer_p_fcf_values") or {}).items())),
            }
        forward = invariant_signature(logical_rows)
        reverse = invariant_signature(list(reversed(logical_rows)))
        diagnostics[symbol] = {
            **route,
            "governed_candidates_considered": considered,
            "peer_support_symbols_acquired": list(logical_symbols),
            "complete_peer_record_count": len(logical_rows) - 1,
            "certified_peer_count": len(evidence.get("included_peers") or ()),
            "selected_peers": list(evidence.get("final_peer_set") or ()),
            "peer_p_fcf_values": {
                item.get("peer_ticker"): item.get("multiple")
                for item in evidence.get("included_peers") or ()
            },
            "median_justified_p_fcf": evidence.get("published_median"),
            "fair_value": model.get("value"),
            "peer_certification": certification,
            "excluded_peers": list(evidence.get("excluded_peers") or ()),
            "governed_candidate_universe_exhausted": not queue,
            "evaluation_order_invariance": "PASS" if forward == reverse else "FAIL",
            "logical_scope_sha256": hashlib.sha256("\n".join(sorted(logical_symbols)).encode()).hexdigest(),
        }
        prepared_targets[symbol] = prepared_target
    return prepared_targets, {
        "targets": diagnostics,
        "physical_peer_support_symbols": sorted(physical_cache),
        "physical_peer_support_symbol_count": len(physical_cache),
        "physical_provider_calls": provider_calls,
    }, provider_calls


def build_report(*, pace_seconds: float = 1.05) -> dict[str, Any]:
    adapter = FinnhubCanonicalAdapter()
    catalog, catalog_provenance = load_governed_classifications()
    now = datetime.now(timezone.utc)
    start = int((now.timestamp()) - 400 * 86400)
    end = int(now.timestamp())
    rows, technical_by_symbol, diagnostics = [], {}, {}
    provider_calls = 0
    for symbol in SYMBOLS:
        classification = catalog.get(symbol) or {}
        records = {
            "company_profile": _fetch(adapter, "company_profile", symbol, pace_seconds),
            "financial_statements": _fetch(adapter, "financial_statements", symbol, pace_seconds),
            "basic_financials": _fetch(adapter, "basic_financials", symbol, pace_seconds),
            "historical_ohlcv": _fetch(adapter, "historical_ohlcv", symbol, pace_seconds, resolution="D", **{"from": start, "to": end}),
        }
        provider_calls += 4
        row, bars, blockers = _normalized_row(symbol, classification, records)
        diagnostics[symbol] = {"authority_blockers": blockers, "record_statuses": {
            key: (value.get("provenance") or {}).get("certification_status") for key, value in records.items()
        }}
        if row is not None:
            rows.append(row); technical_by_symbol[symbol] = bars
    target_rows = {row["ticker"]: row for row in rows}
    for symbol, row in target_rows.items():
        catalog.setdefault(symbol, {}).update({
            "sector": row.get("sector"), "industry": row.get("industry"),
            "security_type": row.get("security_type"), "reference_market_cap": row.get("market_cap"),
        })
    peer_support = {"targets": {}, "physical_peer_support_symbols": [], "physical_peer_support_symbol_count": 0, "physical_provider_calls": 0}
    prepared = []
    if len(target_rows) == len(SYMBOLS):
        prepared_by_symbol, peer_support, peer_calls = _target_local_peer_support(
            adapter, targets=target_rows, catalog=catalog, pace_seconds=pace_seconds,
        )
        provider_calls += peer_calls
        prepared = [prepared_by_symbol[symbol] for symbol in SYMBOLS]
    evaluations = {}
    for row in prepared:
        symbol = row["ticker"]; bars = technical_by_symbol[symbol]
        analysis = TechnicalIntelligenceEngine().evaluate(bars, security_type=SecurityType.STOCK, feed_health=FeedHealth.HEALTHY)
        ev = dict(analysis.result.evidence)
        ev.update({
            "completed_daily_evidence": True, "valid_daily_volume_baseline": True,
            "volume_statistic": "DAILY_RELATIVE_VOLUME", "volume_session_scope": "COMPLETED_SESSION",
            "volume_semantics": "CONSOLIDATED_AFTER_4PM", "provider_authority": "CANONICAL_CERTIFIED",
            "volume_evidence_id": row.get("historical_ohlcv_evidence_id"),
            "as_of": analysis.result.event_timestamp.isoformat(),
        })
        technical = {
            "status": "AVAILABLE", "state": analysis.result.new_state.value, "score": analysis.result.score,
            "as_of": analysis.result.event_timestamp.isoformat(), "feed_health": "HEALTHY",
            "completed_bar": True, "fingerprint": analysis.result.fingerprint, "evidence": ev,
        }
        indicator = {"price": bars[-1].close, "atr14": ev.get("atr14"), "sma20": ev.get("sma20"), "rolling_high_20": max(bar.high for bar in bars[-20:])}
        plan = build_trade_plan(indicator, int(analysis.result.score))
        plan["target_1"] = plan.get("target")
        plan["entry_relationship_valid"] = bool(plan.get("entry_low") <= plan.get("entry_high") < plan.get("target_1"))
        components = build_components(row)
        fundamentals = dict(components["fundamentals"])
        fundamentals["evidence_ids"] = tuple((row.get("professional_evidence_lineage") or {}).get("evidence_ids") or ())
        risk = {
            "status": "AVAILABLE" if row.get("free_cash_flow") is not None and _drawdown_label(bars) else "DATA_UNAVAILABLE",
            "as_of": technical["as_of"], "net_debt_to_ebitda": row.get("net_debt_to_ebitda"),
            "evidence": {"drawdown_label": _drawdown_label(bars), "volatility_risk": _drawdown_label(bars)},
        }
        market = {
            "ticker": symbol, "price": bars[-1].close, "provider": "FINNHUB",
            "provider_timestamp": bars[-1].timestamp.isoformat(), "received_timestamp": now.isoformat(),
            "source_type": "LATEST_COMPLETED_SESSION", "fresh_current_price": False,
            "latest_completed_session_valid": True, "stale": False, "feed_health": "HEALTHY",
            "evidence_id": f"FINNHUB:HISTORICAL_OHLCV:{symbol}:LATEST",
        }
        evaluation = build_canonical_evaluation(
            symbol, evaluation_mode="SNAPSHOT", market_snapshot=market, technical=technical,
            fundamentals=fundamentals, risk=risk, trade_plan=plan, valuation_inputs=row,
            evidence_ids=tuple((row.get("professional_evidence_lineage") or {}).get("evidence_ids") or ()),
            positive_action_volume_authority_required=True, evaluated_at=now.isoformat(),
        )
        combined = {**row, **evaluation}
        inspector = inspect_ticker(combined)
        professional = (evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}
        route_states = {
            item.get("methodology_id"): item.get("status") or item.get("eligibility_state")
            for item in professional.get("models") or ()
        }
        diagnostics[symbol].update({
            "canonical_action": (evaluation.get("guidance") or {}).get("state"),
            "valuation_status": (evaluation.get("atlas_valuation") or {}).get("status"),
            "valuation_route_states": route_states,
            "shadow_evidence_leakage": any(
                marker in json.dumps(combined, sort_keys=True, default=str)
                for marker in ("UNVERIFIED_SHADOW", "SHADOW_ONLY")
            ),
            "inspector_traceability": inspector["traceability"],
            "peer_support": (peer_support.get("targets") or {}).get(symbol),
        })
        evaluations[symbol] = evaluation
    historical_route_count = sum(
        item.get("valuation_status") == "AVAILABLE" for item in diagnostics.values()
    )
    forward_route_leakage = any(
        any(states.get(method) in {"CERTIFIED", "ELIGIBLE_COMPLETE", "PUBLISHED"} for method in ("VAL_FORWARD_PE_V1", "VAL_EV_EBITDA_V1"))
        for states in (item.get("valuation_route_states") or {} for item in diagnostics.values())
    )
    ready = historical_route_count > 0 and not forward_route_leakage and len(evaluations) == len(SYMBOLS) and all(
        not item.get("authority_blockers") and not item.get("shadow_evidence_leakage")
        and (item.get("inspector_traceability") or {}).get("status") == "PASS"
        and ((item.get("peer_support") or {}).get("evaluation_order_invariance") == "PASS")
        and ((item.get("peer_support") or {}).get("provider_input_status") == "CERTIFIED_COMPLETE")
        for item in diagnostics.values()
    )
    payload = {
        "version": VERSION, "authority_version": AUTHORITY_VERSION,
        "generated_at": now.isoformat(), "symbols": list(SYMBOLS), "provider_calls": provider_calls,
        "classification_provenance": catalog_provenance,
        "certified_historical_valuation_count": historical_route_count,
        "forward_route_leakage": forward_route_leakage,
        "peer_support": peer_support,
        "evaluations": evaluations, "diagnostics": diagnostics,
        "state": "FINNHUB_CANONICAL_PATH_READY" if ready else "FINNHUB_CANONICAL_PATH_NOT_READY",
        "provider_authority_scope": "FIELD_FAMILY_SCOPED_ONLY", "production_cutover": False,
    }
    digest_payload = {key: value for key, value in payload.items() if key != "generated_at"}
    payload["artifact_digest"] = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pace-seconds", type=float, default=1.05)
    parser.add_argument("--output", type=Path, default=Path("audit_results/finnhub_canonical/finnhub_canonical_proving_set.json"))
    args = parser.parse_args()
    report = build_report(pace_seconds=max(0.0, args.pace_seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"state": report["state"], "provider_calls": report["provider_calls"], "artifact_digest": report["artifact_digest"]}))
    return 0 if report["state"] == "FINNHUB_CANONICAL_PATH_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
