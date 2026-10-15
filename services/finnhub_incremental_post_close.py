"""Provider-free request planning for the bounded post-close Finnhub refresh.

This module deliberately does not own transport or scoring.  It produces a
deterministic, deduplicated acquisition contract which the existing Finnhub
adapter and canonical evaluation pipeline may execute after authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PLAN_VERSION = "ATLAS_FINNHUB_INCREMENTAL_POST_CLOSE_V1"
PRICE_FAMILY = "completed_session_price"
CHANGE_PROBE_FAMILY = "filing_change_probe"
FUNDAMENTAL_FAMILIES = (
    "company_profile",
    "financial_statements",
    "basic_financials",
)
CHECKPOINT_VERSION = "ATLAS_FINNHUB_INCREMENTAL_CHECKPOINT_V1"
RETRY_LIMIT = 0


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _symbols(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip().upper() for value in values if str(value).strip()})


@dataclass(frozen=True)
class IncrementalCeiling:
    customer_symbols: int = 1298
    changed_fundamental_symbols: int = 50
    fundamental_families_per_symbol: int = len(FUNDAMENTAL_FAMILIES)

    @property
    def price_requests(self) -> int:
        return self.customer_symbols

    @property
    def change_probe_requests(self) -> int:
        return self.customer_symbols

    @property
    def fundamental_requests(self) -> int:
        return self.changed_fundamental_symbols * self.fundamental_families_per_symbol

    @property
    def exact_max_requests(self) -> int:
        return self.price_requests + self.change_probe_requests + self.fundamental_requests


def request_key(*, session: str, symbol: str, family: str) -> str:
    return f"{session}:{symbol.upper()}:{family}"


def build_incremental_plan(
    *,
    session: str,
    customer_symbols: Sequence[str],
    changed_fundamental_symbols: Sequence[str] = (),
    ceiling: IncrementalCeiling = IncrementalCeiling(),
) -> dict[str, Any]:
    """Build a zero-provider-call request contract and fail closed on overflow.

    ``changed_fundamental_symbols`` must come from the completed-session filing
    change probe (or a certified retained change receipt), never model output.
    The plan intentionally contains no scoring changes.
    """
    symbols = _symbols(customer_symbols)
    changed = _symbols(changed_fundamental_symbols)
    if not session:
        raise ValueError("INCREMENTAL_SESSION_REQUIRED")
    if len(symbols) != ceiling.customer_symbols:
        raise ValueError(
            f"INCREMENTAL_CUSTOMER_SCOPE_MISMATCH:{len(symbols)}:{ceiling.customer_symbols}"
        )
    unknown = sorted(set(changed) - set(symbols))
    if unknown:
        raise ValueError(f"INCREMENTAL_CHANGED_SYMBOL_OUTSIDE_SCOPE:{','.join(unknown)}")
    if len(changed) > ceiling.changed_fundamental_symbols:
        raise ValueError(
            "INCREMENTAL_FUNDAMENTAL_CHANGE_CEILING_EXCEEDED:"
            f"{len(changed)}:{ceiling.changed_fundamental_symbols}"
        )

    requests: list[dict[str, str]] = []
    for symbol in symbols:
        requests.append({"symbol": symbol, "family": PRICE_FAMILY})
        requests.append({"symbol": symbol, "family": CHANGE_PROBE_FAMILY})
    for symbol in changed:
        for family in FUNDAMENTAL_FAMILIES:
            requests.append({"symbol": symbol, "family": family})

    keyed = {
        request_key(session=session, symbol=item["symbol"], family=item["family"]): item
        for item in requests
    }
    if len(keyed) != len(requests):
        raise ValueError("INCREMENTAL_REQUEST_DEDUPLICATION_FAILURE")
    if len(requests) > ceiling.exact_max_requests:
        raise ValueError("INCREMENTAL_EXACT_REQUEST_CEILING_EXCEEDED")

    family_counts = {
        family: sum(item["family"] == family for item in requests)
        for family in (PRICE_FAMILY, CHANGE_PROBE_FAMILY, *FUNDAMENTAL_FAMILIES)
    }
    plan: dict[str, Any] = {
        "plan_version": PLAN_VERSION,
        "session": session,
        "mode": "PROVIDER_FREE_PLAN",
        "provider_calls": 0,
        "methodology_mutation": "NONE",
        "publication_mode": "EXISTING_ATOMIC_PROMOTER",
        "customer_symbol_count": len(symbols),
        "changed_fundamental_symbol_count": len(changed),
        "request_count": len(requests),
        "exact_max_requests": ceiling.exact_max_requests,
        "request_ceiling": {
            "completed_session_price": ceiling.price_requests,
            "filing_change_probe": ceiling.change_probe_requests,
            "changed_fundamentals": ceiling.fundamental_requests,
        },
        "family_counts": family_counts,
        "request_keys": sorted(keyed),
    }
    plan["plan_sha256"] = _digest(plan)
    return plan


def validate_incremental_receipts(
    *, plan: Mapping[str, Any], receipts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Validate freshness and one-to-one request ownership before aggregation."""
    planned = set(plan.get("request_keys") or [])
    observed: dict[str, Mapping[str, Any]] = {}
    session = str(plan.get("session") or "")
    for receipt in receipts:
        key = str(receipt.get("request_key") or "")
        if key in observed:
            raise ValueError(f"INCREMENTAL_DUPLICATE_RECEIPT:{key}")
        if key not in planned:
            raise ValueError(f"INCREMENTAL_UNPLANNED_RECEIPT:{key}")
        if str(receipt.get("session") or "") != session:
            raise ValueError(f"INCREMENTAL_STALE_SESSION_RECEIPT:{key}")
        if receipt.get("status") != "AVAILABLE":
            raise ValueError(f"INCREMENTAL_UNAVAILABLE_RECEIPT:{key}")
        observed[key] = receipt
    missing = sorted(planned - set(observed))
    if missing:
        raise ValueError(f"INCREMENTAL_RECEIPTS_INCOMPLETE:{len(missing)}")
    result = {
        "status": "PASS",
        "session": session,
        "planned_requests": len(planned),
        "validated_receipts": len(observed),
        "methodology_mutation": "NONE",
    }
    result["receipt_set_sha256"] = _digest(sorted(observed))
    return result


def classify_retry(*, failure_code: str) -> dict[str, Any]:
    """Classify failures while preserving the production zero-retry policy."""
    retryable = failure_code in {"TIMEOUT", "HTTP_429", "HTTP_503", "CONNECTION_RESET"}
    return {
        "failure_code": failure_code,
        "retryable_class": retryable,
        "automatic_retry_limit": RETRY_LIMIT,
        "automatic_retry_authorized": False,
    }


def new_checkpoint(*, plan: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "checkpoint_version": CHECKPOINT_VERSION,
        "plan_sha256": str(plan.get("plan_sha256") or ""),
        "session": str(plan.get("session") or ""),
        "request_count": int(plan.get("request_count") or 0),
        "receipts": {},
        "telemetry": {"attempted_requests": 0, "accepted_receipts": 0, "automatic_retries": 0},
    }
    if not value["plan_sha256"] or not value["session"]:
        raise ValueError("INCREMENTAL_CHECKPOINT_PLAN_IDENTITY_MISSING")
    value["checkpoint_sha256"] = _digest(value)
    return value


def _validated_checkpoint(*, plan: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(checkpoint)
    supplied = value.pop("checkpoint_sha256", None)
    if supplied != _digest(value):
        raise ValueError("INCREMENTAL_CHECKPOINT_CORRUPT")
    value["checkpoint_sha256"] = supplied
    if value.get("checkpoint_version") != CHECKPOINT_VERSION:
        raise ValueError("INCREMENTAL_CHECKPOINT_VERSION_MISMATCH")
    if value.get("plan_sha256") != plan.get("plan_sha256"):
        raise ValueError("INCREMENTAL_CHECKPOINT_PLAN_MISMATCH")
    receipts = value.get("receipts")
    telemetry = value.get("telemetry")
    if not isinstance(receipts, dict) or not isinstance(telemetry, dict):
        raise ValueError("INCREMENTAL_CHECKPOINT_SCHEMA_INVALID")
    attempted = int(telemetry.get("attempted_requests") or 0)
    accepted = int(telemetry.get("accepted_receipts") or 0)
    retries = int(telemetry.get("automatic_retries") or 0)
    if attempted > int(plan.get("request_count") or 0) or accepted > attempted or retries != RETRY_LIMIT:
        raise ValueError("INCREMENTAL_TELEMETRY_CEILING_EXCEEDED")
    return value


def write_checkpoint_atomic(*, path: Path, checkpoint: Mapping[str, Any]) -> None:
    """Durably replace one checkpoint; a failed replace never reports success."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise


def load_checkpoint(*, path: Path, plan: Mapping[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return new_checkpoint(plan=plan)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("INCREMENTAL_CHECKPOINT_CORRUPT") from exc
    return _validated_checkpoint(plan=plan, checkpoint=value)


def accept_receipt(
    *, plan: Mapping[str, Any], checkpoint: Mapping[str, Any], receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the next checkpoint, treating exact duplicate execution idempotently."""
    current = _validated_checkpoint(plan=plan, checkpoint=checkpoint)
    key = str(receipt.get("request_key") or "")
    if key not in set(plan.get("request_keys") or []):
        raise ValueError(f"INCREMENTAL_UNPLANNED_RECEIPT:{key}")
    existing = current["receipts"].get(key)
    if existing is not None:
        if dict(existing) != dict(receipt):
            raise ValueError(f"INCREMENTAL_CONFLICTING_DUPLICATE_RECEIPT:{key}")
        return current
    if receipt.get("status") != "AVAILABLE" or receipt.get("session") != plan.get("session"):
        raise ValueError(f"INCREMENTAL_INVALID_RECEIPT:{key}")
    next_value = {key: value for key, value in current.items() if key != "checkpoint_sha256"}
    next_value["receipts"] = {**current["receipts"], key: dict(receipt)}
    next_value["telemetry"] = {
        **current["telemetry"],
        "attempted_requests": int(current["telemetry"]["attempted_requests"]) + 1,
        "accepted_receipts": int(current["telemetry"]["accepted_receipts"]) + 1,
        "automatic_retries": RETRY_LIMIT,
    }
    if next_value["telemetry"]["attempted_requests"] > int(plan["request_count"]):
        raise ValueError("INCREMENTAL_TELEMETRY_CEILING_EXCEEDED")
    next_value["checkpoint_sha256"] = _digest(next_value)
    return next_value


def resume_request_keys(*, plan: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> list[str]:
    current = _validated_checkpoint(plan=plan, checkpoint=checkpoint)
    return sorted(set(plan.get("request_keys") or []) - set(current["receipts"]))


def publication_readiness(*, plan: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    """Certify the input boundary; this function never mutates production files."""
    current = _validated_checkpoint(plan=plan, checkpoint=checkpoint)
    if resume_request_keys(plan=plan, checkpoint=current):
        raise ValueError("INCREMENTAL_PARTIAL_PUBLICATION_FORBIDDEN")
    receipts = list(current["receipts"].values())
    validation = validate_incremental_receipts(plan=plan, receipts=receipts)
    result = {
        "status": "READY_FOR_EXISTING_ATOMIC_PROMOTER",
        "provider_calls": 0,
        "production_writes": 0,
        "plan_sha256": plan["plan_sha256"],
        "checkpoint_sha256": current["checkpoint_sha256"],
        "receipt_set_sha256": validation["receipt_set_sha256"],
        "methodology_mutation": "NONE",
    }
    result["readiness_sha256"] = _digest(result)
    return result


__all__ = [
    "CHANGE_PROBE_FAMILY", "CHECKPOINT_VERSION", "FUNDAMENTAL_FAMILIES", "IncrementalCeiling",
    "PLAN_VERSION", "PRICE_FAMILY", "build_incremental_plan", "request_key",
    "accept_receipt", "classify_retry", "load_checkpoint", "new_checkpoint",
    "publication_readiness", "resume_request_keys", "validate_incremental_receipts",
    "write_checkpoint_atomic",
]
