"""Build the provider-free G6 Enterprise Research expansion proposal.

This module only plans requests from the retained gap inventory.  It never
contacts Finnhub and it never changes certified investment authority.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


FREQUENCIES = ("annual", "quarterly")
ENDPOINTS = {
    "reported_financials": "/stock/financials-reported",
    "standardized_financials": "/stock/financials",
    "basic_financials": "/stock/metric",
    "eps_estimates": "/stock/eps-estimate",
    "ebitda_estimates": "/stock/ebitda-estimate",
}


def _sha(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


def build_plan(rows: list[dict[str, str]], *, batch_size: int = 100) -> dict:
    published = [r for r in rows if r.get("customer_published") == "True"]
    tickers = sorted({r["ticker"] for r in published})
    families = {(r["ticker"], r["endpoint_family"]) for r in published}

    requests: set[tuple[str, str, str]] = set()
    for ticker in tickers:
        # Both representations are acquired for reconciliation, not silently
        # substituted for one another.  Annual and quarterly are distinct.
        for frequency in FREQUENCIES:
            requests.add((ticker, "reported_financials", frequency))
            requests.add((ticker, "standardized_financials", frequency))
        if (ticker, "basic_financials") in families:
            requests.add((ticker, "basic_financials", "all"))
        if (ticker, "eps_estimates") in families:
            for frequency in FREQUENCIES:
                requests.add((ticker, "eps_estimates", frequency))
        if (ticker, "ebitda_estimates") in families:
            for frequency in FREQUENCIES:
                requests.add((ticker, "ebitda_estimates", frequency))

    ordered = sorted(requests)
    by_endpoint = Counter(family for _, family, _ in ordered)
    batch_counts = []
    for index in range(0, len(tickers), batch_size):
        batch_tickers = set(tickers[index:index + batch_size])
        batch_requests = [r for r in ordered if r[0] in batch_tickers]
        batch_counts.append({
            "batch": index // batch_size + 1,
            "ticker_count": len(batch_tickers),
            "request_count": len(batch_requests),
            "ticker_first": min(batch_tickers),
            "ticker_last": max(batch_tickers),
            "scope_sha256": _sha("|".join(r) for r in batch_requests),
        })

    pilot_tickers = sorted({r["ticker"] for r in published if r.get("publishable_buy_now") == "True"})
    pilot = [(ticker, "reported_financials", "annual") for ticker in pilot_tickers]
    return {
        "contract": "ATLAS_G6_ENTERPRISE_RESEARCH_EXPANSION_V1",
        "status": "PROPOSED_NOT_AUTHORIZED",
        "provider_calls": 0,
        "contractual_rights": {
            "basis": "OWNER_CONFIRMED_SIGNED_AGREEMENT_2026_09_23",
            "potentially_unlimited_subject_to_reasonable_use": True,
            "explicit_numeric_rpm": None,
            "history_years": 30,
            "commercial_website_mobile_display": True,
            "raw_api_redistribution": False,
        },
        "observed_behavior": {
            "status": "UNOBSERVED_FOR_THIS_SCOPE",
            "rate_limit_headers": None,
            "sustainable_rpm": None,
            "schema_conformance": None,
        },
        "engineering_controls": {
            "initial_rpm": 60,
            "implementation_ceiling_rpm": 500,
            "concurrency": 1,
            "automatic_retry": False,
            "adaptive_rule": "Increase only after clean batches; decrease on latency or rate-limit signals; halt on first HTTP 429 during initial acquisition.",
        },
        "source_gap_inventory": {
            "published_tickers": len(tickers),
            "deduplicated_ticker_family_gaps": len(families),
            "scope_sha256": _sha(f"{t}|{f}" for t, f in families),
        },
        "stage_0_response_validation": {
            "description": "Original BUY NOW annual reported-financial pilot retained as a response/schema validation stage, not a contractual maximum.",
            "ticker_count": len(pilot_tickers),
            "request_count": len(pilot),
            "operational_cap": 12,
            "scope_sha256": _sha("|".join(r) for r in pilot),
        },
        "expanded_scope": {
            "request_count": len(ordered),
            "request_count_by_endpoint": dict(sorted(by_endpoint.items())),
            "scope_sha256": _sha("|".join(r) for r in ordered),
            "batch_size": batch_size,
            "batches": batch_counts,
        },
        "refresh_policy": {
            "reported_and_standardized_financials": "Event-driven after a new filing; monthly stale-check only.",
            "estimates": "Weekly and after earnings; skip when source snapshot is unchanged.",
            "basic_financials": "Weekly for published securities; content-hash deduplication.",
            "immutable_raw_store": "Content-addressed response bytes plus endpoint, parameters, acquisition time, HTTP metadata, entitlement identity and SHA-256.",
        },
        "stop_conditions": [
            "HTTP 401 or 403 entitlement/authentication response",
            "First HTTP 429 during initial validation or any exhausted approved retry allowance later",
            "Unexpected response schema or missing identity/period/unit fields",
            "Reported and standardized values disagree outside registered tolerance",
            "Currency, fiscal-period or ticker identity mismatch",
            "Planned request differs from the owner-approved scope hash",
            "Raw response cannot be durably persisted and hash-verified before normalization",
        ],
        "authority_boundary": "New evidence is research context only until separately governed reevaluation and publication approval.",
    }


def main() -> None:
    source = Path("output/joint/r2_reconciliation/g6_missing_cells.csv")
    rows = list(csv.DictReader(source.open(encoding="utf-8")))
    plan = build_plan(rows)
    target = source.with_name("g6_enterprise_expansion_plan.json")
    target.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
