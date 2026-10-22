"""Pure conversion from a reviewed refresh plan to an existing gateway scope.

This does not execute a request, issue an authorization token, widen the
registered endpoint allowlist, or certify/publish financial information.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import re
from typing import Any, Mapping

from services.finnhub_enterprise_display_contract import display_authority
from services.operations_gateway import RESEARCH_ENDPOINTS, canonical_bytes, sha256
from services.research_refresh_execution import request_parameters, validate_execution_plan


SCHEMA = "ATLAS_RESEARCH_GATEWAY_SCOPE_FROM_REFRESH_V1"


def _pending_records(plan: Mapping[str, Any], key: str) -> list[dict[str, str]]:
    records = plan.get(key)
    fields = {"ticker", "capability"} if key == "retained_fresh" else {"ticker", "capability", "reason"}
    if not isinstance(records, list):
        raise ValueError("RESEARCH_GATEWAY_SCOPE_PENDING_SCHEMA_INVALID")
    for row in records:
        if (not isinstance(row, Mapping) or set(row) != fields
                or any(type(value) is not str for value in row.values())
                or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,29}", row["ticker"])
                or display_authority(row["capability"]) is None
                or (key != "retained_fresh" and row["reason"] not in {
                    "NOT_ENTITLED", "NOT_IN_UPSTREAM_PLAN", "DEFERRED_REQUEST_BUDGET"})):
            raise ValueError("RESEARCH_GATEWAY_SCOPE_PENDING_SCHEMA_INVALID")
    return deepcopy(records)


def build_research_gateway_scope(
    plan: Mapping[str, Any], *, expected_source_sha: str, rate_limit_rpm: int = 60,
) -> dict[str, Any]:
    """Return an immutable-scope candidate and its separately calculated digest.

    Every request must be compatible. Unsupported families are rejected, never
    silently filtered. To use a smaller compatible selection, compile a fresh
    plan and obtain a new owner scope approval. Write only result['scope'] as
    the gateway artifact; the digest/receipt stay outside that scope document.
    """
    requests = validate_execution_plan(plan)
    if (not re.fullmatch(r"[0-9a-f]{40}", str(expected_source_sha))
            or plan.get("source_sha") != expected_source_sha):
        raise PermissionError("RESEARCH_GATEWAY_SCOPE_SOURCE_MISMATCH")
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(plan.get(key) or ""))
           for key in ("upstream_plan_sha256", "upstream_scope_sha256")):
        raise ValueError("RESEARCH_GATEWAY_SCOPE_UPSTREAM_IDENTITY_INVALID")
    if type(rate_limit_rpm) is not int or not 1 <= rate_limit_rpm <= 500:
        raise ValueError("RESEARCH_GATEWAY_SCOPE_RATE_INVALID")
    if any(type(plan.get(key)) is not int or plan[key] != 0
           for key in ("provider_calls", "publication_writes", "report_card_writes")):
        raise PermissionError("RESEARCH_GATEWAY_SCOPE_AUTHORITY_INVALID")
    limits = plan.get("limits")
    if (not isinstance(limits, Mapping)
            or set(limits) != {"max_tickers", "max_requests", "concurrency", "retries"}
            or type(limits.get("max_tickers")) is not int
            or not 1 <= limits["max_tickers"] <= 25
            or type(limits.get("concurrency")) is not int or limits["concurrency"] != 1
            or type(limits.get("retries")) is not int or limits["retries"] != 0):
        raise ValueError("RESEARCH_GATEWAY_SCOPE_LIMITS_INVALID")
    try:
        session = date.fromisoformat(plan["as_of"])
    except (ValueError, TypeError, KeyError):
        raise ValueError("RESEARCH_GATEWAY_SCOPE_SESSION_INVALID") from None
    if not requests:
        raise ValueError("RESEARCH_GATEWAY_SCOPE_REQUESTS_EMPTY")
    converted = []
    tickers: set[str] = set()
    identities: set[str] = set()
    for request in requests:
        if set(request) != {"ordinal", "ticker", "capability", "endpoint", "parameters", "cache_reason", "request_sha256"}:
            raise ValueError("RESEARCH_GATEWAY_SCOPE_REQUEST_SCHEMA_INVALID")
        if type(request["cache_reason"]) is not str or request["cache_reason"] not in {"CACHE_MISSING", "CACHE_STALE_OR_UNVERIFIED", "SIGNED_DISPLAY_CONTRACT_CACHE_MISSING"}:
            raise ValueError("RESEARCH_GATEWAY_SCOPE_CACHE_REASON_INVALID")
        ticker, capability = request.get("ticker"), request.get("capability")
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,29}", ticker):
            raise ValueError("RESEARCH_GATEWAY_SCOPE_TICKER_INVALID")
        authority = display_authority(capability)
        endpoint = request.get("endpoint")
        if authority is None or endpoint != authority.endpoint or endpoint not in RESEARCH_ENDPOINTS:
            raise PermissionError("RESEARCH_GATEWAY_SCOPE_ENDPOINT_UNSUPPORTED")
        try:
            expected_parameters = request_parameters(capability, ticker, as_of=session)
        except (ValueError, OverflowError):
            raise PermissionError("RESEARCH_GATEWAY_SCOPE_PARAMETERS_MISMATCH") from None
        if request.get("parameters") != expected_parameters:
            raise PermissionError("RESEARCH_GATEWAY_SCOPE_PARAMETERS_MISMATCH")
        fingerprint = sha256(canonical_bytes({"endpoint": endpoint, "parameters": request["parameters"]}))
        if fingerprint in identities:
            raise ValueError("RESEARCH_GATEWAY_SCOPE_DUPLICATE_REQUEST")
        identities.add(fingerprint)
        tickers.add(ticker)
        row = deepcopy(dict(request))
        row["source_request_sha256"] = row.pop("request_sha256")
        row["method"] = "GET"
        converted.append(row)
    if len(tickers) > limits["max_tickers"]:
        raise ValueError("RESEARCH_GATEWAY_SCOPE_LIMITS_INVALID")
    scope = {
        "schema": SCHEMA,
        "source_sha": expected_source_sha,
        "as_of": plan["as_of"],
        "refresh_package_sha256": plan["package_sha256"],
        "refresh_scope_sha256": plan["scope_sha256"],
        "upstream_plan_sha256": plan["upstream_plan_sha256"],
        "upstream_scope_sha256": plan["upstream_scope_sha256"],
        "limits": deepcopy(dict(limits)),
        "execution_policy": {"rate_limit_rpm": rate_limit_rpm, "concurrency": 1, "retry_count": 0},
        "requests": converted,
        "retained_fresh": _pending_records(plan, "retained_fresh"),
        "unavailable": _pending_records(plan, "unavailable"),
        "deferred": _pending_records(plan, "deferred"),
        "acquisition_authority": "SEPARATE_OWNER_APPROVAL_REQUIRED",
        "recommendation_authority": "UNCHANGED",
        "publication_authority": "NONE",
        "report_card_authority": "NONE",
    }
    return {
        "status": "OWNER_REVIEW_ONLY_NOT_EXECUTABLE",
        "scope": scope,
        "scope_sha256": sha256(canonical_bytes(scope)),
        "max_provider_calls": limits["max_requests"],
        "request_count": len(converted),
        "authorization_issued": False,
        "provider_calls": 0,
        "publication_writes": 0,
        "report_card_writes": 0,
    }


__all__ = ["SCHEMA", "build_research_gateway_scope"]
