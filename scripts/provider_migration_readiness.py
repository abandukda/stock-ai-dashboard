#!/usr/bin/env python3
"""Generate a non-production Finnhub/transcript migration-readiness artifact."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from services.finnhub_shadow_provider import ENDPOINT_BY_CAPABILITY, FinnhubShadowAdapter
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
        transcript_record = transcript.transcript(symbol, year=2026, quarter=2).as_dict()
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
        "records": by_symbol,
    }


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
