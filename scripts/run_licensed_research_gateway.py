#!/usr/bin/env python3
"""Generic raw-first Finnhub acquisition for a verified gateway scope."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import requests

from services.operations_gateway import GatewayApproval, resolve_bounded_path, verify_scope


def run(*, approval_path: Path, scope_path: Path, output: Path, run_id: str) -> dict:
    approval = GatewayApproval.parse(json.loads(approval_path.read_text(encoding="utf-8")))
    if approval.operation != "acquire":
        raise PermissionError("RESEARCH_GATEWAY_ACQUIRE_TOKEN_REQUIRED")
    scope = verify_scope(scope_path, approval)
    api_key = os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        raise PermissionError("RESEARCH_GATEWAY_SECRET_REQUIRED")
    policy = scope.get("execution_policy") or {}
    rpm = int(policy.get("rate_limit_rpm", 0))
    if not 1 <= rpm <= 500 or int(policy.get("concurrency", 0)) != 1 or int(policy.get("retry_count", -1)) != 0:
        raise PermissionError("RESEARCH_GATEWAY_EXECUTION_POLICY_INVALID")
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"; raw.mkdir()
    session = requests.Session()
    session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1))
    telemetry = []
    last = 0.0
    for row in scope.get("requests") or ():
        delay = 60.0 / rpm - (time.monotonic() - last)
        if delay > 0: time.sleep(delay)
        started = time.monotonic(); last = started
        response = session.get("https://finnhub.io/api/v1" + row["endpoint"], params={**row["parameters"], "token": api_key}, timeout=30)
        body = response.content
        ticker = str(row.get("ticker") or row.get("parameters", {}).get("symbol") or "scope").upper()
        stem = f'{int(row["ordinal"]):05d}-{ticker}'
        body_path = raw / f"{stem}.json"; body_path.write_bytes(body)
        record = {"ordinal": row["ordinal"], "ticker": ticker, "endpoint": row["endpoint"],
                  "parameters": row["parameters"], "status_code": response.status_code,
                  "latency_ms": round((time.monotonic()-started)*1000,2),
                  "raw_sha256": hashlib.sha256(body).hexdigest(), "raw_bytes": len(body)}
        (raw/f"{stem}.metadata.json").write_text(json.dumps(record,sort_keys=True)+"\n",encoding="utf-8")
        telemetry.append(record)
        if response.status_code == 429: raise RuntimeError("RESEARCH_GATEWAY_RATE_LIMIT_STOP")
        if response.status_code in {401,403}: raise RuntimeError("RESEARCH_GATEWAY_ENTITLEMENT_STOP")
        if response.status_code != 200: raise RuntimeError(f"RESEARCH_GATEWAY_HTTP_STOP:{response.status_code}")
        try: payload=json.loads(body)
        except json.JSONDecodeError as exc: raise RuntimeError("RESEARCH_GATEWAY_SCHEMA_STOP") from exc
        if not isinstance(payload,(dict,list)): raise RuntimeError("RESEARCH_GATEWAY_SCHEMA_STOP")
    summary={"contract":"ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1","source_sha":approval.source_sha,
             "scope_sha256":approval.scope_sha256,"run_id":str(run_id),"provider_calls":len(telemetry),"telemetry":telemetry}
    (output/"run_summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser(); p.add_argument("--approval",type=Path,required=True); p.add_argument("--scope",type=Path,required=True); p.add_argument("--scope-root",type=Path); p.add_argument("--output",type=Path,required=True); p.add_argument("--run-id",required=True)
    a=p.parse_args(); scope=resolve_bounded_path(a.scope_root,str(a.scope)) if a.scope_root else a.scope
    run(approval_path=a.approval,scope_path=scope,output=a.output,run_id=a.run_id)


if __name__ == "__main__": main()
