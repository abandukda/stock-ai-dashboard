#!/usr/bin/env python3
"""Bounded preflight for a prospective full Finnhub Core credential.

This diagnostic never grants provider authority.  It verifies that three
families needed by the existing broad P/FCF certification are accessible for
a small, non-demo, cross-sector sample before the 152-symbol acquisition runs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Mapping

from scripts.finnhub_p_fcf_peer_certification import (
    ATLAS_INTEGRATION_FAILURE,
    CERTIFIED_DATA_AVAILABLE,
    CREDENTIAL_ENTITLEMENT_UNAVAILABLE,
    EXPECTED_DEMO_SYMBOL_RESTRICTION,
    PAID_CORE_BREADTH_UNTESTED,
    PROVIDER_CONTRACT_UNRESOLVED,
    PROVIDER_DATA_UNAVAILABLE,
    TARGETS,
    classify_provider_record,
)
from services.finnhub_shadow_provider import FinnhubShadowAdapter


VERSION = "ATLAS_FINNHUB_CORE_ENTITLEMENT_SMOKE_V2_DEMO_AWARE"
REQUIRED_CAPABILITIES = ("company_profile", "financial_statements", "basic_financials")
SMOKE_SAMPLE = {
    "ORCL": "Technology",
    "COST": "Consumer Defensive",
    "GM": "Consumer Cyclical",
    "AMGN": "Healthcare",
}
ENTITLEMENT_SMOKE_PASS = "ENTITLEMENT_SMOKE_PASS"
ENTITLEMENT_SMOKE_FAIL = "ENTITLEMENT_SMOKE_FAIL"


def _latest_fy(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    reports = [row for row in payload.get("reports") or () if isinstance(row, Mapping) and row.get("fiscal_period") == "FY"]
    return max(reports, key=lambda row: str(row.get("fiscal_date") or ""), default=None)


def _contract_complete(capability: str, record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    payload = record.get("payload") or {}
    provenance = record.get("provenance") or {}
    missing = [name for name in ("provider", "endpoint_or_source_family", "capture_timestamp", "raw_evidence_id") if not provenance.get(name)]
    if capability == "company_profile":
        missing.extend(name for name in ("name", "industry", "currency") if not payload.get(name))
    elif capability == "financial_statements":
        report = _latest_fy(payload)
        facts = (report or {}).get("canonical_facts") or {}
        if not report:
            missing.append("annual_filing_period")
        fcf = facts.get("free_cash_flow") or {}
        diluted = facts.get("weighted_average_shares_diluted") or {}
        if fcf.get("value") is None:
            missing.append("free_cash_flow")
        if not fcf.get("currency"):
            missing.append("free_cash_flow.currency")
        if diluted.get("value") is None:
            missing.append("weighted_average_shares_diluted")
        if diluted.get("normalized_unit") != "SHARES":
            missing.append("weighted_average_shares_diluted.normalized_unit")
    elif capability == "basic_financials":
        if payload.get("market_capitalization") is None:
            missing.append("market_capitalization")
        if not payload.get("market_capitalization_lineage"):
            missing.append("market_capitalization_lineage")
    return not missing, sorted(set(missing))


def build_smoke_report(adapter: Any, pace_seconds: float = 0.0) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    counts = {
        CERTIFIED_DATA_AVAILABLE: 0,
        CREDENTIAL_ENTITLEMENT_UNAVAILABLE: 0,
        EXPECTED_DEMO_SYMBOL_RESTRICTION: 0,
        PROVIDER_DATA_UNAVAILABLE: 0,
        PROVIDER_CONTRACT_UNRESOLVED: 0,
        ATLAS_INTEGRATION_FAILURE: 0,
    }
    for symbol, sector in SMOKE_SAMPLE.items():
        for capability in REQUIRED_CAPABILITIES:
            try:
                governed = adapter.fetch(capability, symbol).as_dict()
                classification = classify_provider_record(governed)
                complete, missing = _contract_complete(capability, governed)
                if classification == CERTIFIED_DATA_AVAILABLE and not complete:
                    classification = PROVIDER_CONTRACT_UNRESOLVED
                provenance = governed.get("provenance") or {}
                payload = governed.get("payload") or {}
                records.append({
                    "ticker": symbol,
                    "representative_sector": sector,
                    "capability": capability,
                    "classification": classification,
                    "provider_status": provenance.get("certification_status"),
                    "reason": payload.get("reason"),
                    "endpoint_or_source_family": provenance.get("endpoint_or_source_family"),
                    "evidence_id": provenance.get("raw_evidence_id"),
                    "capture_timestamp": provenance.get("capture_timestamp"),
                    "contract_missing": missing,
                })
            except Exception as exc:  # an adapter/runtime failure is not provider data absence
                classification = ATLAS_INTEGRATION_FAILURE
                records.append({
                    "ticker": symbol,
                    "representative_sector": sector,
                    "capability": capability,
                    "classification": classification,
                    "reason": type(exc).__name__,
                    "contract_missing": [],
                })
            counts[classification] += 1
            if pace_seconds:
                time.sleep(pace_seconds)

    if counts[EXPECTED_DEMO_SYMBOL_RESTRICTION]:
        state, failure = PAID_CORE_BREADTH_UNTESTED, EXPECTED_DEMO_SYMBOL_RESTRICTION
    elif counts[CREDENTIAL_ENTITLEMENT_UNAVAILABLE]:
        state, failure = ENTITLEMENT_SMOKE_FAIL, CREDENTIAL_ENTITLEMENT_UNAVAILABLE
    elif counts[PROVIDER_DATA_UNAVAILABLE]:
        state, failure = PROVIDER_DATA_UNAVAILABLE, PROVIDER_DATA_UNAVAILABLE
    elif counts[PROVIDER_CONTRACT_UNRESOLVED]:
        state, failure = PROVIDER_CONTRACT_UNRESOLVED, PROVIDER_CONTRACT_UNRESOLVED
    elif counts[ATLAS_INTEGRATION_FAILURE]:
        state, failure = ATLAS_INTEGRATION_FAILURE, ATLAS_INTEGRATION_FAILURE
    else:
        state, failure = ENTITLEMENT_SMOKE_PASS, None
    return {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "FULL_CORE_ENTITLEMENT_PREFLIGHT_ONLY",
        "grants_production_authority": False,
        "sample": [{"ticker": symbol, "sector": sector} for symbol, sector in SMOKE_SAMPLE.items()],
        "sample_is_disjoint_from_demo_targets": not bool(set(SMOKE_SAMPLE) & set(TARGETS)),
        "required_capabilities": list(REQUIRED_CAPABILITIES),
        "state": state,
        "failure_classification": failure,
        "counts": counts,
        "records": records,
    }


def exit_code(report: Mapping[str, Any]) -> int:
    return {
        ENTITLEMENT_SMOKE_PASS: 0,
        ENTITLEMENT_SMOKE_FAIL: 2,
        PAID_CORE_BREADTH_UNTESTED: 6,
        PROVIDER_DATA_UNAVAILABLE: 3,
        PROVIDER_CONTRACT_UNRESOLVED: 4,
        ATLAS_INTEGRATION_FAILURE: 5,
    }.get(str(report.get("state")), 5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="audit_results/finnhub_certification/finnhub_core_entitlement_smoke.json")
    parser.add_argument("--pace-seconds", type=float, default=1.05)
    args = parser.parse_args()
    report = build_smoke_report(FinnhubShadowAdapter(), max(0.0, args.pace_seconds))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"state": report["state"], "counts": report["counts"], "output": str(output)}, sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
