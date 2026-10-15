"""Provider-free request planning for the bounded post-close Finnhub refresh.

This module deliberately does not own transport or scoring.  It produces a
deterministic, deduplicated acquisition contract which the existing Finnhub
adapter and canonical evaluation pipeline may execute after authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


PLAN_VERSION = "ATLAS_FINNHUB_INCREMENTAL_POST_CLOSE_V1"
PRICE_FAMILY = "completed_session_price"
CHANGE_PROBE_FAMILY = "filing_change_probe"
FUNDAMENTAL_FAMILIES = (
    "company_profile",
    "financial_statements",
    "basic_financials",
)


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


__all__ = [
    "CHANGE_PROBE_FAMILY", "FUNDAMENTAL_FAMILIES", "IncrementalCeiling",
    "PLAN_VERSION", "PRICE_FAMILY", "build_incremental_plan", "request_key",
    "validate_incremental_receipts",
]
