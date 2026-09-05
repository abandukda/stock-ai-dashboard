"""Explicit INTERNAL_TRIAL Twelve intelligence acquisition.

This context is non-scoring.  Canonical ATLAS values always win and raw
provider payloads are retained behind evidence envelopes for later mapping.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import time
from typing import Any, Callable, Mapping, Sequence

import requests

from services.data_mode_policy import internal_trial_mode
from services.live_market.twelve_data_phase1 import REST_BASE, load_twelve_data_setting, normalize_ticker


VERSION = "TWELVE_DATA_INTERNAL_TRIAL_INTELLIGENCE_V1"
ENDPOINTS = (
    "profile", "statistics", "income_statement", "balance_sheet", "cash_flow",
    "earnings", "earnings_estimate", "revenue_estimate", "price_target",
    "insider_transactions", "institutional_holders", "press_releases",
    "splits", "dividends", "etf",
)


def _evidence_id(symbol: str, family: str, observed: str) -> str:
    digest = hashlib.sha256(f"{symbol}|{family}|{observed}".encode()).hexdigest()[:20]
    return f"TDTRIAL-{digest}"


def acquire_twelve_trial_dossiers(
    symbols: Sequence[str], *, get: Callable[..., Any] = requests.get,
    secrets: Mapping[str, Any] | None = None, environ: Mapping[str, str] | None = None,
    max_workers: int = 6, timeout: float = 12, endpoints: Sequence[str] = ENDPOINTS,
) -> dict[str, Any]:
    if not internal_trial_mode(environ=environ, secrets=secrets):
        return {"version": VERSION, "status": "DISABLED", "dossiers": {}, "provider_calls": 0}
    key = load_twelve_data_setting("TWELVE_DATA_API_KEY", secrets=secrets, environ=environ)
    if not key:
        return {"version": VERSION, "status": "DATA_UNAVAILABLE", "dossiers": {}, "provider_calls": 0, "reason_codes": ("TWELVE_DATA_API_KEY_UNAVAILABLE",)}
    observed = datetime.now(timezone.utc).isoformat()
    clean = tuple(dict.fromkeys(normalize_ticker(symbol) for symbol in symbols))
    dossiers = {symbol: {"ticker": symbol, "families": {}} for symbol in clean}
    telemetry = []

    def fetch(symbol: str, family: str) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        try:
            response = get(f"{REST_BASE}/{family}", params={"symbol": symbol}, headers={"Authorization": f"apikey {key}"}, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            error = isinstance(payload, Mapping) and str(payload.get("status") or "").lower() == "error"
            envelope = {
                "status": "DATA_UNAVAILABLE" if error else "AVAILABLE", "provider": "TWELVE_DATA",
                "endpoint": family, "observed_at": observed,
                "evidence_id": _evidence_id(symbol, family, observed),
                "payload": payload if not error else None,
                "reason_codes": ("PROVIDER_ERROR",) if error else (),
            }
            meta = {"ticker": symbol, "endpoint": family, "success": not error, "latency_seconds": round(time.monotonic()-started, 3)}
            return symbol, family, envelope, meta
        except Exception as exc:
            return symbol, family, {"status": "DATA_UNAVAILABLE", "provider": "TWELVE_DATA", "endpoint": family, "observed_at": observed, "evidence_id": _evidence_id(symbol, family, observed), "payload": None, "reason_codes": (type(exc).__name__.upper(),)}, {"ticker": symbol, "endpoint": family, "success": False, "latency_seconds": round(time.monotonic()-started, 3)}

    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as pool:
        selected = tuple(family for family in endpoints if family in ENDPOINTS)
        futures = [pool.submit(fetch, symbol, family) for symbol in clean for family in selected]
        for future in as_completed(futures):
            symbol, family, envelope, meta = future.result()
            dossiers[symbol]["families"][family] = envelope
            telemetry.append(meta)
    successes = sum(item["success"] for item in telemetry)
    for dossier in dossiers.values():
        dossier["evidence_ids"] = tuple(item["evidence_id"] for item in dossier["families"].values() if item["status"] == "AVAILABLE")
    return {
        "version": VERSION, "status": "AVAILABLE" if successes else "DATA_UNAVAILABLE",
        "dossiers": dossiers, "provider_calls": len(telemetry), "successful_calls": successes,
        "success_rate": successes / len(telemetry) if telemetry else 0,
        "latency_seconds": {"total": round(sum(item["latency_seconds"] for item in telemetry), 3), "max": max((item["latency_seconds"] for item in telemetry), default=0)},
        "endpoint_success": {family: sum(item["success"] for item in telemetry if item["endpoint"] == family) for family in selected},
        "observed_at": observed,
    }


def _nested(source: Any, *path: str) -> Any:
    current = source
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_record(payload: Any, key: str) -> Mapping[str, Any]:
    values = payload.get(key) if isinstance(payload, Mapping) else None
    return values[0] if isinstance(values, list) and values and isinstance(values[0], Mapping) else {}


def _forward_estimate_record(payload: Any, key: str) -> Mapping[str, Any]:
    values = payload.get(key) if isinstance(payload, Mapping) else None
    records = [item for item in values or () if isinstance(item, Mapping)] if isinstance(values, list) else []
    for period in ("next_year", "current_year"):
        record = next((item for item in records if str(item.get("period") or "").lower() == period), None)
        if record is not None:
            return record
    return {}


def _pct(value: Any) -> float | None:
    try:
        number = float(value)
        return number * 100 if abs(number) <= 2 else number
    except (TypeError, ValueError):
        return None


def _coalesce(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def normalize_trial_dossier(row: Mapping[str, Any], dossier: Mapping[str, Any]) -> dict[str, Any]:
    """Merge only missing evidence fields; never overwrite an ATLAS value."""
    output = dict(row)
    families = dossier.get("families") if isinstance(dossier.get("families"), Mapping) else {}
    payload = lambda family: (families.get(family) or {}).get("payload") or {}
    stats = _nested(payload("statistics"), "statistics") or {}
    financials = _nested(stats, "financials") or {}
    income_stats = _nested(financials, "income_statement") or {}
    balance_stats = _nested(financials, "balance_sheet") or {}
    cash_stats = _nested(financials, "cash_flow") or {}
    income = _first_record(payload("income_statement"), "income_statement")
    balance = _first_record(payload("balance_sheet"), "balance_sheet")
    cash = _first_record(payload("cash_flow"), "cash_flow")
    values = {
        "revenue_growth": _pct(income_stats.get("quarterly_revenue_growth")),
        "earnings_growth": _pct(income_stats.get("quarterly_earnings_growth_yoy")),
        "operating_profit_margin": _pct(financials.get("operating_margin")),
        "free_cash_flow": _coalesce(cash_stats.get("levered_free_cash_flow_ttm"), cash.get("free_cash_flow")),
        "current_ratio": balance_stats.get("current_ratio_mrq"),
        "latest_revenue": _coalesce(income_stats.get("revenue_ttm"), income.get("sales")),
        "latest_operating_income": income.get("operating_income"),
        "operating_cash_flow": _coalesce(cash_stats.get("operating_cash_flow_ttm"), _nested(cash, "operating_activities", "operating_cash_flow")),
        "total_debt": _coalesce(balance_stats.get("total_debt_mrq"), _nested(balance, "liabilities", "total_liabilities")),
        "cash_and_equivalents": _coalesce(balance_stats.get("total_cash_mrq"), _nested(balance, "assets", "current_assets", "cash_and_cash_equivalents")),
    }
    for key, value in values.items():
        if output.get(key) in (None, "", "Unavailable") and value is not None:
            output[key] = value
    profile = payload("profile")
    if isinstance(profile, Mapping):
        for target, source in (("description", "description"), ("sector", "sector"), ("industry", "industry")):
            if not output.get(target) and profile.get(source): output[target] = profile[source]
    eps_est = _forward_estimate_record(payload("earnings_estimate"), "earnings_estimate")
    rev_est = _forward_estimate_record(payload("revenue_estimate"), "revenue_estimate")
    if output.get("forward_eps") is None and eps_est.get("avg_estimate") is not None:
        output["forward_eps"] = eps_est["avg_estimate"]
        output["forward_eps_period"] = eps_est.get("period")
    if output.get("forward_revenue") is None and rev_est.get("avg_estimate") is not None:
        output["forward_revenue"] = rev_est["avg_estimate"]
        output["forward_revenue_period"] = rev_est.get("period")
    output["twelve_trial_dossier"] = dict(dossier)
    output["twelve_trial_evidence_ids"] = tuple(dossier.get("evidence_ids") or ())
    output["fundamental_source"] = output.get("fundamental_source") or "TWELVE_DATA_INTERNAL_TRIAL"
    return output


__all__ = ["ENDPOINTS", "VERSION", "acquire_twelve_trial_dossiers", "normalize_trial_dossier"]
