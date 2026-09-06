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
    dossiers = {
        symbol: {"ticker": symbol, "observed_at": observed, "families": {}}
        for symbol in clean
    }
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


def _forward_estimate_records(payload: Any, key: str) -> list[dict[str, Any]]:
    values = payload.get(key) if isinstance(payload, Mapping) else None
    return [dict(item) for item in values or () if isinstance(item, Mapping)] if isinstance(values, list) else []


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
    valuation_stats = _nested(stats, "valuations_metrics") or {}
    stock_stats = _nested(stats, "stock_statistics") or {}
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
        "net_income": income.get("net_income"),
        "operating_cash_flow": _coalesce(cash_stats.get("operating_cash_flow_ttm"), _nested(cash, "operating_activities", "operating_cash_flow")),
        "total_debt": _coalesce(balance_stats.get("total_debt_mrq"), _nested(balance, "liabilities", "current_liabilities", "short_term_debt") if _nested(balance, "liabilities", "non_current_liabilities", "long_term_debt") is None else (_nested(balance, "liabilities", "current_liabilities", "short_term_debt") or 0) + (_nested(balance, "liabilities", "non_current_liabilities", "long_term_debt") or 0)),
        "cash_and_equivalents": _coalesce(balance_stats.get("total_cash_mrq"), _nested(balance, "assets", "current_assets", "cash_and_cash_equivalents")),
        "market_cap": _coalesce(valuation_stats.get("market_capitalization"), stats.get("market_capitalization"), stats.get("market_cap")),
        "diluted_shares": _coalesce(income.get("diluted_shares_outstanding"), income.get("weighted_average_shares_diluted"), income.get("diluted_average_shares"), stock_stats.get("shares_outstanding")),
        "basic_shares": _coalesce(income.get("basic_shares_outstanding"), stock_stats.get("shares_outstanding")),
        "forward_ebitda": _coalesce(_nested(financials,"income_statement","ebitda"), financials.get("ebitda_ttm"), income.get("ebitda")),
        "ebit": _coalesce(income.get("ebit"), income.get("operating_income")),
        "capital_expenditures": _coalesce(cash_stats.get("capital_expenditures_ttm"), _nested(cash,"investing_activities","capital_expenditures"), cash.get("capital_expenditures")),
        "depreciation_amortization": _coalesce(_nested(cash,"operating_activities","depreciation"), cash.get("depreciation_and_amortization"), cash.get("depreciation")),
        "beta": _coalesce(stock_stats.get("beta"), stats.get("beta")),
        "provider_forward_pe": valuation_stats.get("forward_pe"),
        "provider_ev_ebitda": valuation_stats.get("enterprise_to_ebitda"),
    }
    for key, value in values.items():
        if output.get(key) in (None, "", "Unavailable") and value is not None:
            output[key] = value
    profile = payload("profile")
    if isinstance(profile, Mapping):
        for target, source in (("description", "description"), ("sector", "sector"), ("industry", "industry")):
            if not output.get(target) and profile.get(source): output[target] = profile[source]
        if not output.get("security_type") and profile.get("type"): output["security_type"] = profile["type"]
    eps_est = _forward_estimate_record(payload("earnings_estimate"), "earnings_estimate")
    rev_est = _forward_estimate_record(payload("revenue_estimate"), "revenue_estimate")
    eps_records = _forward_estimate_records(payload("earnings_estimate"), "earnings_estimate")
    rev_records = _forward_estimate_records(payload("revenue_estimate"), "revenue_estimate")
    if output.get("forward_eps") is None and eps_est.get("avg_estimate") is not None:
        output["forward_eps"] = eps_est["avg_estimate"]
        output["forward_eps_period"] = eps_est.get("date")
        output["forward_eps_period_label"] = eps_est.get("period")
        output["forward_eps_period_type"] = "ANNUAL"
        output["forward_eps_basis"] = str(eps_est.get("basis") or "UNKNOWN").upper()
        output["forward_eps_source"] = "TWELVE_DATA"
    if output.get("forward_revenue") is None and rev_est.get("avg_estimate") is not None:
        output["forward_revenue"] = rev_est["avg_estimate"]
        output["forward_revenue_period"] = rev_est.get("date")
        output["forward_revenue_period_label"] = rev_est.get("period")
        output["forward_revenue_period_type"] = "ANNUAL"
        output["forward_revenue_basis"] = str(rev_est.get("basis") or "GAAP").upper()
        output["forward_revenue_source"] = "TWELVE_DATA"
    output["forward_estimate_evidence"] = {
        "eps": dict(eps_est), "revenue": dict(rev_est), "eps_periods": eps_records,
        "revenue_periods": rev_records,
        "as_of": dossier.get("observed_at"),
        "evidence_ids": tuple(dossier.get("evidence_ids") or ()),
    }
    output["financial_reporting_period"] = _coalesce(income.get("fiscal_date"), income.get("fiscal_year"), balance.get("fiscal_date"))
    output["professional_evidence_lineage"] = {
        "provider": "TWELVE_DATA", "observed_at": dossier.get("observed_at"),
        "evidence_ids": tuple(dossier.get("evidence_ids") or ()),
        "forward_eps": {"period": eps_est.get("date"), "provider_label": eps_est.get("period"), "period_type": "ANNUAL", "basis": output.get("forward_eps_basis")},
        "forward_revenue": {"period": rev_est.get("date"), "provider_label": rev_est.get("period"), "period_type": "ANNUAL", "basis": output.get("forward_revenue_basis")},
        "financial_reporting_period": output.get("financial_reporting_period"),
    }
    raw_candidates = {
        "latest_revenue": (("statistics", "statistics.financials.income_statement.revenue_ttm", income_stats.get("revenue_ttm")), ("income_statement", "income_statement[0].sales", income.get("sales"))),
        "latest_operating_income": (("income_statement", "income_statement[0].operating_income", income.get("operating_income")),),
        "operating_cash_flow": (("statistics", "statistics.financials.cash_flow.operating_cash_flow_ttm", cash_stats.get("operating_cash_flow_ttm")), ("cash_flow", "cash_flow[0].operating_activities.operating_cash_flow", _nested(cash,"operating_activities","operating_cash_flow"))),
        "free_cash_flow": (("statistics", "statistics.financials.cash_flow.levered_free_cash_flow_ttm", cash_stats.get("levered_free_cash_flow_ttm")), ("cash_flow", "cash_flow[0].free_cash_flow", cash.get("free_cash_flow"))),
        "capital_expenditures": (("statistics", "statistics.financials.cash_flow.capital_expenditures_ttm", cash_stats.get("capital_expenditures_ttm")), ("cash_flow", "cash_flow[0].investing_activities.capital_expenditures", _nested(cash,"investing_activities","capital_expenditures"))),
        "total_debt": (("statistics", "statistics.financials.balance_sheet.total_debt_mrq", balance_stats.get("total_debt_mrq")),),
        "cash_and_equivalents": (("statistics", "statistics.financials.balance_sheet.total_cash_mrq", balance_stats.get("total_cash_mrq")), ("balance_sheet", "balance_sheet[0].assets.current_assets.cash_and_cash_equivalents", _nested(balance,"assets","current_assets","cash_and_cash_equivalents"))),
        "market_cap": (("statistics", "statistics.valuations_metrics.market_capitalization", valuation_stats.get("market_capitalization")), ("statistics", "statistics.market_capitalization", stats.get("market_capitalization"))),
        "diluted_shares": (("income_statement", "income_statement[0].diluted_shares_outstanding", income.get("diluted_shares_outstanding")), ("income_statement", "income_statement[0].weighted_average_shares_diluted", income.get("weighted_average_shares_diluted")), ("statistics", "statistics.stock_statistics.shares_outstanding", stock_stats.get("shares_outstanding"))),
        "forward_ebitda": (("statistics", "statistics.financials.income_statement.ebitda", _nested(financials,"income_statement","ebitda")), ("statistics", "statistics.financials.ebitda_ttm", financials.get("ebitda_ttm")), ("income_statement", "income_statement[0].ebitda", income.get("ebitda"))),
        "ebit": (("income_statement", "income_statement[0].ebit", income.get("ebit")), ("income_statement", "income_statement[0].operating_income", income.get("operating_income"))),
    }
    field_lineage = {}
    for canonical_field, candidates in raw_candidates.items():
        normalized = output.get(canonical_field)
        selected = next(((endpoint, raw_field, raw) for endpoint, raw_field, raw in candidates if raw is not None and normalized == raw), None)
        if selected:
            endpoint, raw_field, raw = selected
            field_lineage[canonical_field] = {
                "provider": "TWELVE_DATA", "endpoint": endpoint, "raw_field": raw_field,
                "raw_value": raw, "canonical_field": canonical_field, "normalized_value": normalized,
                "ticker": str(output.get("ticker") or output.get("symbol") or "").upper(),
                "period": output.get("financial_reporting_period"), "period_type": "TTM" if raw_field.endswith("_ttm") else "REPORTED",
                "basis": "PROVIDER_REPORTED", "currency": "USD", "unit": "CURRENCY" if "shares" not in canonical_field else "SHARES",
                "as_of": dossier.get("observed_at"), "transformation": "DIRECT_MAP",
                "consuming_methodology": "ATLAS_PROFESSIONAL_VALUATION_V2",
            }
    output["professional_evidence_lineage"]["fields"] = field_lineage
    for canonical_field, endpoint, estimate in (("forward_eps", "earnings_estimate", eps_est), ("forward_revenue", "revenue_estimate", rev_est)):
        if output.get(canonical_field) is not None and estimate.get("avg_estimate") == output.get(canonical_field):
            output["professional_evidence_lineage"]["fields"][canonical_field] = {
                "provider": "TWELVE_DATA", "endpoint": endpoint,
                "raw_field": f"{endpoint}[period={estimate.get('period')}].avg_estimate",
                "raw_value": estimate.get("avg_estimate"), "canonical_field": canonical_field,
                "normalized_value": output.get(canonical_field), "ticker": str(output.get("ticker") or output.get("symbol") or "").upper(),
                "period": estimate.get("date"), "period_type": "ANNUAL", "basis": estimate.get("basis") or "UNKNOWN",
                "currency": "USD", "unit": "PER_SHARE" if canonical_field == "forward_eps" else "CURRENCY",
                "as_of": dossier.get("observed_at"), "transformation": "SELECT_NEXT_YEAR_THEN_CURRENT_YEAR",
                "consuming_methodology": "ATLAS_PROFESSIONAL_VALUATION_V2",
                "analyst_count": estimate.get("number_of_analysts") or estimate.get("analyst_count"),
            }
    output["professional_evidence_as_of"] = dossier.get("observed_at")
    output["twelve_trial_dossier"] = dict(dossier)
    output["twelve_trial_evidence_ids"] = tuple(dossier.get("evidence_ids") or ())
    output["fundamental_source"] = output.get("fundamental_source") or "TWELVE_DATA_INTERNAL_TRIAL"
    return output


__all__ = ["ENDPOINTS", "VERSION", "acquire_twelve_trial_dossiers", "normalize_trial_dossier"]
