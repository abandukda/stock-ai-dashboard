"""Build deterministic, approval-gated Finnhub financial-history batches.

This module is deliberately provider-free.  It creates review manifests only;
it cannot execute HTTP requests and does not accept an API key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

ENDPOINT = "/stock/financials-reported"
METHOD = "GET"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def published_tickers(records: Iterable[dict[str, Any]]) -> list[str]:
    """Return the exact governed publication scope, rejecting bad identity."""
    tickers = []
    for record in records:
        cert = record.get("publication_certification") or {}
        if cert.get("customer_publication_allowed") is not True:
            continue
        ticker = str(record.get("ticker") or "").strip().upper()
        if not ticker or ticker != str(cert.get("ticker") or "").strip().upper():
            raise ValueError("PUBLISHED_TICKER_IDENTITY_INVALID")
        tickers.append(ticker)
    if len(tickers) != len(set(tickers)):
        raise ValueError("PUBLISHED_TICKER_DUPLICATE")
    return sorted(tickers)


def request_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    params = row["parameters"]
    return row["method"], row["endpoint"], params["symbol"], params["freq"]


def stage0_keys(package: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    return {request_key(row) for row in package["manifest"]["requests"]}


def build_plan(
    tickers: list[str], policy: dict[str, Any], gateway: dict[str, Any],
    stage0_package: dict[str, Any], *, scope_sha256: str,
) -> dict[str, Any]:
    expected = policy["published_scope"]["expected_count"]
    if len(tickers) != expected:
        raise ValueError(f"PUBLISHED_SCOPE_COUNT_MISMATCH:{len(tickers)}:{expected}")
    expected_scope_hash = policy["published_scope"]["ticker_scope_sha256"]
    if digest(tickers) != expected_scope_hash:
        raise ValueError("PUBLISHED_TICKER_SCOPE_HASH_MISMATCH")
    if gateway.get("contract") != "ATLAS_FINNHUB_FINANCIALS_GATEWAY_V1":
        raise ValueError("GATEWAY_CONTRACT_MISMATCH")
    pacing = gateway["pacing"]
    if pacing != {"concurrency": 1, "minimum_inter_request_seconds": 1.0,
                   "rate_limit_rpm": 60, "retry_count": 0}:
        raise ValueError("GATEWAY_PACING_DRIFT")
    prior = stage0_keys(stage0_package)
    rows = []
    for ticker in tickers:
        for freq in policy["requested_frequencies"]:
            row = {"method": METHOD, "endpoint": ENDPOINT,
                   "parameters": {"symbol": ticker, "freq": freq}, "ticker": ticker}
            if request_key(row) not in prior:
                rows.append(row)
    keys = [request_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("EXPANSION_REQUEST_DUPLICATE")

    size = int(policy["batch_size"])
    batches = []
    for offset in range(0, len(rows), size):
        requests = rows[offset:offset + size]
        number = len(batches) + 1
        body = {
            "contract": "ATLAS_G6_EXPANSION_BATCH_V1",
            "batch_id": f"B{number:03d}",
            "gateway_contract_sha256": digest(gateway),
            "published_scope_sha256": scope_sha256,
            "request_cap": size,
            "request_count": len(requests),
            "requests": [{"ordinal": i + 1, **row} for i, row in enumerate(requests)],
            "state": "AWAITING_EXACT_OWNER_AUTHORIZATION"
        }
        batch_hash = digest(body)
        batches.append({
            "manifest": body,
            "manifest_sha256": batch_hash,
            "required_authorization_token": f"AUTHORIZE_G6_EXPANSION_BATCH:B{number:03d}:{batch_hash}"
        })
    return {
        "contract": policy["contract"],
        "state": "PLANNING_ONLY_NO_PROVIDER_CALLS",
        "provider_calls_performed": 0,
        "source": {"published_count": len(tickers), "published_scope_sha256": scope_sha256},
        "coverage": {
            "target_symbol_frequency_pairs": len(tickers) * len(policy["requested_frequencies"]),
            "stage0_pairs_deduplicated": len(prior),
            "expansion_request_count": len(rows),
            "frequencies": policy["requested_frequencies"]
        },
        "gateway_contract_sha256": digest(gateway),
        "batch_count": len(batches),
        "batches": batches,
        "authorization_note": "Stage 0 authorization does not authorize any expansion batch."
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--published-records", type=Path, required=True)
    parser.add_argument("--published-records-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("config/g6_enterprise_expansion_policy.json"))
    parser.add_argument("--gateway", type=Path, default=Path("config/finnhub_financials_gateway_v1.json"))
    parser.add_argument("--stage0", type=Path, default=Path("output/joint/r2_reconciliation/g6_stage0_approval.json"))
    args = parser.parse_args()
    raw = args.published_records.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != args.published_records_sha256:
        raise SystemExit("PUBLISHED_SCOPE_ARTIFACT_HASH_MISMATCH")
    records = json.loads(raw)
    plan = build_plan(published_tickers(records), json.loads(args.policy.read_text()),
                      json.loads(args.gateway.read_text()), json.loads(args.stage0.read_text()),
                      scope_sha256=actual)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
