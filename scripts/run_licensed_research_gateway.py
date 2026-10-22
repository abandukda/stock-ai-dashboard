#!/usr/bin/env python3
"""Generic raw-first Finnhub acquisition for a verified gateway scope.

Raw capture is bounded. A partial body is explicitly incomplete and cannot carry
an authoritative raw_sha256. Redirects and retries never expand the approved GET
budget. Transport exceptions are never serialized because their URL may include
credentials. A local terminal receipt records attempted calls even on failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import requests

from services.operations_gateway import GatewayApproval, resolve_bounded_path, verify_scope

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
RESPONSE_CHUNK_BYTES = 64 * 1024


class _GatewayStop(RuntimeError):
    """Internal allowlisted failure code only, never a provider exception."""


def _capture(response) -> tuple[bytes, bool, str | None]:
    body = bytearray()
    try:
        for chunk in response.iter_content(chunk_size=RESPONSE_CHUNK_BYTES):
            if not chunk:
                continue
            remaining = MAX_RESPONSE_BYTES - len(body)
            if len(chunk) > remaining:
                body.extend(chunk[:remaining])
                return bytes(body), False, "RESEARCH_GATEWAY_RESPONSE_SIZE_STOP"
            body.extend(chunk)
    except requests.RequestException:
        return bytes(body), False, "RESEARCH_GATEWAY_TRANSPORT_STOP"
    except Exception:
        return bytes(body), False, "RESEARCH_GATEWAY_EXECUTION_STOP"
    return bytes(body), True, None


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    # Never overwrite another execution's evidence directory.
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    telemetry = []
    attempted_calls = 0
    session = None
    failure_code = None
    last = 0.0
    try:
        session = requests.Session()
        session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1))
        for index, row in enumerate(scope.get("requests") or (), 1):
            if api_key in json.dumps(row, sort_keys=True):
                raise _GatewayStop("RESEARCH_GATEWAY_SCOPE_CREDENTIAL_STOP")
            parameters = dict(row["parameters"])
            delay = 60.0 / rpm - (time.monotonic() - last)
            if delay > 0:
                time.sleep(delay)
            started = time.monotonic()
            last = started
            # Scope labels are never used as filesystem components.
            stem = f"{index:05d}"
            record = {"ordinal": row["ordinal"], "ticker": str(row.get("ticker") or parameters.get("symbol") or "scope").upper(),
                      "endpoint": row["endpoint"], "parameters": parameters,
                      "status_code": None, "attempt_count": 1, "retry_count": 0,
                      "raw_complete": False, "raw_sha256": None, "raw_bytes": 0,
                      "status": "ATTEMPTING", "raw_capture": "NO_RESPONSE"}
            telemetry.append(record)
            response = None
            stop_code = None
            try:
                attempted_calls += 1
                response = session.get("https://finnhub.io/api/v1" + row["endpoint"],
                                       params={**parameters, "token": api_key}, timeout=30,
                                       allow_redirects=False, stream=True)
                record["status_code"] = int(response.status_code)
                body, complete, capture_stop = _capture(response)
                # Never persist an echoed API credential, even in an error body.
                if api_key.encode("utf-8") in body:
                    record["raw_capture"] = "REJECTED_CREDENTIAL_ECHO"
                    raise _GatewayStop("RESEARCH_GATEWAY_CREDENTIAL_ECHO_STOP")
                suffix = ".json" if complete else ".incomplete"
                body_path = raw / (stem + suffix)
                body_path.write_bytes(body)
                record.update({"raw_file": body_path.name, "raw_complete": complete,
                               "raw_bytes": len(body), "raw_capture": "COMPLETE" if complete else ("INCOMPLETE_SIZE_LIMIT" if capture_stop == "RESEARCH_GATEWAY_RESPONSE_SIZE_STOP" else "INCOMPLETE_STREAM_FAILURE")})
                if complete:
                    record["raw_sha256"] = hashlib.sha256(body).hexdigest()
                else:
                    record["raw_prefix_sha256"] = hashlib.sha256(body).hexdigest()
                    raise _GatewayStop(capture_stop or "RESEARCH_GATEWAY_EXECUTION_STOP")
                if response.status_code == 429:
                    raise _GatewayStop("RESEARCH_GATEWAY_RATE_LIMIT_STOP")
                if response.status_code in {401, 403}:
                    raise _GatewayStop("RESEARCH_GATEWAY_ENTITLEMENT_STOP")
                if 300 <= response.status_code < 400:
                    raise _GatewayStop("RESEARCH_GATEWAY_REDIRECT_STOP")
                if response.status_code != 200:
                    raise _GatewayStop(f"RESEARCH_GATEWAY_HTTP_STOP:{response.status_code}")
                try:
                    payload = json.loads(body)
                except (ValueError, UnicodeError):
                    raise _GatewayStop("RESEARCH_GATEWAY_SCHEMA_STOP") from None
                if not isinstance(payload, (dict, list)):
                    raise _GatewayStop("RESEARCH_GATEWAY_SCHEMA_STOP")
            except _GatewayStop as exc:
                stop_code = str(exc)
            except requests.RequestException:
                stop_code = "RESEARCH_GATEWAY_TRANSPORT_STOP"
            except Exception:
                stop_code = "RESEARCH_GATEWAY_EXECUTION_STOP"
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        stop_code = stop_code or "RESEARCH_GATEWAY_RESPONSE_CLOSE_STOP"
                record["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
                record["status"] = "FAIL" if stop_code else "PASS"
                if stop_code:
                    record["failure_code"] = stop_code
                _write_json(raw / f"{stem}.metadata.json", record)
            if stop_code:
                raise _GatewayStop(stop_code)
    except _GatewayStop as exc:
        failure_code = str(exc)
    except Exception:
        failure_code = "RESEARCH_GATEWAY_EXECUTION_STOP"
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                failure_code = failure_code or "RESEARCH_GATEWAY_SESSION_CLOSE_STOP"
    summary = {"contract": "ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1", "source_sha": approval.source_sha,
               "scope_sha256": approval.scope_sha256, "run_id": str(run_id),
               "status": "FAIL" if failure_code else "PASS", "failure_code": failure_code,
               "max_provider_calls": approval.max_provider_calls,
               "provider_calls": attempted_calls, "attempted_transport_calls": attempted_calls,
               "call_count_semantics": "CLIENT_GET_ATTEMPTS_NOT_SERVER_ACKNOWLEDGEMENTS",
               "responses_received": sum(row["status_code"] is not None for row in telemetry),
               "automatic_redirects": False, "retry_count": 0,
               "max_response_bytes": MAX_RESPONSE_BYTES, "telemetry": telemetry}
    try:
        _write_json(output / "run_summary.json", summary)
    except Exception:
        raise RuntimeError("RESEARCH_GATEWAY_RECEIPT_WRITE_STOP") from None
    if failure_code:
        raise RuntimeError(failure_code) from None
    return summary


def main():
    p=argparse.ArgumentParser(); p.add_argument("--approval",type=Path,required=True); p.add_argument("--scope",type=Path,required=True); p.add_argument("--scope-root",type=Path); p.add_argument("--output",type=Path,required=True); p.add_argument("--run-id",required=True)
    a=p.parse_args(); scope=resolve_bounded_path(a.scope_root,str(a.scope)) if a.scope_root else a.scope
    run(approval_path=a.approval,scope_path=scope,output=a.output,run_id=a.run_id)


if __name__ == "__main__": main()
