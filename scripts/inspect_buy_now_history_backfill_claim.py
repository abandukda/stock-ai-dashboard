#!/usr/bin/env python3
"""Sanitized, provider-free inspection of one durable backfill claim."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.buy_now_history_backfill_execution import digest, file_sha256


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _shape(envelope: dict) -> dict:
    result = {
        "http_status": int(envelope.get("status_code", 0)),
        "content_type": str((envelope.get("headers") or {}).get("content-type", "")),
        "raw_body_sha256": str(envelope.get("body_sha256", "")),
    }
    try:
        body = json.loads(base64.b64decode(str(envelope["body_base64"])))
    except Exception:
        return {**result, "classification": "INVALID_OR_NON_JSON_BODY"}
    if not isinstance(body, dict):
        return {**result, "classification": "NON_OBJECT_CANDLE_BODY", "body_type": type(body).__name__}
    status = body.get("s")
    arrays = {k: len(body[k]) if isinstance(body.get(k), list) else None for k in ("c", "h", "l", "o", "t", "v")}
    if status == "no_data": classification = "FINNHUB_NO_DATA"
    elif status != "ok": classification = "UNRECOGNIZED_CANDLE_STATUS"
    elif any(v is None for v in arrays.values()): classification = "CANDLE_ARRAY_MISSING"
    elif len(set(arrays.values())) != 1: classification = "CANDLE_ARRAY_LENGTH_MISMATCH"
    elif not arrays["t"]: classification = "CANDLE_ARRAY_EMPTY"
    elif any(v is None for v in body["v"]): classification = "CANDLE_VOLUME_MISSING"
    else: classification = "CANDLE_SHAPE_VALID"
    return {**result, "classification": classification, "provider_status": status,
            "array_lengths": arrays, "keys": sorted(body)}


def inspect(*, package: Path, state_root: Path, raw_root: Path, claim_id: str,
            expected_claim_scope: str) -> dict:
    package_value = _json(package); plan = package_value["backfill_plan"]
    claim_dir = state_root / "history_backfill_claims" / claim_id
    raw_dir = raw_root / "history_backfill" / claim_id
    claim_path = claim_dir / "claim.json"
    claim = _json(claim_path)
    scope = claim.get("scope") or {}
    if scope.get("claim_id") != claim_id or scope.get("claim_scope_sha256") != expected_claim_scope:
        raise PermissionError("BACKFILL_FORENSIC_CLAIM_SCOPE_MISMATCH")
    if scope.get("plan_sha256") != plan.get("plan_sha256"):
        raise PermissionError("BACKFILL_FORENSIC_PLAN_MISMATCH")
    requests = {int(row["ordinal"]): row for row in plan["requests"]}
    intents = {int(p.stem): p for p in (claim_dir / "intents").glob("*.json")}
    envelopes = {int(p.stem): p for p in raw_dir.glob("*.json")}
    receipts = {int(p.stem): p for p in (claim_dir / "receipts").glob("*.json")}
    for ordinal, path in intents.items():
        if ordinal not in requests or _json(path).get("request_sha256") != digest(requests[ordinal]):
            raise RuntimeError(f"BACKFILL_FORENSIC_INTENT_INVALID:{ordinal}")
    for ordinal, path in envelopes.items():
        if ordinal not in requests or _json(path).get("request_sha256") != digest(requests[ordinal]):
            raise RuntimeError(f"BACKFILL_FORENSIC_ENVELOPE_INVALID:{ordinal}")
    for ordinal, path in receipts.items():
        receipt = _json(path)
        if ordinal not in envelopes or receipt.get("request_sha256") != digest(requests[ordinal]):
            raise RuntimeError(f"BACKFILL_FORENSIC_RECEIPT_INVALID:{ordinal}")
        if receipt.get("envelope_sha256") != file_sha256(envelopes[ordinal]):
            raise RuntimeError(f"BACKFILL_FORENSIC_RECEIPT_DIGEST_INVALID:{ordinal}")
    failed = sorted(set(envelopes) - set(receipts))
    indeterminate = sorted(set(intents) - set(envelopes))
    first = failed[0] if failed else (indeterminate[0] if indeterminate else None)
    request = requests.get(first) if first else None
    failure = None
    if first:
        failure = {"ordinal": first, "ticker": request["ticker"], "endpoint": request["endpoint"],
                   "parameters": {k: v for k, v in request["parameters"].items() if k != "token"},
                   "intent_sha256": file_sha256(intents[first]) if first in intents else None,
                   "envelope_sha256": file_sha256(envelopes[first]) if first in envelopes else None,
                   "response_shape": _shape(_json(envelopes[first])) if first in envelopes else {"classification":"INDETERMINATE_NO_ENVELOPE"}}
    manifest = lambda rows: hashlib.sha256("".join(f"{n}:{file_sha256(rows[n])}\n" for n in sorted(rows)).encode()).hexdigest()
    return {
        "schema_version": "atlas.backfill-claim-forensics.v1", "provider_calls": 0,
        "publication_writes": 0, "report_card_mutations": 0,
        "claim_id": claim_id, "claim_state": claim.get("state"), "execution_id": claim.get("execution_id"),
        "claim_scope_sha256": expected_claim_scope, "authorized_requests": len(requests),
        "durable_intents": len(intents), "raw_envelopes": len(envelopes),
        "completed_receipts": len(receipts), "indeterminate_requests": len(indeterminate),
        "failed_response_requests": len(failed), "not_attempted": len(requests) - len(intents),
        "remaining_authorized_budget": 0, "unattempted_scope_is_not_new_authority": True,
        "intent_manifest_sha256": manifest(intents), "envelope_manifest_sha256": manifest(envelopes),
        "receipt_manifest_sha256": manifest(receipts), "failure": failure,
    }


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--package",type=Path,required=True); p.add_argument("--state-root",type=Path,required=True)
    p.add_argument("--raw-root",type=Path,required=True); p.add_argument("--claim-id",required=True); p.add_argument("--claim-scope-sha256",required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=inspect(package=a.package,state_root=a.state_root,raw_root=a.raw_root,claim_id=a.claim_id,expected_claim_scope=a.claim_scope_sha256)
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); print(json.dumps(result,sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
