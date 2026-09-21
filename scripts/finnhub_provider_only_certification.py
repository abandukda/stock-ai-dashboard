#!/usr/bin/env python3
"""Bounded, shadow-only Finnhub/EarningsCall certification.

This diagnostic never imports a production acquisition adapter and never changes
provider authority. Unknown vendor semantics remain explicitly unresolved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import time
from typing import Any, Mapping, Sequence

from services.finnhub_shadow_provider import ENDPOINT_BY_CAPABILITY, FinnhubShadowAdapter
from services.transcript_provider import ConfiguredTranscriptProvider
from services.technical_intelligence.engine import _rsi, _sma, _true_ranges, _wilder_average, DailyBar


VERSION = "ATLAS_FINNHUB_PROVIDER_ONLY_CERTIFICATION_V2"
DEFAULT_SYMBOLS = ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA")
UNRESOLVED_METRICS = (
    "operatingMarginTTM", "grossMarginTTM", "netProfitMarginTTM", "ebitdaMarginTTM",
    "roeTTM", "roaTTM", "roicTTM", "revenueGrowthTTMYoy", "epsGrowthTTMYoy",
    "freeCashFlowGrowthTTMYoy", "payoutRatioTTM", "totalDebtToEquityTTM",
)


def _count(payload: Mapping[str, Any]) -> int:
    for value in payload.values():
        if isinstance(value, list):
            return len(value)
    return 0 if payload.get("status") else 1


def _bars(symbol: str, payload: Mapping[str, Any]) -> list[DailyBar]:
    cols = [payload.get(k) or [] for k in ("timestamps", "open", "high", "low", "close", "volume")]
    if not cols or len({len(x) for x in cols}) != 1:
        return []
    return [DailyBar(symbol, datetime.fromtimestamp(t, timezone.utc), float(o), float(h), float(l), float(c), float(v))
            for t, o, h, l, c, v in zip(*cols)]


def technical_recomputation(symbol: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    bars = _bars(symbol, payload)
    if len(bars) < 200:
        return {"status": "INSUFFICIENT_HISTORY", "bar_count": len(bars)}
    closes, volumes = [b.close for b in bars], [b.volume for b in bars]
    independent = {
        "sma20": statistics.fmean(closes[-20:]), "sma50": statistics.fmean(closes[-50:]),
        "sma200": statistics.fmean(closes[-200:]), "rsi14": _independent_rsi(closes),
        "atr14": _independent_atr(bars), "average_volume20": statistics.fmean(volumes[-20:]),
        "average_dollar_volume20": statistics.fmean(b.close * b.volume for b in bars[-20:]),
    }
    atlas = {
        "sma20": _sma(closes, 20), "sma50": _sma(closes, 50), "sma200": _sma(closes, 200),
        "rsi14": _rsi(closes), "atr14": _wilder_average(_true_ranges(bars), 14),
        "average_volume20": _sma(volumes, 20),
        "average_dollar_volume20": statistics.fmean(b.close * b.volume for b in bars[-20:]),
    }
    deltas = {k: abs(independent[k] - atlas[k]) for k in independent}
    return {"status": "MATCH" if max(deltas.values()) <= 1e-9 else "MISMATCH", "bar_count": len(bars),
            "independent": independent, "atlas": atlas, "absolute_deltas": deltas,
            "volume_certification": "VOLUME_SEMANTICS_UNRESOLVED"}


def _independent_rsi(values: Sequence[float], length: int = 14) -> float:
    changes = [b - a for a, b in zip(values, values[1:])]
    gains, losses = [max(x, 0.0) for x in changes], [max(-x, 0.0) for x in changes]
    gain, loss = statistics.fmean(gains[:length]), statistics.fmean(losses[:length])
    for g, l in zip(gains[length:], losses[length:]):
        gain, loss = ((length - 1) * gain + g) / length, ((length - 1) * loss + l) / length
    return 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)


def _independent_atr(bars: Sequence[DailyBar], length: int = 14) -> float:
    values = [bars[0].high - bars[0].low]
    values += [max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close)) for a, b in zip(bars, bars[1:])]
    result = statistics.fmean(values[:length])
    for value in values[length:]:
        result = ((length - 1) * result + value) / length
    return result


def safe_derivations(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    report = next((r for r in reports if r.get("fiscal_period") == "FY"), None)
    facts = (report or {}).get("canonical_facts") or {}
    out: dict[str, Any] = {}
    for name, numerator in (("gross_margin", "gross_profit"), ("operating_margin", "ebit"), ("net_margin", "net_income"),
                            ("fcf_margin", "free_cash_flow"), ("ebitda_margin", "ebitda")):
        top, revenue = facts.get(numerator), facts.get("revenue")
        if name == "gross_margin" and not top:
            cost = facts.get("cost_of_revenue")
            if cost and revenue and cost.get("period_end") == revenue.get("period_end") and cost.get("currency") == revenue.get("currency"):
                top = {**revenue, "value": float(revenue["value"]) - float(cost["value"]),
                       "source_field": "REVENUE_MINUS_COST_OF_REVENUE",
                       "source_record_version": revenue.get("source_record_version")}
        missing = not top or not revenue
        period_mismatch = bool(top and revenue and (
            top.get("period_end") != revenue.get("period_end") or top.get("currency") != revenue.get("currency")
        ))
        aligned = bool(not missing and not period_mismatch and float(revenue.get("value") or 0))
        classification = (
            "SAFE_DERIVED" if aligned else "SOURCE_FACT_MISSING" if missing else
            "PERIOD_MISMATCH" if period_mismatch else "SOURCE_FACT_MISSING"
        )
        out[name] = {
            "classification": classification,
            "value_percentage_points": (float(top["value"]) / float(revenue["value"]) * 100.0) if aligned else None,
            "numerator": numerator, "period_end": top.get("period_end") if top else None,
            "source_record_version": top.get("source_record_version") if top else None,
        }
    return out


def canonical_dry_run_v2(
    reports: Sequence[Mapping[str, Any]], derivations: Mapping[str, Any],
    bridge: Mapping[str, Any], technical: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe production-reachable readiness without manufacturing an Action.

    This deliberately does not execute Professional V2: the bounded shadow
    acquisition lacks the certified forward forecasts and capital assumptions
    those methods require.  It proves which inputs can safely cross the
    canonical boundary and which remain fail-closed.
    """
    report = next((r for r in reports if r.get("fiscal_period") == "FY"), None)
    facts = (report or {}).get("canonical_facts") or {}
    certified_fields = sorted(facts)
    safe_fields = sorted(name for name, value in derivations.items() if value.get("classification") == "SAFE_DERIVED")
    unresolved = list(UNRESOLVED_METRICS) + ["historical_volume_semantics"]
    valuation = {
        "VAL_FCFF_DCF_V1": "UNAVAILABLE_CERTIFIED_FORECAST_AND_CAPITAL_INPUTS_MISSING",
        "VAL_FORWARD_PE_V1": "UNAVAILABLE_CERTIFIED_FORWARD_EPS_AND_MULTIPLE_BASIS_MISSING",
        "VAL_EV_EBITDA_V1": (
            "UNAVAILABLE_CERTIFIED_PEER_MULTIPLE_BASIS_MISSING" if facts.get("ebitda") else
            "UNAVAILABLE_EXPLICIT_EBITDA_AND_PEER_MULTIPLE_BASIS_MISSING"
        ),
        "VAL_P_FCF_V1": "UNAVAILABLE_CERTIFIED_FORWARD_FCF_AND_MULTIPLE_BASIS_MISSING",
    }
    available_pillars = []
    if facts.get("revenue") and facts.get("net_income") and facts.get("free_cash_flow"):
        available_pillars.append("FUNDAMENTAL_QUALITY_PARTIAL")
    if technical.get("status") == "MATCH":
        available_pillars.extend(("TECHNICAL_QUALITY_EX_VOLUME", "ENTRY_TRADE_PLAN_EX_VOLUME"))
    blockers = [
        "NO_CERTIFIED_PROFESSIONAL_VALUATION_METHOD",
        "CERTIFIED_FORWARD_GROWTH_AND_ESTIMATE_INPUTS_UNAVAILABLE",
    ]
    if bridge.get("shares", {}).get("shares_outstanding", {}).get("classification") != "CERTIFIED_AVAILABLE":
        blockers.append("CURRENT_SHARE_BRIDGE_UNAVAILABLE")
    return {
        "status": "FAIL_CLOSED",
        "certified_financial_fields": certified_fields,
        "safe_derived_fields": safe_fields,
        "unresolved_fields_excluded": unresolved,
        "available_pillars": available_pillars,
        "unavailable_or_partial_pillars": ["VOLUME_QUALITY_UNAVAILABLE", "VALUATION_OPPORTUNITY_UNAVAILABLE"],
        "valuation_methods": valuation,
        "opportunity": None,
        "decision_confidence": None,
        "certified_action": False,
        "blockers": blockers,
        "volume_effect": "FAIL_CLOSED_AS_UNAVAILABLE; OTHER_AVAILABLE_PILLARS_RENORMALIZE_UNDER_EXISTING_RULES",
    }


def financial_bridges(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    report = next((r for r in reports if r.get("fiscal_period") == "FY"), None)
    facts = (report or {}).get("canonical_facts") or {}
    shares = {}
    for canonical in ("shares_outstanding", "weighted_average_shares_basic", "weighted_average_shares_diluted"):
        fact = facts.get(canonical)
        shares[canonical] = {
            "classification": "CERTIFIED_AVAILABLE" if fact and fact.get("normalized_unit") == "SHARES" else "SOURCE_FACT_MISSING",
            "value": fact.get("value") if fact else None,
            "source_field": fact.get("source_field") if fact else None,
            "period_end": fact.get("period_end") if fact else None,
            "source_record_version": fact.get("source_record_version") if fact else None,
        }
    debt = facts.get("total_debt")
    return {"shares": shares, "debt": {
        "classification": "CERTIFIED_AVAILABLE" if debt and debt.get("normalized_unit") else "SOURCE_FACT_MISSING",
        "value": debt.get("value") if debt else None,
        "source_fields": debt.get("source_fields") if debt else [],
        "period_end": debt.get("period_end") if debt else None,
        "unit": debt.get("normalized_unit") if debt else None,
        "source_record_version": debt.get("source_record_version") if debt else None,
    }}


def build_report(symbols: Sequence[str], *, sample_count: int = 3, sample_interval: float = 2.0) -> dict[str, Any]:
    adapter, transcript = FinnhubShadowAdapter(), ConfiguredTranscriptProvider()
    matrix, technical, derivations, bridges, records, live, transcripts = [], {}, {}, {}, {}, [], {}
    now = datetime.now(timezone.utc)
    start = int((now.timestamp() - 400 * 86400)); end = int(now.timestamp())
    for symbol in symbols:
        by_cap = {}
        for capability in ENDPOINT_BY_CAPABILITY:
            params = {"resolution": "D", "from": start, "to": end} if capability == "historical_ohlcv" else {}
            if capability == "company_news": params = {"from": now.date().replace(month=1, day=1).isoformat(), "to": now.date().isoformat()}
            record = adapter.fetch(capability, symbol, **params)
            value = record.as_dict(); by_cap[capability] = value
            matrix.append({"symbol": symbol, "capability": capability,
                           "endpoint": ENDPOINT_BY_CAPABILITY[capability].path,
                           "status": value["provenance"]["certification_status"],
                           "record_count": _count(value["payload"]),
                           "provenance_complete": bool(value["provenance"].get("raw_evidence_id")),
                           "use": "LIVE_DISPLAY_ONLY" if capability == "live_quote" else
                                  "CONTEXTUAL_ONLY" if value["provenance"]["dataset_family"] != "CANONICAL_QUANTITATIVE" else
                                  "SHADOW_PENDING_CERTIFICATION"})
        records[symbol] = by_cap
        reports = by_cap["financial_statements"]["payload"].get("reports") or []
        derivations[symbol] = safe_derivations(reports)
        bridges[symbol] = financial_bridges(reports)
        technical[symbol] = technical_recomputation(symbol, by_cap["historical_ohlcv"]["payload"])
        evidence = transcript.transcript(symbol, year=now.year, quarter=((now.month - 1) // 3 or 1))
        transcripts[symbol] = {"status": evidence.provenance.certification_status.value,
                               "provider": evidence.provenance.provider,
                               "license": evidence.provenance.license_class,
                               "evidence_id": evidence.provenance.raw_evidence_id,
                               "content_hash": evidence.provenance.content_hash,
                               "metadata": {k: evidence.payload.get(k) for k in
                                            ("company", "call_date", "provider_transcript_id", "speaker_metadata",
                                             "prepared_sections", "qa_segments", "source_record_version")}}
    for index in range(sample_count):
        for symbol in symbols[:3]:
            quote = adapter.fetch("live_quote", symbol).as_dict()
            live.append({"sample": index + 1, "symbol": symbol, "captured_at": datetime.now(timezone.utc).isoformat(),
                         "price": quote["payload"].get("price"), "provider_timestamp": quote["payload"].get("provider_timestamp"),
                         "coverage": quote["provenance"]["market_coverage_class"],
                         "dataset_family": quote["provenance"]["dataset_family"],
                         "evidence_id": quote["provenance"].get("raw_evidence_id"),
                         "certified_input_allowed": False})
        if index + 1 < sample_count: time.sleep(sample_interval)
    unit_matrix = [{"source_field": field, "source_unit": "UNIT_UNRESOLVED", "canonical_unit": None,
                    "conversion": None, "certified_scoring_allowed": False} for field in UNRESOLVED_METRICS]
    dry_run = {
        symbol: canonical_dry_run_v2(
            records[symbol]["financial_statements"]["payload"].get("reports") or [],
            derivations[symbol], bridges[symbol], technical[symbol],
        ) for symbol in symbols
    }
    blockers = ["NO_REPRESENTATIVE_ISSUER_WITH_CERTIFIED_ACTION", "CERTIFIED_FORWARD_VALUATION_INPUTS_UNAVAILABLE"]
    return {"version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "FINNHUB_ONLY_SHADOW_CERTIFICATION", "production_authority_changed": False,
            "discontinued_provider_calls": 0, "symbols": list(symbols), "capability_matrix": matrix,
            "unit_matrix": unit_matrix, "safe_derivations": derivations, "technical_recomputation": technical,
            "financial_bridges": bridges,
            "ohlcv_contract": {"daily_price_adjustment": "SPLIT_ADJUSTED_DOCUMENTED",
                               "intraday_price_adjustment": "UNADJUSTED_DOCUMENTED",
                               "dividend_adjustment": "UNKNOWN", "volume_adjustment": "UNKNOWN",
                               "volume_certification": "VOLUME_SEMANTICS_UNRESOLVED"},
            "market_hours_samples": live, "transcripts": transcripts,
            "canonical_dry_run": dry_run,
            "verdict": "FAIL", "blockers": blockers, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--output", default="audit_results/finnhub_certification/finnhub_provider_certification.json")
    args = parser.parse_args(); symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    report = build_report(symbols); path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("version", "generated_at", "verdict", "blockers")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
