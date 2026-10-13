import hashlib
import json

import pytest

from scripts.build_g6_stage0_approval import ENDPOINT, EXPECTED_TICKERS, build_stage0, canonical_bytes


def _reconciliation():
    return {"g6_request": {"requests": [
        {"ticker": ticker, "endpoint_family": "financial_statements", "fields": ["latest_revenue"]}
        for ticker in EXPECTED_TICKERS
    ]}}


def test_stage0_is_exact_hash_bound_serial_and_non_retrying():
    package = build_stage0(_reconciliation(), agreement_sha256="a" * 64)
    manifest = package["manifest"]
    assert manifest["provider_calls_performed"] == 0
    assert manifest["request_count"] == 11 and manifest["request_cap"] == 12
    assert [row["ticker"] for row in manifest["requests"]] == list(EXPECTED_TICKERS)
    assert all(row["endpoint"] == ENDPOINT and row["parameters"]["freq"] == "annual" for row in manifest["requests"])
    assert manifest["execution_policy"] == {
        "rate_limit_rpm": 60, "minimum_inter_request_seconds": 1.0, "concurrency": 1,
        "retry_count": 0, "fail_fast": True, "redirects": "PROVIDER_DEFAULT_ONLY", "scope_expansion": False,
    }
    digest = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    assert package["manifest_sha256"] == digest
    assert package["authorization_token"] == f"AUTHORIZE_G6_STAGE0:{digest}"


def test_stage0_rejects_any_ticker_scope_change():
    changed = _reconciliation(); changed["g6_request"]["requests"].pop()
    with pytest.raises(ValueError, match="TICKER_SCOPE_MISMATCH"):
        build_stage0(changed, agreement_sha256="a" * 64)
