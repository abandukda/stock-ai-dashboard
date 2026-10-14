"""Single-use, approval-gated G6 quarterly statement acquisition.

This module is inert unless every frozen identity, protected-environment, and
owner authorization gate matches. Requests are serial and never retried.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

import requests


EXPECTED_EVIDENCE_SOURCE_SHA = "220865a70214781db8a87d1b90a11cf0e4a50cdd"
EXPECTED_MANIFEST_SHA = "c0ddabaa766cb50b165f1703d84dd2374ca144645f598366bbf32d9d77cc3121"
EXPECTED_APPROVAL_SHA = "ff08750d2d12c8cd18dfcb3cd75fd548df4c01613dc125c448ee48992384a5bb"
EXPECTED_TOKEN = f"AUTHORIZE_G6_QUARTERLY:{EXPECTED_MANIFEST_SHA}"
EXPECTED_TICKERS = ("AVT", "BKTI", "CODA", "CSCO", "CTS", "DIOD", "EXTR", "GNE", "MSFT", "NVDA", "SBC")
BASE_URL = "https://finnhub.io/api/v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest_without_embedded_sha(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes({key: item for key, item in value.items() if key != "sha256"})).hexdigest()


def verify(approval: dict[str, Any], manifest: dict[str, Any], *, evidence_source_sha: str, token: str) -> tuple[str, ...]:
    if evidence_source_sha != EXPECTED_EVIDENCE_SOURCE_SHA:
        raise PermissionError("G6_QUARTERLY_EVIDENCE_SOURCE_SHA_MISMATCH")
    if manifest.get("sha256") != EXPECTED_MANIFEST_SHA or _digest_without_embedded_sha(manifest) != EXPECTED_MANIFEST_SHA:
        raise PermissionError("G6_QUARTERLY_MANIFEST_SHA_MISMATCH")
    if approval.get("sha256") != EXPECTED_APPROVAL_SHA or _digest_without_embedded_sha(approval) != EXPECTED_APPROVAL_SHA:
        raise PermissionError("G6_QUARTERLY_APPROVAL_SHA_MISMATCH")
    if approval.get("request_manifest_sha256") != EXPECTED_MANIFEST_SHA or token != EXPECTED_TOKEN:
        raise PermissionError("G6_QUARTERLY_AUTHORIZATION_TOKEN_MISMATCH")
    if approval.get("execution_authorized") is not False or manifest.get("execution_authorized") is not False:
        raise PermissionError("G6_QUARTERLY_INERT_PACKAGE_REQUIRED")

    request = approval.get("request_contract") or {}
    rate = approval.get("rate_contract") or {}
    symbols = tuple(request.get("symbol_order") or ())
    manifest_symbols = tuple((manifest.get("batches") or [{}])[0].get("symbols") or ())
    if symbols != EXPECTED_TICKERS or manifest_symbols != EXPECTED_TICKERS:
        raise PermissionError("G6_QUARTERLY_SYMBOL_ALLOWLIST_MISMATCH")
    if approval.get("request_count") != 11 or len(symbols) != 11:
        raise PermissionError("G6_QUARTERLY_REQUEST_COUNT_MISMATCH")
    if request != {
        "method": "GET",
        "endpoint": "/stock/financials-reported",
        "parameters": {"symbol": "<EXACT_MANIFEST_SYMBOL>", "freq": "quarterly"},
        "symbol_order": list(EXPECTED_TICKERS),
    }:
        raise PermissionError("G6_QUARTERLY_ENDPOINT_PARAMETER_SCOPE_MISMATCH")
    required_rate = {
        "scope": "SINGLE_GLOBAL_ACCOUNT_LEVEL_LIMITER",
        "requests_per_minute": 500,
        "burst_requests_per_second_ceiling": 20,
        "workers": 1,
        "original_request_ceiling": 11,
        "automatic_retry_ceiling_per_request": 0,
        "absolute_provider_attempt_ceiling": 11,
        "retry_policy": "NO_AUTOMATIC_RETRIES",
    }
    if rate != required_rate:
        raise PermissionError("G6_QUARTERLY_ZERO_RETRY_RATE_CONTRACT_MISMATCH")
    return symbols


def execute(
    approval_path: Path,
    manifest_path: Path,
    output_root: Path,
    *,
    evidence_source_sha: str,
    execution_sha: str,
    token: str,
    api_key: str,
) -> dict[str, Any]:
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    symbols = verify(approval, manifest, evidence_source_sha=evidence_source_sha, token=token)
    if os.getenv("G6_QUARTERLY_EXECUTE") != "1" or not api_key or not execution_sha:
        raise PermissionError("G6_QUARTERLY_PROTECTED_EXECUTION_ENVIRONMENT_REQUIRED")

    raw_dir = output_root / "raw"
    raw_dir.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1))
    telemetry: list[dict[str, Any]] = []
    last_started = 0.0
    for ordinal, ticker in enumerate(symbols, 1):
        wait = 0.12 - (time.monotonic() - last_started)
        if wait > 0:
            time.sleep(wait)
        requested_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        last_started = started
        response = session.get(
            BASE_URL + "/stock/financials-reported",
            params={"symbol": ticker, "freq": "quarterly", "token": api_key},
            timeout=30,
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        body = response.content
        stem = f"{ordinal:02d}-{ticker}-financials-reported"
        raw_path = raw_dir / f"{stem}.json"
        raw_path.write_bytes(body)
        safe_headers = {
            key: value for key, value in response.headers.items()
            if key.lower() in {"content-type", "date", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"}
        }
        metadata = {
            "endpoint": "/stock/financials-reported",
            "parameters": {"symbol": ticker, "freq": "quarterly"},
            "ticker": ticker,
            "status_code": response.status_code,
            "response_headers": safe_headers,
            "raw_bytes": len(body),
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "requested_at": requested_at,
            "completed_at": completed_at,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "attempt_count": 1,
            "retry_count": 0,
        }
        (raw_dir / f"{stem}.metadata.json").write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")
        telemetry.append(metadata)
        if response.status_code != 200:
            raise RuntimeError(f"G6_QUARTERLY_HTTP_FAILURE:{ticker}:{response.status_code}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"G6_QUARTERLY_MALFORMED_JSON:{ticker}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise RuntimeError(f"G6_QUARTERLY_RESPONSE_CONTRACT_FAILURE:{ticker}")

    summary = {
        "contract": "ATLAS_G6_QUARTERLY_RUN_V1",
        "execution_sha": execution_sha,
        "evidence_source_sha": evidence_source_sha,
        "manifest_sha256": EXPECTED_MANIFEST_SHA,
        "approval_sha256": EXPECTED_APPROVAL_SHA,
        "request_count": 11,
        "provider_calls": 11,
        "retry_count": 0,
        "tickers": list(symbols),
        "telemetry": telemetry,
    }
    (output_root / "run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence-source-sha", required=True)
    parser.add_argument("--execution-sha", required=True)
    parser.add_argument("--authorization-token", required=True)
    args = parser.parse_args()
    execute(
        args.approval,
        args.manifest,
        args.output_root,
        evidence_source_sha=args.evidence_source_sha,
        execution_sha=args.execution_sha,
        token=args.authorization_token,
        api_key=os.getenv("FINNHUB_API_KEY", ""),
    )


if __name__ == "__main__":
    main()
