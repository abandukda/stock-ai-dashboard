"""Build the immutable, provider-free G6 Stage 0 approval package."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from services.finnhub_canonical_authority import authority_contract
from services.finnhub_enterprise_display_contract import CONTRACT_ID, display_authority


EXPECTED_TICKERS = ("AVT", "BKTI", "CODA", "CSCO", "CTS", "DIOD", "EXTR", "GNE", "MSFT", "NVDA", "SBC")
ENDPOINT = "/stock/financials-reported"


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def build_stage0(reconciliation: Mapping[str, Any], *, agreement_sha256: str) -> dict[str, Any]:
    proposed = (reconciliation.get("g6_request") or {}).get("requests") or ()
    source = {str(row["ticker"]): row for row in proposed}
    if tuple(sorted(source)) != EXPECTED_TICKERS:
        raise ValueError("G6_STAGE0_TICKER_SCOPE_MISMATCH")
    authority = display_authority("financial_statements")
    canonical = authority_contract("financial_statements")
    if authority is None or authority.endpoint != ENDPOINT or canonical.get("state") != "CANONICAL_CERTIFIED":
        raise ValueError("G6_STAGE0_CONTRACT_AUTHORITY_UNPROVEN")
    requests = [{
        "ordinal": index + 1, "ticker": ticker, "method": "GET", "endpoint": ENDPOINT,
        "parameters": {"symbol": ticker, "freq": "annual"},
        "expected_history": {
            "contracted_financial_history": "UP_TO_30_YEARS",
            "requested_frequency": "ANNUAL",
            "minimum_useful_result": "At least 3 distinct annual periods where the issuer reports them",
            "quarterly_depth": "OUT_OF_SCOPE_FOR_THIS_ANNUAL_STAGE0_PILOT",
        },
        "target_fields": list(source[ticker].get("fields") or ()),
    } for index, ticker in enumerate(EXPECTED_TICKERS)]
    manifest = {
        "contract": "ATLAS_G6_STAGE0_FINANCIAL_HISTORY_V1",
        "state": "AWAITING_EXACT_OWNER_AUTHORIZATION",
        "provider_calls_performed": 0,
        "request_count": len(requests), "request_cap": 12, "requests": requests,
        "execution_policy": {
            "rate_limit_rpm": 60, "minimum_inter_request_seconds": 1.0,
            "concurrency": 1, "retry_count": 0, "fail_fast": True,
            "redirects": "PROVIDER_DEFAULT_ONLY", "scope_expansion": False,
        },
        "raw_persistence": {
            "required": True, "mode": "WRITE_ONCE_BEFORE_NORMALIZATION",
            "path_template": "<authorized-run-root>/raw/{ordinal:02d}-{ticker}-financials-reported.json",
            "per_response_sha256_required": True, "http_status_and_headers_required": True,
            "redact": ["request token", "authorization headers"],
            "retention": "CONTRACT_PERIOD_ONLY", "redistribution": "PROHIBITED",
        },
        "contract_evidence": {
            "signed_agreement_sha256": agreement_sha256,
            "signed_agreement_relevant_pages": [2, 9],
            "signed_terms": [
                "US Equity Financials: 30 years", "Appendix A includes /stock/financials-reported",
                "local storage permitted during contracted period", "raw machine-readable redistribution prohibited",
            ],
            "repository_contract_id": CONTRACT_ID,
            "repository_endpoint": authority.endpoint,
            "canonical_authority_state": canonical["state"],
        },
        "acceptance": {
            "same_ticker_response_required": True, "annual_periods_deduplicated": True,
            "values_must_retain_period_unit_provider_and_evidence_id": True,
            "empty_or_malformed_response": "FAIL_CLOSED_NO_RETRY",
            "methodology_change": False,
        },
    }
    digest = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    return {
        "manifest": manifest, "manifest_sha256": digest,
        "authorization_token": f"AUTHORIZE_G6_STAGE0:{digest}",
        "authorization_rule": "Execution is authorized only by an exact, case-sensitive match of authorization_token.",
    }


def write_stage0(package: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["ENDPOINT", "EXPECTED_TICKERS", "build_stage0", "canonical_bytes", "write_stage0"]
