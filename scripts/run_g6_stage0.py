"""Exact, single-use G6 Stage 0 acquisition runner.

The runner is inert unless every frozen identity and authorization gate matches.
It performs requests sequentially, never retries, and persists raw bytes before
any JSON inspection. It does not normalize, publish, or alter ratings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

import requests

from scripts.build_g6_stage0_approval import canonical_bytes

EXPECTED_SOURCE_SHA = "3418d83dbf304b3fbe62805291f08025a90b22ac"
EXPECTED_MANIFEST_SHA = "3ca088a01a2fb220d08761df764ccacc3d605a217e510d599905864df0f3ea2b"
EXPECTED_TOKEN = f"AUTHORIZE_G6_STAGE0:{EXPECTED_MANIFEST_SHA}"
BASE_URL = "https://finnhub.io/api/v1"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify(package: dict[str, Any], *, source_sha: str, token: str) -> list[dict[str, Any]]:
    manifest = package.get("manifest") or {}
    digest = _sha256(canonical_bytes(manifest))
    if source_sha != EXPECTED_SOURCE_SHA:
        raise PermissionError("G6_SOURCE_SHA_MISMATCH")
    if digest != EXPECTED_MANIFEST_SHA or package.get("manifest_sha256") != EXPECTED_MANIFEST_SHA:
        raise PermissionError("G6_MANIFEST_SHA_MISMATCH")
    if token != EXPECTED_TOKEN or package.get("authorization_token") != EXPECTED_TOKEN:
        raise PermissionError("G6_AUTHORIZATION_TOKEN_MISMATCH")
    policy = manifest.get("execution_policy") or {}
    requests_scope = list(manifest.get("requests") or ())
    if manifest.get("request_count") != 11 or manifest.get("request_cap") != 12 or len(requests_scope) != 11:
        raise PermissionError("G6_REQUEST_COUNT_MISMATCH")
    if policy.get("rate_limit_rpm") != 60 or policy.get("concurrency") != 1 or policy.get("retry_count") != 0:
        raise PermissionError("G6_EXECUTION_POLICY_MISMATCH")
    for row in requests_scope:
        if row.get("method") != "GET" or row.get("endpoint") != "/stock/financials-reported":
            raise PermissionError("G6_ENDPOINT_MISMATCH")
        if row.get("parameters") != {"symbol": row.get("ticker"), "freq": "annual"}:
            raise PermissionError("G6_PARAMETER_MISMATCH")
    return requests_scope


def execute(package_path: Path, output_root: Path, *, source_sha: str, token: str, api_key: str) -> dict[str, Any]:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    scope = verify(package, source_sha=source_sha, token=token)
    if os.getenv("G6_EXECUTE") != "1" or not api_key:
        raise PermissionError("G6_PROTECTED_EXECUTION_ENVIRONMENT_REQUIRED")
    raw_dir = output_root / "raw"; raw_dir.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1)
    session.mount("https://", adapter)
    telemetry = []
    last_started = 0.0
    for row in scope:
        wait = 1.0 - (time.monotonic() - last_started)
        if wait > 0:
            time.sleep(wait)
        started = time.monotonic(); last_started = started
        response = session.get(
            BASE_URL + row["endpoint"], params={**row["parameters"], "token": api_key}, timeout=30,
        )
        body = response.content
        stem = f'{int(row["ordinal"]):02d}-{row["ticker"]}-financials-reported'
        raw_path = raw_dir / f"{stem}.json"
        raw_path.write_bytes(body)
        body_hash = _sha256(body)
        safe_headers = {
            key: value for key, value in response.headers.items()
            if key.lower() in {"content-type", "date", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"}
        }
        meta = {
            "ordinal": row["ordinal"], "ticker": row["ticker"], "endpoint": row["endpoint"],
            "parameters": row["parameters"], "status_code": response.status_code,
            "latency_ms": round((time.monotonic() - started) * 1000, 2),
            "raw_sha256": body_hash, "raw_bytes": len(body), "headers": safe_headers,
        }
        (raw_dir / f"{stem}.metadata.json").write_text(json.dumps(meta, sort_keys=True) + "\n", encoding="utf-8")
        telemetry.append(meta)
        if response.status_code != 200:
            raise RuntimeError(f'G6_HTTP_FAILURE:{row["ticker"]}:{response.status_code}')
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f'G6_MALFORMED_JSON:{row["ticker"]}') from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise RuntimeError(f'G6_RESPONSE_CONTRACT_FAILURE:{row["ticker"]}')
    summary = {
        "contract": "ATLAS_G6_STAGE0_RUN_V1", "source_sha": source_sha,
        "manifest_sha256": EXPECTED_MANIFEST_SHA, "request_count": len(telemetry),
        "provider_calls": len(telemetry), "telemetry": telemetry,
    }
    (output_root / "run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--authorization-token", required=True)
    args = parser.parse_args()
    execute(args.package, args.output_root, source_sha=args.source_sha,
            token=args.authorization_token, api_key=os.getenv("FINNHUB_API_KEY", ""))


if __name__ == "__main__":
    main()
