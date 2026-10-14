#!/usr/bin/env python3
"""Exact-manifest, raw-first WS3 acquisition runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable

import requests

from scripts.plan_g6_enterprise_expansion import digest

CONTRACT = "ATLAS_WS3_HUMAN_APPROVAL_PACKAGE_V1"
ALLOWED_ENDPOINT = "/stock/financials-reported"
MAX_CALLS = 25


def _manifest(package: dict[str, Any]) -> dict[str, Any]:
    requests = [
        {"ordinal": i + 1, "dataset": package["dataset"], "method": package["request_method"],
         "endpoint": package["endpoint"], "ticker": ticker,
         "parameters": {"symbol": ticker, "freq": package["frequency"]},
         "refresh_hours": package["refresh_hours"]}
        for i, ticker in enumerate(package["tickers"])
    ]
    return {"contract": "ATLAS_WS3_IMMUTABLE_BATCH_V1", "batch_id": package["batch_id"],
            "membership_artifact_sha256": package["membership_artifact_sha256"],
            "request_cap": package["request_cap"], "request_count": package["request_count"],
            "requests": requests, "pacing": package["pacing"], "state": package["state"]}


def validate_package(package: dict[str, Any], authorization_token: str, source_sha: str) -> dict[str, Any]:
    if package.get("contract") != CONTRACT or package.get("state") != "AWAITING_EXACT_OWNER_AUTHORIZATION":
        raise PermissionError("WS3_PACKAGE_CONTRACT_INVALID")
    if package.get("source_commit_sha") != source_sha:
        raise PermissionError("WS3_SOURCE_SHA_MISMATCH")
    if authorization_token != package.get("required_authorization_token"):
        raise PermissionError("WS3_AUTHORIZATION_TOKEN_MISMATCH")
    if package.get("provider_calls_performed") != 0:
        raise PermissionError("WS3_PACKAGE_ALREADY_EXECUTED")
    pacing = package.get("pacing") or {}
    if pacing != {"concurrency": 1, "minimum_inter_request_seconds": 1.0, "rate_limit_rpm": 60, "retry_count": 0}:
        raise PermissionError("WS3_PACING_POLICY_INVALID")
    requests = _manifest(package)["requests"]
    if package.get("request_cap") != MAX_CALLS or package.get("request_count") != len(requests) or len(requests) > MAX_CALLS:
        raise PermissionError("WS3_REQUEST_CAP_INVALID")
    keys = []
    for ordinal, row in enumerate(requests, 1):
        if row["ordinal"] != ordinal or row["method"] != "GET" or row["endpoint"] != ALLOWED_ENDPOINT:
            raise PermissionError("WS3_REQUEST_CONTRACT_INVALID")
        if row["parameters"] != {"symbol": row["ticker"], "freq": "annual"} or "token" in row["parameters"]:
            raise PermissionError("WS3_REQUEST_PARAMETERS_INVALID")
        keys.append((row["endpoint"], row["ticker"], row["parameters"]["freq"]))
    if len(keys) != len(set(keys)):
        raise PermissionError("WS3_DUPLICATE_REQUEST")
    manifest = _manifest(package)
    if digest(manifest) != package.get("immutable_batch_manifest_sha256"):
        raise PermissionError("WS3_MANIFEST_DIGEST_MISMATCH")
    expected = f"AUTHORIZE_WS3_BATCH:{package['batch_id']}:{package['immutable_batch_manifest_sha256']}"
    if authorization_token != expected:
        raise PermissionError("WS3_AUTHORIZATION_IDENTITY_MISMATCH")
    return manifest


def _persist(path: Path, body: bytes) -> str:
    with path.open("xb") as handle:
        handle.write(body); handle.flush(); os.fsync(handle.fileno())
    return hashlib.sha256(body).hexdigest()


def run(*, package_path: Path, output: Path, authorization_token: str, source_sha: str,
        session: Any | None = None, sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    manifest = validate_package(package, authorization_token, source_sha)
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        raise PermissionError("WS3_PROVIDER_SECRET_REQUIRED")
    output.mkdir(parents=True, exist_ok=False); raw = output / "raw"; raw.mkdir()
    client = session or requests.Session()
    if session is None:
        client.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1))
    telemetry=[]; last=None
    for row in manifest["requests"]:
        if last is not None:
            delay=max(0.0, manifest["pacing"]["minimum_inter_request_seconds"]-(monotonic()-last))
            if delay: sleep(delay)
        started=monotonic(); last=started
        response=client.get("https://finnhub.io/api/v1"+row["endpoint"],params={**row["parameters"],"token":api_key},timeout=30)
        body=response.content; stem=f"{row['ordinal']:05d}-{row['ticker']}"; body_path=raw/f"{stem}.json"
        raw_sha=_persist(body_path,body)
        record={"ordinal":row["ordinal"],"ticker":row["ticker"],"endpoint":row["endpoint"],"parameters":row["parameters"],
                "status_code":response.status_code,"raw_sha256":raw_sha,"raw_bytes":len(body),"latency_ms":round((monotonic()-started)*1000,2)}
        (raw/f"{stem}.metadata.json").write_text(json.dumps(record,sort_keys=True)+"\n",encoding="utf-8");telemetry.append(record)
        if response.status_code==429:raise RuntimeError("WS3_HTTP_429_STOP")
        if response.status_code in {401,403}:raise RuntimeError("WS3_AUTH_OR_ENTITLEMENT_STOP")
        if response.status_code!=200:raise RuntimeError(f"WS3_HTTP_STOP:{response.status_code}")
        try: payload=json.loads(body)
        except json.JSONDecodeError as exc:raise RuntimeError("WS3_SCHEMA_STOP") from exc
        if not isinstance(payload,dict):raise RuntimeError("WS3_SCHEMA_STOP")
    summary={"contract":"ATLAS_WS3_BATCH_RUN_V1","batch_id":manifest["batch_id"],"source_commit_sha":source_sha,
             "manifest_sha256":package["immutable_batch_manifest_sha256"],"provider_calls":len(telemetry),"retry_count":0,"telemetry":telemetry}
    (output/"run_summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return summary


def main() -> None:
    p=argparse.ArgumentParser();p.add_argument("--package",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--authorization-token",required=True);p.add_argument("--source-sha",required=True);a=p.parse_args()
    run(package_path=a.package,output=a.output,authorization_token=a.authorization_token,source_sha=a.source_sha)


if __name__=="__main__":main()
