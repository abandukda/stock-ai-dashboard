#!/usr/bin/env python3
"""Sanitize and classify one durable incremental provider response, offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def classify(record: Mapping[str, Any], *, session: str) -> dict[str, Any]:
    parameters = record.get("parameters") if isinstance(record.get("parameters"), Mapping) else {}
    payload = record.get("payload")
    status_code = record.get("status_code")
    iso_session_parameters = parameters.get("from") == session and parameters.get("to") == session
    if iso_session_parameters:
        cause = "INCORRECT_STOCK_CANDLE_DATE_PARAMETERS"
    elif status_code in (401, 403):
        cause = "ENTITLEMENT_OR_ENDPOINT_MISMATCH"
    elif status_code != 200:
        cause = "PROVIDER_HTTP_FAILURE"
    elif isinstance(payload, Mapping) and payload.get("error"):
        cause = "VALID_PROVIDER_ERROR_RESPONSE"
    elif isinstance(payload, Mapping) and payload.get("s") == "no_data":
        cause = "VALID_PROVIDER_NO_DATA_RESPONSE"
    elif not isinstance(payload, Mapping) or not isinstance(payload.get("t"), list):
        cause = "PROVIDER_RESPONSE_SCHEMA_MISMATCH"
    else:
        cause = "NORMALIZATION_OR_AVAILABILITY_CLASSIFICATION"
    sanitized_payload = payload
    if isinstance(payload, Mapping):
        sanitized_payload = {
            key: value for key, value in payload.items()
            if str(key).lower() not in {"token", "api_key", "apikey"}
        }
    result = {
        "diagnostic_version": "ATLAS_INCREMENTAL_FAILURE_DIAGNOSTIC_V1",
        "capability": record.get("capability"),
        "endpoint": record.get("endpoint"),
        "symbol": record.get("symbol"),
        "parameters": dict(parameters),
        "status_code": status_code,
        "payload": sanitized_payload,
        "classified_cause": cause,
        "provider_calls": 0,
        "production_writes": 0,
    }
    result["diagnostic_sha256"] = hashlib.sha256(
        (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--request-key", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_name = hashlib.sha256(args.request_key.encode()).hexdigest() + ".json"
    source = args.raw_root / raw_name
    record = json.loads(source.read_text(encoding="utf-8"))
    result = classify(record, session=args.session)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
