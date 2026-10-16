"""Crash-safe, consume-once execution for the bounded BUY NOW history backfill.

The journal is the authority.  An intent is durably committed before transport;
an atomic response envelope is committed before normalization.  Therefore a
missing envelope after an intent is indeterminate and is never retried.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from services.buy_now_history_continuity import validate_backfill_observation_set

CLAIM_SCHEMA = "ATLAS_BUY_NOW_HISTORY_BACKFILL_CLAIM_V1"
ALLOWED_ENDPOINTS = ("/stock/candle", "/stock/split", "/stock/dividend")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def scope_digest(value: Any) -> str:
    """Match the registered gateway canonical JSON contract (no trailing LF)."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical(value)); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_dir(path.parent)
    except BaseException:
        # An existing intent/claim is never removed or rolled back.
        raise


def build_claim_scope(*, claim_id: str, source_sha: str, workflow_source_sha: str, artifact_id: int,
                      artifact_zip_sha256: str, package_sha256: str,
                      plan_sha256: str, scope_sha256: str,
                      plan: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "schema": CLAIM_SCHEMA, "claim_id": claim_id, "source_sha": source_sha,
        "workflow_source_sha": workflow_source_sha,
        "artifact_id": int(artifact_id), "artifact_zip_sha256": artifact_zip_sha256,
        "package_sha256": package_sha256, "plan_sha256": plan_sha256,
        "scope_sha256": scope_sha256,
        "membership_count": int(plan.get("customer_symbol_count", 0)),
        "membership_sha256": str((plan.get("membership_identity") or {}).get("membership_sha256", "")),
        "retained_artifact_set_sha256": str((plan.get("retained_history_identity") or {}).get("artifact_set_sha256", "")),
        "sessions": list(plan.get("missing_sessions") or []),
        "endpoints": list(plan.get("endpoint_allowlist") or []),
        "maximum_requests": int(plan.get("absolute_request_ceiling", 0)),
        "concurrency": int((plan.get("execution_policy") or {}).get("concurrency", 0)),
        "initial_rpm": int((plan.get("execution_policy") or {}).get("rate_limit_rpm", 0)),
        "automatic_retries": int(plan.get("automatic_retries", -1)),
    }
    value["claim_scope_sha256"] = digest(value)
    return value


def validate_scope(scope: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    supplied = str(scope.get("claim_scope_sha256", ""))
    if supplied != digest({k: v for k, v in scope.items() if k != "claim_scope_sha256"}):
        raise PermissionError("BACKFILL_CLAIM_SCOPE_DIGEST_INVALID")
    checks = (
        len(str(scope.get("workflow_source_sha", ""))) == 40,
        scope.get("source_sha") == plan.get("source_sha"),
        scope.get("plan_sha256") == plan.get("plan_sha256"),
        scope.get("scope_sha256") == scope_digest(plan),
        scope.get("membership_count") == plan.get("customer_symbol_count") == 1298,
        scope.get("sessions") == plan.get("missing_sessions"),
        tuple(scope.get("endpoints") or ()) == ALLOWED_ENDPOINTS,
        scope.get("maximum_requests") == plan.get("request_count") == 3894,
        scope.get("concurrency") == 1,
        scope.get("initial_rpm") == 60,
        scope.get("automatic_retries") == 0,
    )
    if not all(checks):
        raise PermissionError("BACKFILL_CLAIM_SCOPE_BINDING_INVALID")


def authorization_token(scope: Mapping[str, Any]) -> str:
    return f"AUTHORIZE_ATLAS_BACKFILL_CLAIM:{scope['claim_id']}:{scope['claim_scope_sha256']}"


@dataclass(frozen=True)
class Response:
    status_code: int
    body: bytes
    headers: Mapping[str, str] | None = None


class BackfillExecutor:
    def __init__(self, *, state_root: Path, raw_root: Path, scope: Mapping[str, Any],
                 plan: Mapping[str, Any], token: str, execution_id: str,
                 transport: Callable[[Mapping[str, Any]], Response], provider_free: bool = False):
        validate_scope(scope, plan)
        if token != authorization_token(scope):
            raise PermissionError("BACKFILL_CLAIM_AUTHORIZATION_INVALID")
        self.scope, self.plan, self.execution_id = dict(scope), dict(plan), execution_id
        self.transport = transport
        self.provider_free = provider_free
        self.claim_dir = state_root / "history_backfill_claims" / str(scope["claim_id"])
        self.raw_dir = raw_root / "history_backfill" / str(scope["claim_id"])

    def _claim(self) -> dict[str, Any]:
        self.claim_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        claim_path = self.claim_dir / "claim.json"
        if not claim_path.exists():
            record = {"scope": self.scope, "state": "CONSUMED", "execution_id": self.execution_id,
                      "consumed_at": datetime.now(timezone.utc).isoformat()}
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            fd = os.open(claim_path, flags, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical(record)); handle.flush(); os.fsync(handle.fileno())
            fsync_dir(self.claim_dir)
            return record
        record = json.loads(claim_path.read_text())
        if record.get("scope") != self.scope:
            raise PermissionError("BACKFILL_CLAIM_REUSE_SCOPE_MISMATCH")
        if record.get("execution_id") != self.execution_id:
            raise PermissionError("BACKFILL_CLAIM_ALREADY_CONSUMED")
        if record.get("state") == "COMPLETE":
            raise PermissionError("BACKFILL_CLAIM_ALREADY_COMPLETE")
        return record

    def run(self, *, stop_after_response_ordinal: int | None = None,
            stop_after_intent_ordinal: int | None = None) -> dict[str, Any]:
        self.claim_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.claim_dir / "execution.lock"
        with lock_path.open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise PermissionError("BACKFILL_CLAIM_COMPETING_WORKER") from exc
            claim = self._claim()
            attempts = recovered = 0
            for request in self.plan["requests"]:
                ordinal = int(request["ordinal"])
                intent = self.claim_dir / "intents" / f"{ordinal:05d}.json"
                envelope = self.raw_dir / f"{ordinal:05d}.json"
                receipt = self.claim_dir / "receipts" / f"{ordinal:05d}.json"
                if receipt.exists():
                    r = json.loads(receipt.read_text())
                    if not envelope.exists() or r.get("envelope_sha256") != file_sha256(envelope):
                        raise RuntimeError(f"BACKFILL_RECEIPT_CORRUPT:{ordinal}")
                    recovered += 1; continue
                if envelope.exists():
                    body = json.loads(envelope.read_text())
                    disposition = self._validate_response(request, body)
                    atomic_json(receipt, {"ordinal": ordinal, "request_sha256": digest(request),
                                         "envelope_sha256": file_sha256(envelope), "recovered": True,
                                         "evidence_disposition": disposition})
                    recovered += 1; continue
                if intent.exists():
                    raise RuntimeError(f"BACKFILL_ATTEMPT_INDETERMINATE:{ordinal}")
                atomic_json(intent, {"ordinal": ordinal, "request_sha256": digest(request),
                                     "state": "INTENT_RECORDED", "attempt_budget_consumed": True})
                attempts += 1
                if stop_after_intent_ordinal == ordinal:
                    raise RuntimeError("SIMULATED_CRASH_AFTER_INTENT")
                response = self.transport(request)
                envelope_value = {
                    "ordinal": ordinal, "request_sha256": digest(request),
                    "status_code": int(response.status_code),
                    "headers": dict(response.headers or {}),
                    "body_base64": base64.b64encode(response.body).decode(),
                    "body_sha256": hashlib.sha256(response.body).hexdigest(),
                }
                atomic_json(envelope, envelope_value)
                if stop_after_response_ordinal == ordinal:
                    raise RuntimeError("SIMULATED_CRASH_AFTER_RESPONSE")
                disposition = self._validate_response(request, envelope_value)
                atomic_json(receipt, {"ordinal": ordinal, "request_sha256": digest(request),
                                     "envelope_sha256": file_sha256(envelope), "recovered": False,
                                     "evidence_disposition": disposition})
            completed = len(list((self.claim_dir / "receipts").glob("*.json")))
            if completed != 3894:
                raise RuntimeError(f"BACKFILL_NOT_TERMINAL:{completed}:3894")
            validation = self._materialize_and_validate()
            claim["state"] = "COMPLETE"; claim["completed_at"] = datetime.now(timezone.utc).isoformat()
            atomic_json(self.claim_dir / "claim.next.json", claim)
            os.replace(self.claim_dir / "claim.next.json", self.claim_dir / "claim.json")
            fsync_dir(self.claim_dir)
            return {"status": "COMPLETE", "requests": completed, "attempts_this_run": attempts,
                    "recovered_receipts": recovered,
                    "transport_attempts": attempts,
                    "provider_calls": 0 if self.provider_free else attempts,
                    "publication_writes": 0, "claim_scope_sha256": self.scope["claim_scope_sha256"],
                    "observation_validation": validation,
                    "certification_handoff": "READY_FOR_MEMORY_BOUNDED_CERTIFICATION",
                    "publication_boundary": "SEPARATE_AUTHORIZATION_REQUIRED"}

    def _materialize_and_validate(self) -> dict[str, Any]:
        grouped: dict[str, dict[str, tuple[Mapping[str, Any], Path]]] = {}
        for request in self.plan["requests"]:
            ordinal = int(request["ordinal"])
            path = self.raw_dir / f"{ordinal:05d}.json"
            if not path.exists():
                raise RuntimeError(f"BACKFILL_RAW_RESPONSE_MISSING:{ordinal}")
            envelope = json.loads(path.read_text())
            if envelope.get("request_sha256") != digest(request):
                raise RuntimeError(f"BACKFILL_RAW_REQUEST_IDENTITY_INVALID:{ordinal}")
            grouped.setdefault(str(request["ticker"]), {})[str(request["capability"])] = (envelope, path)
        observations: dict[str, list[dict[str, Any]]] = {}
        unavailable: dict[str, dict[str, Any]] = {}
        wanted = list(self.plan["missing_sessions"])
        for ticker, capabilities in grouped.items():
            if set(capabilities) != {"historical_ohlcv", "splits", "dividends"}:
                raise RuntimeError(f"BACKFILL_CAPABILITY_SET_INCOMPLETE:{ticker}")
            candle, candle_path = capabilities["historical_ohlcv"]
            split, split_path = capabilities["splits"]
            dividend, dividend_path = capabilities["dividends"]
            candle_body = json.loads(base64.b64decode(candle["body_base64"]))
            split_body = json.loads(base64.b64decode(split["body_base64"]))
            dividend_body = json.loads(base64.b64decode(dividend["body_base64"]))
            if candle_body.get("s") == "no_data":
                unavailable[ticker] = {
                    "reason": "FINNHUB_NO_DATA",
                    "raw_response_sha256": file_sha256(candle_path),
                    "requested_sessions": wanted,
                }
                continue
            sessions = [datetime.fromtimestamp(int(v), timezone.utc).date().isoformat() for v in candle_body["t"]]
            if sessions != wanted:
                raise RuntimeError(f"BACKFILL_MISSING_SESSION_SET_INVALID:{ticker}")
            action_status = "PRESENT" if split_body or dividend_body else "NONE"
            lineage = hashlib.sha256((file_sha256(candle_path) + file_sha256(split_path) + file_sha256(dividend_path)).encode()).hexdigest()
            observations[ticker] = [
                {"session": session, "open": candle_body["o"][i], "high": candle_body["h"][i],
                 "low": candle_body["l"][i], "close": candle_body["c"][i],
                 "volume": candle_body["v"][i], "raw_response_sha256": lineage,
                 "corporate_action_status": action_status}
                for i, session in enumerate(sessions)
            ]
        return validate_backfill_observation_set(
            plan=self.plan, observations=observations, unavailable=unavailable,
        )

    @staticmethod
    def _validate_response(request: Mapping[str, Any], envelope: Mapping[str, Any]) -> str:
        status = int(envelope.get("status_code", 0))
        if status == 429:
            raise RuntimeError("BACKFILL_HTTP_429")
        if status in (401, 403):
            raise RuntimeError("BACKFILL_ENTITLEMENT_ERROR")
        if status != 200:
            raise RuntimeError(f"BACKFILL_HTTP_ERROR:{status}")
        try:
            body = json.loads(base64.b64decode(str(envelope["body_base64"])))
        except Exception as exc:
            raise RuntimeError("BACKFILL_RESPONSE_SCHEMA_INVALID") from exc
        endpoint = request.get("endpoint")
        if endpoint == "/stock/candle":
            # Finnhub documents {"s":"no_data"} as a terminal response.  It is
            # evidence of unavailability, never an empty price series or a zero.
            # Persist a receipt so the bounded acquisition can continue, then
            # force the affected security into the explicit unavailable set.
            if body == {"s": "no_data"}:
                return "FINNHUB_NO_DATA"
            fields = ("c", "h", "l", "o", "t", "v")
            if body.get("s") != "ok" or any(not isinstance(body.get(k), list) for k in fields):
                raise RuntimeError("BACKFILL_CANDLE_SCHEMA_INVALID")
            lengths = {len(body[k]) for k in fields}
            if len(lengths) != 1 or not next(iter(lengths)) or any(v is None for v in body["v"]):
                raise RuntimeError("BACKFILL_CANDLE_VOLUME_OR_LENGTH_INVALID")
            if body["t"] != sorted(set(body["t"])):
                raise RuntimeError("BACKFILL_CANDLE_SESSIONS_DUPLICATE_OR_UNORDERED")
        elif endpoint in ("/stock/split", "/stock/dividend"):
            if not isinstance(body, list):
                raise RuntimeError("BACKFILL_CORPORATE_ACTION_SCHEMA_INVALID")
            dates: list[str] = []
            for item in body:
                if not isinstance(item, dict) or not isinstance(item.get("date"), str):
                    raise RuntimeError("BACKFILL_CORPORATE_ACTION_SCHEMA_INVALID")
                action_date = item["date"]
                if not (str(request["parameters"]["from"]) <= action_date <= str(request["parameters"]["to"])):
                    raise RuntimeError("BACKFILL_CORPORATE_ACTION_DATE_OUT_OF_RANGE")
                dates.append(action_date)
                if endpoint == "/stock/split" and (
                    not isinstance(item.get("fromFactor"), (int, float)) or
                    not isinstance(item.get("toFactor"), (int, float)) or
                    item["fromFactor"] <= 0 or item["toFactor"] <= 0
                ):
                    raise RuntimeError("BACKFILL_SPLIT_FACTOR_INVALID")
                if endpoint == "/stock/dividend" and (
                    not isinstance(item.get("amount"), (int, float)) or item["amount"] < 0
                ):
                    raise RuntimeError("BACKFILL_DIVIDEND_AMOUNT_INVALID")
            if dates != sorted(set(dates)):
                raise RuntimeError("BACKFILL_CORPORATE_ACTIONS_DUPLICATE_OR_UNORDERED")
        else:
            raise RuntimeError("BACKFILL_ENDPOINT_NOT_ALLOWED")
        return "AVAILABLE"


__all__ = ["BackfillExecutor", "Response", "authorization_token", "build_claim_scope", "scope_digest"]
