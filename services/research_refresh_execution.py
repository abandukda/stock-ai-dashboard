"""Durable, provider-free execution boundary for bounded Research refreshes.

This module deliberately owns no HTTP client.  It compiles the existing
cache-first plan into source-bound request specifications and can rehearse the
complete durable lifecycle.  A future protected workflow may inject a
transport only after separately proving authorization and enablement; the
public entry point remains fail-closed in this release.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from services.buy_now_history_backfill_execution import atomic_json
from services.finnhub_enterprise_display_contract import display_authority
from services.research_refresh_readiness import assert_zero_call_preflight


SCHEMA = "ATLAS_RESEARCH_REFRESH_EXECUTION_V1"
MAX_REQUESTS = 225

# Nine cold-cache requests per ticker fit the immutable 25/225 boundary.
# Lower-priority families can occupy capacity released by verified cache hits.
CAPABILITY_PRIORITY = (
    "historical_ohlcv",
    "splits",
    "dividends",
    "financial_statements",
    "basic_financials",
    "stock_earnings",
    "recommendations",
    "price_targets",
    "company_news",
    "analyst_actions",
    "earnings_calendar",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _unix(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def request_parameters(capability: str, ticker: str, *, as_of: date) -> dict[str, Any]:
    """Return deterministic Finnhub parameters without invoking transport."""
    start_5y = as_of - timedelta(days=5 * 366)
    start_1y = as_of - timedelta(days=366)
    if capability == "historical_ohlcv":
        # Finnhub `to` is an interval end timestamp, not an inclusive date.
        # Match the completed-session boundary used by incremental refreshes.
        return {"symbol": ticker, "resolution": "D", "from": _unix(start_5y), "to": _unix(as_of + timedelta(days=1)) - 1}
    if capability in {"splits", "dividends"}:
        return {"symbol": ticker, "from": start_5y.isoformat(), "to": as_of.isoformat()}
    if capability == "financial_statements":
        return {"symbol": ticker, "freq": "annual"}
    if capability == "basic_financials":
        return {"symbol": ticker, "metric": "all"}
    if capability == "company_news":
        return {"symbol": ticker, "from": start_1y.isoformat(), "to": as_of.isoformat()}
    if capability == "earnings_calendar":
        return {"symbol": ticker, "from": (as_of - timedelta(days=90)).isoformat(),
                "to": (as_of + timedelta(days=180)).isoformat()}
    return {"symbol": ticker}


def compile_execution_plan(plan: Mapping[str, Any], *, as_of: date) -> dict[str, Any]:
    """Compile cache-first intents into a capped, parameter-complete package.

    The upstream plan is checked first.  Families not selected within the hard
    budget are explicit ``DEFERRED_REQUEST_BUDGET`` records, never silently
    treated as current or unavailable.
    """
    assert_zero_call_preflight(plan)
    source_sha = str(plan.get("source_sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("RESEARCH_REFRESH_SOURCE_SHA_INVALID")
    unsigned = dict(plan)
    supplied_plan_digest = str(unsigned.pop("plan_sha256", ""))
    if not supplied_plan_digest or _digest(unsigned) != supplied_plan_digest:
        raise ValueError("RESEARCH_REFRESH_UPSTREAM_PLAN_DIGEST_INVALID")
    expected_scope = _digest({
        "source_sha": source_sha,
        "tickers": list(plan.get("tickers") or ()),
        "requests": list(plan.get("requests") or ()),
        "limits": dict(plan.get("limits") or {}),
        "contract_id": plan.get("contract_id"),
    })
    if expected_scope != plan.get("scope_sha256"):
        raise ValueError("RESEARCH_REFRESH_UPSTREAM_SCOPE_DIGEST_INVALID")
    tickers = list(plan.get("tickers") or ())
    by_key = {
        (str(row.get("ticker")), str(row.get("capability"))): dict(row)
        for row in plan.get("requests") or ()
    }
    retained = {(str(row.get("ticker")), str(row.get("capability")))
                for row in plan.get("retained_fresh") or ()}
    unavailable = {(str(row.get("ticker")), str(row.get("capability")))
                   for row in plan.get("unavailable") or ()}
    requests: list[dict[str, Any]] = []
    deferred: list[dict[str, str]] = []
    # Capability-major ordering ensures every selected ticker receives the
    # same cold-cache core before lower-priority families consume capacity.
    for capability in CAPABILITY_PRIORITY:
        for ticker in tickers:
            key = (ticker, capability)
            if key in retained or key in unavailable:
                continue
            source = by_key.get(key)
            if source is None and capability in {"splits", "dividends"}:
                authority = display_authority(capability)
                if authority is not None:
                    source = {"endpoint": authority.endpoint,
                              "reason": "SIGNED_DISPLAY_CONTRACT_CACHE_MISSING"}
            if source is None:
                deferred.append({"ticker": ticker, "capability": capability,
                                 "reason": "NOT_IN_UPSTREAM_PLAN"})
                continue
            if len(requests) >= MAX_REQUESTS:
                deferred.append({"ticker": ticker, "capability": capability,
                                 "reason": "DEFERRED_REQUEST_BUDGET"})
                continue
            request = {
                "ordinal": len(requests) + 1,
                "ticker": ticker,
                "capability": capability,
                "endpoint": source["endpoint"],
                "parameters": request_parameters(capability, ticker, as_of=as_of),
                "cache_reason": source["reason"],
            }
            request["request_sha256"] = _digest(request)
            requests.append(request)
    compiled: dict[str, Any] = {
        "schema": SCHEMA,
        "source_sha": plan["source_sha"],
        "upstream_plan_sha256": plan["plan_sha256"],
        "upstream_scope_sha256": plan["scope_sha256"],
        "as_of": as_of.isoformat(),
        "mode": "REHEARSAL_TRANSPORT_DISABLED",
        "limits": {"max_tickers": 25, "max_requests": MAX_REQUESTS,
                   "concurrency": 1, "retries": 0},
        "requests": requests,
        "retained_fresh": list(plan.get("retained_fresh") or ()),
        "unavailable": list(plan.get("unavailable") or ()),
        "deferred": deferred,
        "provider_calls": 0,
        "publication_writes": 0,
        "report_card_writes": 0,
        "recommendation_authority": "UNCHANGED",
        "entitlement_status": "LIVE_REVALIDATION_REQUIRED",
    }
    compiled["scope_sha256"] = _digest({
        "source_sha": compiled["source_sha"], "as_of": compiled["as_of"],
        "requests": requests, "limits": compiled["limits"],
    })
    compiled["package_sha256"] = _digest(compiled)
    return compiled


@dataclass(frozen=True)
class RehearsalResult:
    package_sha256: str
    completed: int
    resumed: int
    provider_calls: int = 0


def rehearse(plan: Mapping[str, Any], *, durable_root: Path) -> RehearsalResult:
    """Exercise raw-first durable state with deterministic simulated envelopes."""
    if plan.get("schema") != SCHEMA or plan.get("mode") != "REHEARSAL_TRANSPORT_DISABLED":
        raise ValueError("RESEARCH_REFRESH_REHEARSAL_PLAN_INVALID")
    if plan.get("provider_calls") != 0 or plan.get("recommendation_authority") != "UNCHANGED":
        raise ValueError("RESEARCH_REFRESH_REHEARSAL_AUTHORITY_INVALID")
    requests = list(plan.get("requests") or ())
    if len(requests) > MAX_REQUESTS:
        raise ValueError("RESEARCH_REFRESH_REHEARSAL_CEILING_EXCEEDED")
    run = Path(durable_root) / str(plan["package_sha256"])
    intents, envelopes, receipts = run / "intents", run / "envelopes", run / "receipts"
    for directory in (intents, envelopes, receipts):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = run / "manifest.json"
    if manifest.exists():
        existing = json.loads(manifest.read_text())
        if existing.get("package_sha256") != plan["package_sha256"]:
            raise ValueError("RESEARCH_REFRESH_REHEARSAL_PACKAGE_MISMATCH")
    else:
        atomic_json(manifest, {"schema": SCHEMA, "package_sha256": plan["package_sha256"],
                               "source_sha": plan["source_sha"], "state": "OPEN"})

    resumed = 0
    for request in requests:
        name = f"{int(request['ordinal']):04d}.json"
        receipt = receipts / name
        if receipt.exists():
            value = json.loads(receipt.read_text())
            if value.get("request_sha256") != request["request_sha256"]:
                raise ValueError("RESEARCH_REFRESH_REHEARSAL_RECEIPT_MISMATCH")
            resumed += 1
            continue
        atomic_json(intents / name, request)
        envelope = {
            "request_sha256": request["request_sha256"],
            "classification": "SIMULATED_PROVIDER_FREE_REHEARSAL",
            "licensed_values": None,
            "provider_calls": 0,
        }
        atomic_json(envelopes / name, envelope)
        atomic_json(receipt, {"request_sha256": request["request_sha256"],
                              "envelope_sha256": _digest(envelope), "terminal": True})
    atomic_json(manifest, {"schema": SCHEMA, "package_sha256": plan["package_sha256"],
                           "source_sha": plan["source_sha"], "state": "COMPLETE",
                           "completed": len(requests), "provider_calls": 0})
    return RehearsalResult(plan["package_sha256"], len(requests), resumed)


def execute_live(*_: Any, **__: Any) -> None:
    """Registered LIVE interface; intentionally unavailable in this release."""
    if os.getenv("ATLAS_RESEARCH_REFRESH_LIVE_ENABLED", "false").lower() != "true":
        raise PermissionError("RESEARCH_REFRESH_LIVE_DISABLED")
    raise PermissionError("RESEARCH_REFRESH_LIVE_WORKFLOW_NOT_REGISTERED")


__all__ = ["CAPABILITY_PRIORITY", "MAX_REQUESTS", "RehearsalResult", "SCHEMA",
           "compile_execution_plan", "execute_live", "rehearse", "request_parameters"]
