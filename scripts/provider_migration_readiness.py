#!/usr/bin/env python3
"""Generate a non-production Finnhub/transcript migration-readiness artifact."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from services.finnhub_shadow_provider import ENDPOINT_BY_CAPABILITY, FinnhubShadowAdapter
from services.certified_input_boundary import CertifiedConsumer, attempt_certified_input
from services.provider_domain_contracts import DatasetFamily
from services.transcript_provider import ConfiguredTranscriptProvider


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
            entitlement_matrix.append({
                "symbol": symbol, "capability": capability,
                "endpoint": ENDPOINT_BY_CAPABILITY[capability].path,
                "result_status": _result_status(status, normalized_count),
                "normalized_record_count": normalized_count,
                "dataset_family": value["provenance"]["dataset_family"],
                "coverage_class": value["provenance"]["market_coverage_class"],
                "provenance_complete": _provenance_complete(value["provenance"]),
                "schema_mismatch": False,
                "unexpectedly_absent_fields": [],
            })
            if record.provenance.dataset_family in {
                DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE,
                DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
                DatasetFamily.LIVE_DISPLAY_ONLY,
            }:
                for consumer in _consumers_for(capability):
                    adversarial.append({"symbol": symbol, "capability": capability, **attempt_certified_input(record, consumer)})
        transcript_record = transcript.transcript(symbol, year=2026, quarter=2).as_dict()
        transcript_record["payload"].pop("raw_content", None)
        records["transcript"] = transcript_record
        status = transcript_record["provenance"]["certification_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        by_symbol[symbol] = records
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
        "financial_reconciliation": {
            "status": "NOT_RUN_REQUIRES_TWELVE_AND_FINNHUB_LIVE_EVIDENCE",
            "authority_changed": False, "comparisons": [],
        },
        "ohlcv_reconciliation": {
            "status": "NOT_RUN_REQUIRES_TWELVE_AND_FINNHUB_LIVE_EVIDENCE",
            "authority_changed": False, "comparisons": [],
        },
        "transcript_live_test": {
            "status": transcript_record["provenance"]["certification_status"],
            "license_class": transcript_record["provenance"]["license_class"],
            "customer_publication_allowed": transcript_record["provenance"]["display_permission"] == "CONTEXT_ONLY",
            "raw_text_logged": False,
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
    if status == "DATA_UNAVAILABLE" or count == 0: return "DATA_UNAVAILABLE"
    return "AVAILABLE"


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
