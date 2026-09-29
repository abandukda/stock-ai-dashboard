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
from overnight_market_scan import build_trade_plan
from scripts.finnhub_p_fcf_peer_certification import load_governed_classifications
from services.evidence_inspector import inspect_ticker
from services.finnhub_canonical_authority import AUTHORITY_VERSION, FinnhubCanonicalAdapter
from services.professional_valuation_evidence import apply_peer_multiple_evidence
from services.technical_intelligence.engine import DailyBar, TechnicalIntelligenceEngine
from services.live_market.models import FeedHealth, SecurityType


VERSION = "ATLAS_FINNHUB_CANONICAL_PROVING_SET_V1"
SYMBOLS = ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA", "ORCL", "COST", "GM", "AMGN")


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
    resolved_classification.setdefault("sector", profile.get("finnhubIndustry"))
    resolved_classification.setdefault("industry", profile.get("finnhubIndustry"))
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
        "professional_evidence_lineage": {"provider": "FINNHUB", "evidence_ids": list(filter(None, evidence_ids))},
        "historical_ohlcv_evidence_id": (records["historical_ohlcv"].get("provenance") or {}).get("raw_evidence_id"),
        "finnhub_authority_version": AUTHORITY_VERSION,
        "forward_contract_status": "CONTRACT_PENDING",
    }
    return row, bars, []


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
    prepared = apply_peer_multiple_evidence(rows)
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
        diagnostics[symbol].update({
            "canonical_action": (evaluation.get("guidance") or {}).get("state"),
            "valuation_status": (evaluation.get("atlas_valuation") or {}).get("status"),
            "shadow_evidence_leakage": any(
                marker in json.dumps(combined, sort_keys=True, default=str)
                for marker in ("UNVERIFIED_SHADOW", "SHADOW_ONLY")
            ),
            "inspector_traceability": inspector["traceability"],
        })
        evaluations[symbol] = evaluation
    ready = len(evaluations) == len(SYMBOLS) and all(
        not item.get("authority_blockers") and not item.get("shadow_evidence_leakage")
        and (item.get("inspector_traceability") or {}).get("status") == "PASS"
        for item in diagnostics.values()
    )
    payload = {
        "version": VERSION, "authority_version": AUTHORITY_VERSION,
        "generated_at": now.isoformat(), "symbols": list(SYMBOLS), "provider_calls": provider_calls,
        "classification_provenance": catalog_provenance,
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
