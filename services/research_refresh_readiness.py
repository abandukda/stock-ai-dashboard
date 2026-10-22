"""Provider-free planning contract for a bounded Research evidence refresh.

The customer read model never performs network I/O.  This module is the
separate planning boundary: it inspects cache metadata, signed display
coverage, and an entitlement snapshot, then emits deterministic request
intents for a later *separately authorized* acquisition job.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping

from services.finnhub_enterprise_display_contract import CONTRACT_ID, display_authority
from services.research_market_read_model import FAMILY_MAX_AGE_SECONDS


SCHEMA = "ATLAS_RESEARCH_REFRESH_PLAN_V1"
ABSOLUTE_MAX_TICKERS = 25
ABSOLUTE_MAX_REQUESTS = 225
ALLOWED_CAPABILITIES = (
    "historical_ohlcv",
    "financial_statements",
    "basic_financials",
    "stock_earnings",
    "earnings_calendar",
    "recommendations",
    "price_targets",
    "analyst_actions",
    "company_news",
)


# New endpoint families require explicit selection; defaults stay unchanged.
SUPPORTED_CAPABILITIES = (*ALLOWED_CAPABILITIES, "live_quote", "company_profile",
                          "revenue_estimates", "eps_estimates")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _ticker(value: Any) -> str:
    normalized = "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {"-", "."})
    if not normalized or normalized != str(value).upper().strip():
        raise ValueError("RESEARCH_REFRESH_TICKER_INVALID")
    return normalized


@dataclass(frozen=True)
class ResearchRefreshLimits:
    max_tickers: int = ABSOLUTE_MAX_TICKERS
    max_requests: int = ABSOLUTE_MAX_REQUESTS
    concurrency: int = 1
    retries: int = 0


def plan_research_refresh(
    tickers: Iterable[str],
    cache_index: Mapping[str, Mapping[str, Any]],
    entitlement: Mapping[str, Any],
    *,
    source_sha: str,
    now: datetime,
    limits: ResearchRefreshLimits = ResearchRefreshLimits(),
    capabilities: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return bounded request intents without importing or invoking transport."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("RESEARCH_REFRESH_TIMEZONE_REQUIRED")
    checked = now.astimezone(timezone.utc)
    supplied = tuple(ALLOWED_CAPABILITIES if capabilities is None else capabilities)
    if (not supplied or any(type(value) is not str or value not in SUPPORTED_CAPABILITIES for value in supplied)
            or len(supplied) != len(set(supplied))):
        raise ValueError("RESEARCH_REFRESH_CAPABILITY_INVALID")
    selected = tuple(value for value in SUPPORTED_CAPABILITIES if value in supplied)
    symbols = sorted({_ticker(value) for value in tickers})
    if (
        not source_sha
        or limits.max_tickers < 1
        or limits.max_tickers > ABSOLUTE_MAX_TICKERS
        or limits.max_requests < 1
        or limits.max_requests > ABSOLUTE_MAX_REQUESTS
        or limits.concurrency != 1
        or limits.retries != 0
        or len(symbols) > limits.max_tickers
    ):
        raise ValueError("RESEARCH_REFRESH_SCOPE_EXCEEDS_BOUND")
    entitled = set(entitlement.get("capabilities") or ())
    if (
        entitlement.get("status") != "APPROVED"
        or entitlement.get("contract_id") != CONTRACT_ID
    ):
        raise ValueError("RESEARCH_REFRESH_ENTITLEMENT_INVALID")

    intents: list[dict[str, Any]] = []
    retained: list[dict[str, str]] = []
    unavailable: list[dict[str, str]] = []
    for symbol in symbols:
        cached = cache_index.get(symbol) if isinstance(cache_index.get(symbol), Mapping) else {}
        for capability in selected:
            authority = display_authority(capability)
            if authority is None or capability not in entitled:
                unavailable.append({"ticker": symbol, "capability": capability, "reason": "NOT_ENTITLED"})
                continue
            family = cached.get(capability) if isinstance(cached.get(capability), Mapping) else {}
            captured = _instant(family.get("capture_timestamp"))
            age = (checked - captured).total_seconds() if captured and captured <= checked else None
            max_age = FAMILY_MAX_AGE_SECONDS[capability]
            if age is not None and age <= max_age and family.get("integrity_verified") is True:
                retained.append({"ticker": symbol, "capability": capability})
                continue
            intents.append({
                "ordinal": len(intents) + 1,
                "ticker": symbol,
                "capability": capability,
                "endpoint": authority.endpoint,
                "reason": "CACHE_MISSING" if not family else "CACHE_STALE_OR_UNVERIFIED",
            })
    if len(intents) > limits.max_requests:
        raise ValueError("RESEARCH_REFRESH_REQUEST_CEILING_EXCEEDED")

    plan: dict[str, Any] = {
        "schema": SCHEMA,
        "source_sha": source_sha,
        "created_at": checked.isoformat(),
        "mode": "PLAN_ONLY_TRANSPORT_DISABLED",
        "provider_calls": 0,
        "authorization_consumed": False,
        "publication_authority": "NONE",
        "recommendation_authority": "UNCHANGED",
        "limits": {
            "max_tickers": limits.max_tickers,
            "max_requests": limits.max_requests,
            "concurrency": limits.concurrency,
            "retries": limits.retries,
        },
        "tickers": symbols,
        "capabilities": list(selected),
        "requests": intents,
        "retained_fresh": retained,
        "unavailable": unavailable,
        "contract_id": CONTRACT_ID,
    }
    plan["scope_sha256"] = hashlib.sha256(_canonical({
        "source_sha": source_sha,
        "tickers": symbols,
        "capabilities": list(selected),
        "requests": intents,
        "limits": plan["limits"],
        "contract_id": CONTRACT_ID,
    })).hexdigest()
    plan["plan_sha256"] = hashlib.sha256(_canonical(plan)).hexdigest()
    return plan


def assert_zero_call_preflight(plan: Mapping[str, Any]) -> None:
    """Fail closed unless the object is an unconsumed provider-free plan."""
    if (
        plan.get("schema") != SCHEMA
        or plan.get("mode") != "PLAN_ONLY_TRANSPORT_DISABLED"
        or plan.get("provider_calls") != 0
        or plan.get("authorization_consumed") is not False
        or plan.get("publication_authority") != "NONE"
        or plan.get("recommendation_authority") != "UNCHANGED"
    ):
        raise ValueError("RESEARCH_REFRESH_ZERO_CALL_PREFLIGHT_FAILED")


__all__ = [
    "ABSOLUTE_MAX_REQUESTS", "ABSOLUTE_MAX_TICKERS", "ALLOWED_CAPABILITIES", "SUPPORTED_CAPABILITIES",
    "ResearchRefreshLimits", "SCHEMA",
    "assert_zero_call_preflight", "plan_research_refresh",
]
