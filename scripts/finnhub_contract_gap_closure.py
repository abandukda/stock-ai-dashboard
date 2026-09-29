#!/usr/bin/env python3
"""Bounded live evidence collector for the signed Finnhub contract families."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

from services.finnhub_contract_gap_governance import authority_state, estimate_bridge
from services.finnhub_shadow_provider import (
    ENDPOINT_BY_CAPABILITY, FINNHUB_ESTIMATE_CAPABILITIES, FinnhubShadowAdapter,
)


VERSION = "ATLAS_FINNHUB_CONTRACT_GAP_CLOSURE_V1"
SYMBOLS = ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA", "ORCL", "COST", "GM", "AMGN")
CAPABILITIES = tuple(ENDPOINT_BY_CAPABILITY)


def _params(capability: str, now: datetime) -> dict[str, Any]:
    if capability == "historical_ohlcv":
        return {"resolution": "D", "from": int(now.timestamp()) - 400 * 86400, "to": int(now.timestamp())}
    if capability == "historical_market_cap":
        return {"from": now.date().replace(year=now.year - 3).isoformat(), "to": now.date().isoformat()}
    if capability in FINNHUB_ESTIMATE_CAPABILITIES:
        return {"freq": "annual"}
    if capability in {"company_news", "press_releases"}:
        return {"from": now.date().replace(month=1, day=1).isoformat(), "to": now.date().isoformat()}
    return {}


def _classification(record: Mapping[str, Any]) -> str:
    status = str((record.get("provenance") or {}).get("certification_status") or "")
    if status == "UNVERIFIED_SHADOW": return "CERTIFIED_PROVIDER_CONTRACT"
    if status in {"DATA_UNAVAILABLE", "ENTITLEMENT_UNAVAILABLE"}: return "PROVIDER_DATA_UNAVAILABLE"
    return "ATLAS_INTEGRATION_FAILURE"


def quote_comparison(quote: Mapping[str, Any], quote_us: Mapping[str, Any]) -> str:
    if quote_us.get("status"): return "UNRESOLVED"
    keys = ("price", "open", "high", "low", "previous_close", "provider_timestamp")
    if all(quote.get(key) == quote_us.get(key) for key in keys): return "SEMANTICALLY_EQUIVALENT"
    if quote_us.get("coverage_metadata"): return "MORE_COMPLETE_US_QUOTE"
    return "DIFFERENT_CONTRACT"


def build_report(symbols: Sequence[str], *, pace_seconds: float = 0.0) -> dict[str, Any]:
    adapter = FinnhubShadowAdapter(); now = datetime.now(timezone.utc)
    records: dict[str, Any] = {}; matrix: list[dict[str, Any]] = []
    for symbol in symbols:
        profile_record = adapter.fetch("company_profile", symbol).as_dict()
        profile = profile_record.get("payload") or {}
        per_symbol = {"company_profile": profile_record}
        for capability in CAPABILITIES:
            if capability == "company_profile": continue
            record = adapter.fetch(capability, symbol, **_params(capability, now)).as_dict()
            per_symbol[capability] = record
            provenance = record.get("provenance") or {}; payload = record.get("payload") or {}
            semantic = None
            if capability in FINNHUB_ESTIMATE_CAPABILITIES:
                semantic = estimate_bridge(profile, payload, capability=capability,
                                           price_currency=profile.get("currency"))
            semantics_certified = bool(semantic and semantic.get("status") == "CERTIFIED_PROVIDER_CONTRACT")
            matrix.append({
                "symbol": symbol, "capability": capability,
                "endpoint": ENDPOINT_BY_CAPABILITY[capability].path,
                "live_classification": _classification(record),
                "provenance_complete": bool(provenance.get("raw_evidence_id") and provenance.get("capture_timestamp")),
                "evidence_id": provenance.get("raw_evidence_id"),
                "capture_timestamp": provenance.get("capture_timestamp"),
                "semantic_bridge": semantic,
                "authority_state": authority_state(
                    capability, live_status=provenance.get("certification_status"),
                    semantics_certified=semantics_certified,
                    provenance_complete=bool(provenance.get("raw_evidence_id")),
                ),
            })
            if pace_seconds: time.sleep(pace_seconds)
        per_symbol["quote_comparison"] = quote_comparison(
            (per_symbol["live_quote"].get("payload") or {}),
            (per_symbol["quote_us"].get("payload") or {}),
        )
        records[symbol] = per_symbol
    result = {
        "version": VERSION, "generated_at": now.isoformat(), "symbols": list(symbols),
        "records": records, "matrix": matrix,
        "provider_authority_changed": False, "production_cutover": False,
        "methodology_changed": False, "report_card_activated": False,
    }
    result["report_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("audit_results/finnhub_contract_gap/contract_gap_report.json"))
    parser.add_argument("--pace-seconds", type=float, default=0.1)
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_report(SYMBOLS, pace_seconds=args.pace_seconds), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__": raise SystemExit(main())
