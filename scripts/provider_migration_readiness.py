#!/usr/bin/env python3
"""Generate a non-production Finnhub/transcript migration-readiness artifact."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

import requests

from services.finnhub_shadow_provider import ENDPOINT_BY_CAPABILITY, FinnhubShadowAdapter
from services.certified_input_boundary import CertifiedConsumer, attempt_certified_input
from services.provider_domain_contracts import DatasetFamily
from services.provider_reconciliation import ReconciliationTolerance, compare_scalar, reconcile_ohlcv
from services.transcript_provider import ConfiguredTranscriptProvider, build_transcript_derived_insight
from services.twelve_data_trial_intelligence import acquire_twelve_trial_dossiers, normalize_trial_dossier
from services.live_market.twelve_data_phase1 import TwelveDataPhase1Adapter


DEFAULT_CAPABILITIES = (
    "company_profile", "financial_statements", "basic_financials", "dividends", "peers",
    "ownership", "insider_transactions", "executives", "company_news", "sec_filings",
    "revenue_breakdown", "recommendations", "price_targets", "analyst_actions",
    "eps_estimates", "revenue_estimates", "ebitda_estimates", "ebit_estimates",
    "earnings_calendar", "historical_ohlcv", "live_quote", "splits",
)


def build_report(symbols: list[str]) -> dict:
    finnhub = FinnhubShadowAdapter()
    transcript = ConfiguredTranscriptProvider()
    by_symbol = {}
    entitlement_matrix = []
    adversarial = []
    status_counts = {}
    finnhub_records = {}
    transcript_results = {}
    for symbol in symbols:
        records = {}
        for capability in DEFAULT_CAPABILITIES:
            params = {}
            if capability == "company_news": params = {"from": "2026-01-01", "to": "2026-12-31"}
            elif capability == "historical_ohlcv": params = {"resolution": "D", "from": 1735689600, "to": 1789689600}
            record = finnhub.fetch(capability, symbol, **params)
            value = record.as_dict()
            records[capability] = value
            status = value["provenance"]["certification_status"]
            status_counts[status] = status_counts.get(status, 0) + 1
            normalized_count = _record_count(record.payload)
            semantic_status = _result_status(status, normalized_count)
            entitlement_matrix.append({
                "symbol": symbol, "capability": capability,
                "endpoint": ENDPOINT_BY_CAPABILITY[capability].path,
                "result_status": semantic_status,
                "normalized_record_count": normalized_count,
                "dataset_family": value["provenance"]["dataset_family"],
                "coverage_class": value["provenance"]["market_coverage_class"],
                "provenance_complete": _provenance_complete(value["provenance"]),
                "schema_mismatch": semantic_status == "SCHEMA_MISMATCH",
                "unexpectedly_absent_fields": _unexpectedly_absent(capability, record.payload),
            })
            if record.provenance.dataset_family in {
                DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE,
                DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
                DatasetFamily.LIVE_DISPLAY_ONLY,
            }:
                for consumer in _consumers_for(capability):
                    adversarial.append({"symbol": symbol, "capability": capability, **attempt_certified_input(record, consumer)})
        finnhub_records[symbol] = records
        transcript_evidence = transcript.transcript(symbol, year=2026, quarter=2)
        transcript_record = transcript_evidence.as_dict()
        transcript_record["payload"].pop("raw_content", None)
        transcript_results[symbol] = {
            "evidence": transcript_record,
            "derived": _derived_transcript_artifact(transcript_evidence),
        }
        records["transcript"] = transcript_record
        status = transcript_record["provenance"]["certification_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        by_symbol[symbol] = records
    financial_reconciliation = _financial_reconciliation(symbols, finnhub_records)
    ohlcv_reconciliation = _ohlcv_reconciliation(symbols, finnhub_records)
    unavailable = status_counts.get("DATA_UNAVAILABLE", 0) + status_counts.get("ENTITLEMENT_UNAVAILABLE", 0)
    total = sum(status_counts.values())
    return {
        "version": "ATLAS_PROVIDER_MIGRATION_READINESS_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_DEMO_MIGRATION_VALIDATION",
        "production_authority_changed": False,
        "finnhub_credential_available": bool(os.getenv("FINNHUB_API_KEY", "").strip()),
        "transcript_credential_available": bool(os.getenv("ATLAS_TRANSCRIPT_API_KEY", "").strip()),
        "capability_count": len(ENDPOINT_BY_CAPABILITY),
        "status_counts": status_counts,
        "classification": "SHADOW_READY" if total and unavailable < total else "NOT_READY",
        "entitlement_matrix": entitlement_matrix,
        "adversarial_boundary": {
            "attempt_count": len(adversarial),
            "rejected_count": sum(not item["accepted"] for item in adversarial),
            "passed": bool(adversarial) and all(not item["accepted"] for item in adversarial),
            "attempts": adversarial,
        },
        "live_vs_eod_proof": {
            "market_hours_observed": False,
            "status": "INCOMPLETE_REQUIRES_MARKET_HOURS_LIVE_EVIDENCE",
            "trust_tier_separation_enforced": True,
            "authority_changed": False,
        },
        "financial_reconciliation": financial_reconciliation,
        "ohlcv_reconciliation": ohlcv_reconciliation,
        "transcript_live_test": {
            "status": transcript_record["provenance"]["certification_status"],
            "license_class": transcript_record["provenance"]["license_class"],
            "customer_publication_allowed": transcript_record["provenance"]["display_permission"] == "CONTEXT_ONLY",
            "raw_text_logged": False, "symbols": transcript_results,
        },
        "records": by_symbol,
    }


def _record_count(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    for value in payload.values():
        if isinstance(value, list):
            return len(value)
    return 0 if payload.get("status") else 1


def _result_status(status: str, count: int) -> str:
    if status == "ENTITLEMENT_UNAVAILABLE": return "ENTITLEMENT_UNAVAILABLE"
    if status == "DATA_UNAVAILABLE": return "DATA_UNAVAILABLE"
    if count == 0: return "AVAILABLE_EMPTY"
    return "AVAILABLE_POPULATED"


EXPECTED_FIELDS = {
    "company_profile": ("name", "exchange"), "live_quote": ("price",),
    "historical_ohlcv": ("timestamps", "close", "volume"),
    "financial_statements": ("reports",), "splits": ("corporate_actions",),
}


def _unexpectedly_absent(capability: str, payload: Mapping[str, Any]) -> list[str]:
    return [name for name in EXPECTED_FIELDS.get(capability, ()) if name not in payload]


def _derived_transcript_artifact(evidence) -> dict[str, Any] | None:
    if "raw_content_hash" not in evidence.payload:
        return None
    derived = build_transcript_derived_insight(
        evidence,
        {"evidence_summary": f"Transcript retrieved for {evidence.payload.get('resolved_period') or evidence.provenance.effective_period}.",
         "raw_content_hash": evidence.payload["raw_content_hash"], "non_scoring": True},
        model_provider="DETERMINISTIC", model_version="NO_GENERATIVE_MODEL", prompt_version="P1_EVIDENCE_REFERENCE_V1",
    ).as_dict()
    derived["payload"].pop("raw_content", None)
    return derived


FINANCIAL_FIELDS = (
    "revenue", "ebit", "ebitda", "net_income", "cash", "total_debt",
    "operating_cash_flow", "capex", "free_cash_flow", "shares_outstanding", "market_cap",
)
TWELVE_FIELD = {
    "revenue": "latest_revenue", "ebit": "ebit", "ebitda": "forward_ebitda",
    "net_income": "net_income", "cash": "cash_and_equivalents", "total_debt": "total_debt",
    "operating_cash_flow": "operating_cash_flow", "capex": "capital_expenditures",
    "free_cash_flow": "free_cash_flow", "shares_outstanding": "current_shares_outstanding", "market_cap": "market_cap",
}


def _financial_reconciliation(symbols: list[str], finnhub_records: Mapping[str, Any]) -> dict[str, Any]:
    env = {**os.environ, "ATLAS_DATA_MODE": "INTERNAL_TRIAL"}
    acquired = acquire_twelve_trial_dossiers(
        symbols, get=requests.get, environ=env, max_workers=1,
        endpoints=("statistics", "income_statement", "balance_sheet", "cash_flow"),
    )
    comparisons = []
    dossiers = acquired.get("dossiers") or {}
    for symbol in symbols:
        twelve = normalize_trial_dossier({"ticker": symbol}, dossiers.get(symbol) or {})
        reports = (((finnhub_records.get(symbol) or {}).get("financial_statements") or {}).get("payload") or {}).get("reports") or []
        report = reports[0] if reports else {}
        facts = report.get("canonical_facts") or {}
        metrics = (((finnhub_records.get(symbol) or {}).get("basic_financials") or {}).get("payload") or {})
        for field in FINANCIAL_FIELDS:
            shadow = facts.get(field) or {}
            finnhub_value = shadow.get("value")
            if field == "market_cap": finnhub_value = metrics.get("market_capitalization")
            result = compare_scalar(twelve.get(TWELVE_FIELD[field]), finnhub_value, tolerance=ReconciliationTolerance(relative_pct=2.0))
            twelve_period = twelve.get(f"{TWELVE_FIELD[field]}_period")
            period_aligned = not (twelve_period and shadow.get("period_end") and str(twelve_period) != str(shadow.get("period_end")))
            classification = result["status"] if period_aligned else "UNRESOLVED"
            comparisons.append({
                "ticker": symbol, "canonical_period": shadow.get("canonical_period"),
                "period_end_date": shadow.get("period_end"), "twelve_period": twelve_period, "field": field,
                "twelve_value": result.get("left"), "finnhub_value": result.get("right"),
                "normalized_units": shadow.get("normalized_unit"),
                "absolute_difference": result.get("absolute_delta"), "percentage_difference": result.get("relative_delta_pct"),
                "classification": classification,
                "likely_reason": "PERIOD_MISMATCH" if not period_aligned else "PERIOD_OR_BASIS_REQUIRES_REVIEW" if result["status"] == "MATERIAL_MISMATCH" else None,
                "methodology_impact": classification in {"MATERIAL_MISMATCH", "UNRESOLVED"},
                "finnhub_lineage": shadow,
            })
    return {"status": "COMPLETED" if acquired.get("status") == "AVAILABLE" else acquired.get("status"),
            "provider_calls": acquired.get("provider_calls", 0), "authority_changed": False, "comparisons": comparisons}


def _ohlcv_reconciliation(symbols: list[str], finnhub_records: Mapping[str, Any]) -> dict[str, Any]:
    key = os.getenv("TWELVE_DATA_API_KEY", "").strip()
    if not key:
        return {"status": "DATA_UNAVAILABLE", "reason": "TWELVE_DATA_API_KEY_UNAVAILABLE", "authority_changed": False, "comparisons": []}
    adapter = TwelveDataPhase1Adapter(key, enabled=True, get=requests.get)
    output = []
    for symbol in symbols:
        try:
            raw = adapter.fetch_time_series(symbol, interval="1day", outputsize=90, prepost=False)
            twelve = _twelve_bars(raw)
        except Exception as exc:
            output.append({"ticker": symbol, "status": "DATA_UNAVAILABLE", "reason": type(exc).__name__})
            continue
        payload = (((finnhub_records.get(symbol) or {}).get("historical_ohlcv") or {}).get("payload") or {})
        finnhub = _finnhub_bars(payload)
        result = reconcile_ohlcv(twelve, finnhub)
        result.update({"ticker": symbol, "status": "COMPLETED", "twelve_adjustment": "splits",
                       "finnhub_adjustment": payload.get("adjustment_mode"), "coverage_certified": False})
        output.append(result)
    return {"status": "COMPLETED" if all(x.get("status") == "COMPLETED" for x in output) else "PARTIAL",
            "authority_changed": False, "comparisons": output}


def _twelve_bars(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"date": str(row.get("datetime") or "")[:10], **{k: row.get(k) for k in ("open", "high", "low", "close", "volume")}}
            for row in (payload.get("values") or []) if isinstance(row, Mapping)]


def _finnhub_bars(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = ("timestamps", "open", "high", "low", "close", "volume")
    values = [payload.get(key) or [] for key in keys]
    count = min(map(len, values), default=0)
    return [{"date": datetime.fromtimestamp(values[0][i], tz=timezone.utc).date().isoformat(),
             **{key: values[j][i] for j, key in enumerate(keys[1:], 1)}} for i in range(count)]


def _provenance_complete(p: dict) -> bool:
    return all(p.get(name) for name in (
        "provider", "dataset_family", "endpoint_or_source_family", "symbol",
        "canonical_security_id", "capture_timestamp", "raw_evidence_id",
        "adapter_version", "canonical_schema_version",
    ))


def _consumers_for(capability: str) -> tuple[CertifiedConsumer, ...]:
    if capability == "price_targets": return (CertifiedConsumer.VALUATION,)
    if capability == "recommendations": return (CertifiedConsumer.ACTION,)
    if capability == "analyst_actions": return (CertifiedConsumer.SIX_PILLAR,)
    if capability == "company_news": return (CertifiedConsumer.OPPORTUNITY,)
    if capability in {"ownership", "insider_transactions"}: return (CertifiedConsumer.VALUATION,)
    if capability == "live_quote":
        return tuple(consumer for consumer in CertifiedConsumer if consumer in {
            CertifiedConsumer.RVOL, CertifiedConsumer.VOLUME_QUALITY, CertifiedConsumer.LIQUIDITY_GATE,
            CertifiedConsumer.BREAKOUT_CONFIRMATION, CertifiedConsumer.TECHNICAL_SCORE,
            CertifiedConsumer.BUY_NOW_CERTIFICATION,
        })
    return ()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="AAPL,MSFT,NVDA")
    parser.add_argument("--output", default="audit_results/provider_shadow/provider_migration_readiness.json")
    args = parser.parse_args()
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    report = build_report(symbols)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("version", "mode", "status_counts", "classification")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
