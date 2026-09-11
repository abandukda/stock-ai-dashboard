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
from services.evidence_lineage_governance import CACHE_GENERATION_VERSION, PROVIDER_ARCHITECTURE_VERSION
from services.live_market.twelve_data_phase1 import REST_BASE, load_twelve_data_setting, normalize_ticker


VERSION = "TWELVE_DATA_INTERNAL_TRIAL_INTELLIGENCE_V1"
ENDPOINTS = (
    "profile", "statistics", "income_statement", "balance_sheet", "cash_flow",
    "earnings", "earnings_estimate", "revenue_estimate", "eps_trend",
    "price_target", "recommendations", "analyst_ratings/light",
    "insider_transactions", "institutional_holders", "press_releases",
    "splits", "dividends", "etf",
)
# Provider capability inventory is deliberately separate from canonical
# valuation.  "Mapped" means normalized into governed contextual evidence in
# this module; it does not authorize commercial display by itself.
TWELVE_ANALYST_FIELD_INVENTORY = {
    "consensus_price_target_mean": "SUPPORTED_AND_MAPPED",
    "consensus_price_target_median": "SUPPORTED_AND_MAPPED",
    "target_high": "SUPPORTED_AND_MAPPED",
    "target_low": "SUPPORTED_AND_MAPPED",
    "analyst_coverage_count": "SUPPORTED_AND_MAPPED",
    "recommendation_consensus": "SUPPORTED_AND_MAPPED",
    "recommendation_distribution": "SUPPORTED_AND_MAPPED",
    "individual_analyst_actions": "SUPPORTED_AND_MAPPED",
    "price_target_changes": "SUPPORTED_NOT_MAPPED",
    "forward_eps_consensus": "SUPPORTED_AND_MAPPED",
    "forward_revenue_consensus": "SUPPORTED_AND_MAPPED",
    "estimate_revisions_7_30_90d": "SUPPORTED_AND_MAPPED",
}
CANONICAL_QUANTITATIVE_FIELDS = (
    "revenue_growth", "earnings_growth", "gross_profit", "gross_profit_margin",
    "operating_profit_margin", "latest_revenue", "latest_eps", "latest_operating_income",
    "net_income", "operating_cash_flow", "capital_expenditures", "free_cash_flow",
    "provider_defined_fcf", "normalized_fcf", "cash_and_equivalents", "total_debt",
    "total_equity", "current_assets", "current_liabilities", "current_ratio",
    "market_cap", "current_shares_outstanding", "basic_shares", "diluted_shares",
    "forward_eps", "forward_revenue", "forward_ebitda", "ebit",
    "depreciation_amortization", "beta", "provider_forward_pe", "provider_ev_ebitda",
)


def _evidence_id(symbol: str, family: str, observed: str) -> str:
    digest = hashlib.sha256(f"{symbol}|{family}|{observed}".encode()).hexdigest()[:20]
    return f"TDTRIAL-{digest}"


def acquire_twelve_trial_dossiers(
    symbols: Sequence[str], *, get: Callable[..., Any] = requests.get,
    secrets: Mapping[str, Any] | None = None, environ: Mapping[str, str] | None = None,
    max_workers: int = 6, timeout: float = 12, endpoints: Sequence[str] = ENDPOINTS,
    evidence_cache: dict[tuple[str, str, str, str], Mapping[str, Any]] | None = None,
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
    cache = evidence_cache if evidence_cache is not None else {}
    cache_hits = 0

    def fetch(symbol: str, family: str) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        try:
            response = get(f"{REST_BASE}/{family}", params={"symbol": symbol}, headers={"Authorization": f"apikey {key}"}, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            error = isinstance(payload, Mapping) and str(payload.get("status") or "").lower() == "error"
            envelope = {
                "status": "DATA_UNAVAILABLE" if error else "AVAILABLE", "provider": "TWELVE_DATA",
                "provider_architecture_version": PROVIDER_ARCHITECTURE_VERSION,
                "cache_generation_version": CACHE_GENERATION_VERSION,
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
        futures = []
        for symbol in clean:
            for family in selected:
                cache_key = (CACHE_GENERATION_VERSION, VERSION, symbol, family)
                cached = cache.get(cache_key)
                if cached and cached.get("status") == "AVAILABLE":
                    dossiers[symbol]["families"][family] = dict(cached)
                    cache_hits += 1
                else:
                    futures.append(pool.submit(fetch, symbol, family))
        for future in as_completed(futures):
            symbol, family, envelope, meta = future.result()
            dossiers[symbol]["families"][family] = envelope
            if envelope.get("status") == "AVAILABLE":
                cache[(CACHE_GENERATION_VERSION, VERSION, symbol, family)] = dict(envelope)
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
        "cache_hits": cache_hits, "cache_misses": len(telemetry), "calls_avoided": cache_hits,
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


def _missing_label(value: Any) -> bool:
    return value is None or str(value).strip().upper() in {"", "UNKNOWN", "UNAVAILABLE", "N/A", "NONE"}


def _same_statement_operating_margin(income: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a textbook operating margin only for a comparable statement pair."""
    period = _coalesce(income.get("fiscal_date"), income.get("date"), income.get("fiscal_year"))
    revenue = _coalesce(income.get("sales"), income.get("revenue"))
    operating_income = income.get("operating_income")
    shared_currency = _coalesce(income.get("currency"), income.get("reported_currency"))
    revenue_currency = _coalesce(income.get("sales_currency"), income.get("revenue_currency"), shared_currency)
    operating_currency = _coalesce(income.get("operating_income_currency"), shared_currency)
    shared_unit = _coalesce(income.get("unit"), income.get("scale"))
    revenue_unit = _coalesce(income.get("sales_unit"), income.get("revenue_unit"), shared_unit)
    operating_unit = _coalesce(income.get("operating_income_unit"), shared_unit)
    if not period or revenue in (None, 0) or operating_income is None:
        return None
    if revenue_currency and operating_currency and revenue_currency != operating_currency:
        return None
    if revenue_unit and operating_unit and revenue_unit != operating_unit:
        return None
    try:
        revenue_value = float(revenue)
        operating_value = float(operating_income)
        margin = operating_value / revenue_value
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return {
        "margin": margin,
        "revenue": revenue_value,
        "operating_income": operating_value,
        "period": period,
        "period_type": str(income.get("period") or "REPORTED").upper(),
        "basis": str(income.get("basis") or "PROVIDER_REPORTED").upper(),
        "currency": revenue_currency or operating_currency or "UNKNOWN",
        "unit": revenue_unit or operating_unit or "PROVIDER_REPORTED",
    }


def normalize_trial_dossier(row: Mapping[str, Any], dossier: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize canonical quantitative fields solely from Twelve evidence."""
    output = dict(row)
    for field in CANONICAL_QUANTITATIVE_FIELDS:
        output.pop(field, None)
        for suffix in ("_source", "_lineage", "_period", "_period_type", "_basis", "_evidence_id", "_observed_at", "_freshness"):
            output.pop(f"{field}{suffix}", None)
    output.pop("approved_secondary_valuation_inputs", None)
    output.pop("fundamentals_provenance", None)
    families = dossier.get("families") if isinstance(dossier.get("families"), Mapping) else {}
    payload = lambda family: (families.get(family) or {}).get("payload") or {}
    fetched_at = lambda family: (families.get(family) or {}).get("observed_at")
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
    statement_margin = _same_statement_operating_margin(income)
    provider_operating_margin = _pct(financials.get("operating_margin"))
    stats_ocf = cash_stats.get("operating_cash_flow_ttm")
    stats_capex = cash_stats.get("capital_expenditures_ttm")
    statement_ocf = _nested(cash, "operating_activities", "operating_cash_flow")
    statement_capex = _coalesce(_nested(cash, "investing_activities", "capital_expenditures"), cash.get("capital_expenditures"), cash.get("capital_expenditure"))
    cash_flow_pair_compatible = False
    if stats_ocf is not None and stats_capex is not None:
        canonical_ocf, canonical_capex, cash_period, cash_period_type = stats_ocf, stats_capex, "TTM", "TTM"
        cash_evidence_endpoint = "statistics"
        cash_flow_pair_compatible = True
    elif statement_ocf is not None and statement_capex is not None:
        canonical_ocf, canonical_capex = statement_ocf, statement_capex
        cash_period = _coalesce(cash.get("fiscal_date"), cash.get("date"), cash.get("fiscal_year"))
        cash_period_type = str(cash.get("period") or "REPORTED").upper()
        cash_evidence_endpoint = "cash_flow"
        cash_flow_pair_compatible = True
    else:
        canonical_ocf = _coalesce(stats_ocf, statement_ocf)
        canonical_capex = _coalesce(stats_capex, statement_capex)
        cash_period = "TTM" if stats_ocf is not None or stats_capex is not None else _coalesce(cash.get("fiscal_date"), cash.get("date"), cash.get("fiscal_year"))
        cash_period_type = "TTM" if cash_period == "TTM" else str(cash.get("period") or "REPORTED").upper()
        cash_evidence_endpoint = "statistics" if stats_ocf is not None or stats_capex is not None else "cash_flow"
    values = {
        "revenue_growth": _pct(income_stats.get("quarterly_revenue_growth")),
        "earnings_growth": _pct(income_stats.get("quarterly_earnings_growth_yoy")),
        "operating_profit_margin": statement_margin["margin"] if statement_margin else provider_operating_margin,
        "free_cash_flow": None,
        "current_ratio": balance_stats.get("current_ratio_mrq"),
        "latest_revenue": statement_margin["revenue"] if statement_margin else _coalesce(income_stats.get("revenue_ttm"), income.get("sales")),
        "gross_profit": _coalesce(income_stats.get("gross_profit_ttm"), income.get("gross_profit")),
        "latest_eps": _coalesce(income.get("diluted_eps"), income.get("eps_diluted"), income.get("eps")),
        "latest_operating_income": statement_margin["operating_income"] if statement_margin else income.get("operating_income"),
        "net_income": income.get("net_income"),
        "operating_cash_flow": canonical_ocf,
        "total_debt": _coalesce(balance_stats.get("total_debt_mrq"), _nested(balance, "liabilities", "current_liabilities", "short_term_debt") if _nested(balance, "liabilities", "non_current_liabilities", "long_term_debt") is None else (_nested(balance, "liabilities", "current_liabilities", "short_term_debt") or 0) + (_nested(balance, "liabilities", "non_current_liabilities", "long_term_debt") or 0)),
        "cash_and_equivalents": _coalesce(balance_stats.get("total_cash_mrq"), _nested(balance, "assets", "current_assets", "cash_and_cash_equivalents")),
        "total_equity": _coalesce(balance_stats.get("total_stockholders_equity_mrq"), _nested(balance, "shareholders_equity", "total_shareholders_equity")),
        "current_assets": _coalesce(balance_stats.get("total_current_assets_mrq"), _nested(balance, "assets", "current_assets", "total_current_assets")),
        "current_liabilities": _coalesce(balance_stats.get("total_current_liabilities_mrq"), _nested(balance, "liabilities", "current_liabilities", "total_current_liabilities")),
        "market_cap": _coalesce(valuation_stats.get("market_capitalization"), stats.get("market_capitalization"), stats.get("market_cap")),
        "diluted_shares": _coalesce(income.get("diluted_shares_outstanding"), income.get("weighted_average_shares_diluted"), income.get("diluted_average_shares"), stock_stats.get("shares_outstanding")),
        "basic_shares": _coalesce(income.get("basic_shares_outstanding"), stock_stats.get("shares_outstanding")),
        "current_shares_outstanding": stock_stats.get("shares_outstanding"),
        "forward_ebitda": _coalesce(_nested(financials,"income_statement","ebitda"), financials.get("ebitda_ttm"), income.get("ebitda")),
        "ebit": _coalesce(income.get("ebit"), income.get("operating_income")),
        "capital_expenditures": canonical_capex,
        "depreciation_amortization": _coalesce(_nested(cash,"operating_activities","depreciation"), cash.get("depreciation_and_amortization"), cash.get("depreciation")),
        "beta": _coalesce(stock_stats.get("beta"), stats.get("beta")),
        "provider_forward_pe": valuation_stats.get("forward_pe"),
        "provider_ev_ebitda": valuation_stats.get("enterprise_to_ebitda"),
    }
    twelve_populated_fields = set()
    for key, value in values.items():
        if value is not None:
            output[key] = value
            twelve_populated_fields.add(key)
    provider_fcf = _coalesce(cash_stats.get("levered_free_cash_flow_ttm"), cash.get("free_cash_flow"))
    output["provider_defined_fcf"] = provider_fcf
    output["provider_defined_operating_profit_margin"] = provider_operating_margin
    if statement_margin:
        output["historical_operating_margin"] = statement_margin["margin"]
        output["operating_margin_lineage"] = {
            "provider": "TWELVE_DATA", "endpoint": "income_statement",
            "numerator_raw_field": "income_statement[0].operating_income",
            "numerator_raw_value": statement_margin["operating_income"],
            "denominator_raw_field": "income_statement[0].sales",
            "denominator_raw_value": statement_margin["revenue"],
            "numerator_period": statement_margin["period"],
            "denominator_period": statement_margin["period"],
            "period_type": statement_margin["period_type"], "basis": statement_margin["basis"],
            "currency": statement_margin["currency"], "scale": "RATIO_DECIMAL",
            "numerator_currency": statement_margin["currency"],
            "denominator_currency": statement_margin["currency"],
            "numerator_unit": statement_margin["unit"], "denominator_unit": statement_margin["unit"],
            "comparable": True,
            "transformation": "OPERATING_INCOME_DIVIDED_BY_REVENUE",
            "evidence_id": (families.get("income_statement") or {}).get("evidence_id"),
        }
    statement_period = cash_period
    try:
        if not cash_flow_pair_compatible:
            raise ValueError("cash-flow period mismatch")
        ocf_value = float(output["operating_cash_flow"])
        capex_value = float(output["capital_expenditures"])
        canonical_fcf = ocf_value - abs(capex_value)
        output["normalized_fcf"] = canonical_fcf
        output["free_cash_flow"] = canonical_fcf
        output["free_cash_flow_period"] = statement_period
        output["free_cash_flow_period_type"] = cash_period_type
        output["free_cash_flow_basis"] = "OCF_MINUS_ABS_CAPEX"
    except (KeyError, TypeError, ValueError):
        output.pop("free_cash_flow", None)
    profile = payload("profile")
    if isinstance(profile, Mapping):
        for target, source in (("description", "description"), ("sector", "sector"), ("industry", "industry")):
            if _missing_label(output.get(target)) and not _missing_label(profile.get(source)):
                output[target] = profile[source]
                output[f"{target}_lineage"] = {
                    "provider": "TWELVE_DATA", "endpoint": "profile",
                    "evidence_id": ((families.get("profile") or {}).get("evidence_id")),
                    "as_of": ((families.get("profile") or {}).get("observed_at")),
                    "authority_order": "PRIMARY_PROFILE_SOURCE",
                }
        if _missing_label(output.get("security_type")) and not _missing_label(profile.get("type")):
            output["security_type"] = profile["type"]
    eps_est = _forward_estimate_record(payload("earnings_estimate"), "earnings_estimate")
    rev_est = _forward_estimate_record(payload("revenue_estimate"), "revenue_estimate")
    eps_records = _forward_estimate_records(payload("earnings_estimate"), "earnings_estimate")
    rev_records = _forward_estimate_records(payload("revenue_estimate"), "revenue_estimate")
    target = payload("price_target").get("price_target") if isinstance(payload("price_target"), Mapping) else {}
    target = target if isinstance(target, Mapping) else {}
    recommendations_payload = payload("recommendations")
    trends = recommendations_payload.get("trends") if isinstance(recommendations_payload, Mapping) else {}
    current_recommendations = trends.get("current_month") if isinstance(trends, Mapping) else {}
    current_recommendations = current_recommendations if isinstance(current_recommendations, Mapping) else {}
    eps_trend = _forward_estimate_record(payload("eps_trend"), "eps_trend")
    for canonical, raw in (
        ("analyst_target_mean", "average"), ("analyst_target_median", "median"),
        ("analyst_target_low", "low"), ("analyst_target_high", "high"),
    ):
        if target.get(raw) is not None:
            output[canonical] = target[raw]
            output[f"{canonical}_source"] = "TWELVE_DATA"
            output[f"{canonical}_evidence_id"] = (families.get("price_target") or {}).get("evidence_id")
            output[f"{canonical}_observed_at"] = fetched_at("price_target")
    recommendation_counts = {}
    for field in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
        if current_recommendations.get(field) is not None:
            output[field] = current_recommendations[field]
            recommendation_counts[field] = current_recommendations[field]
    if len(recommendation_counts) == 5:
        output["analyst_count"] = sum(int(value) for value in recommendation_counts.values())
        output["analyst_count_source"] = "TWELVE_DATA_RECOMMENDATION_RESPONSE_COUNT"
        output["analyst_coverage_evidence_id"] = (families.get("recommendations") or {}).get("evidence_id")
    rating = recommendations_payload.get("rating") if isinstance(recommendations_payload, Mapping) else None
    try:
        rating_number = float(rating)
        output["recommendation_key"] = "strong_buy" if rating_number >= 8 else "buy" if rating_number >= 6 else "hold" if rating_number >= 4 else "sell" if rating_number >= 2 else "strong_sell"
        output["recommendation_rating_score"] = rating_number
    except (TypeError, ValueError):
        pass
    output["wall_street_evidence_lineage"] = {
        "provider": "TWELVE_DATA",
        "price_target": {"endpoint": "price_target", "raw_fields": ("average", "median", "low", "high", "current"), "evidence_id": (families.get("price_target") or {}).get("evidence_id"), "as_of": fetched_at("price_target")},
        "recommendations": {"endpoint": "recommendations", "raw_field": "trends.current_month", "evidence_id": (families.get("recommendations") or {}).get("evidence_id"), "as_of": fetched_at("recommendations")},
        "non_scoring": True,
    }
    if eps_trend.get("current_estimate") is not None:
        output["estimate_revision_history"] = {
            "period": eps_trend.get("date"), "period_label": eps_trend.get("period"),
            "current_eps_estimate": eps_trend.get("current_estimate"),
            "eps_7d_ago": eps_trend.get("7_days_ago"), "eps_30d_ago": eps_trend.get("30_days_ago"),
            "eps_90d_ago": eps_trend.get("90_days_ago"),
            "provider": "TWELVE_DATA", "endpoint": "eps_trend",
            "evidence_id": (families.get("eps_trend") or {}).get("evidence_id"), "as_of": fetched_at("eps_trend"),
        }
        for days in (7, 30, 90):
            prior = eps_trend.get(f"{days}_days_ago")
            try:
                output[f"eps_revision_{days}d"] = round((float(eps_trend["current_estimate"]) - float(prior)) / abs(float(prior)) * 100, 2) if float(prior) != 0 else None
            except (TypeError, ValueError):
                output[f"eps_revision_{days}d"] = None
    ratings_payload = payload("analyst_ratings/light")
    ratings = ratings_payload.get("ratings") if isinstance(ratings_payload, Mapping) else None
    if isinstance(ratings, list):
        output["analyst_actions"] = tuple({
            "date": item.get("date"), "firm": item.get("firm"),
            "rating_action": item.get("rating_change"), "current_rating": item.get("rating_current"),
            "previous_rating": item.get("rating_prior"), "provider": "TWELVE_DATA",
            "evidence_id": (families.get("analyst_ratings/light") or {}).get("evidence_id"),
            "observed_at": fetched_at("analyst_ratings/light"),
        } for item in ratings if isinstance(item, Mapping))
    if eps_est.get("avg_estimate") is not None:
        output["forward_eps"] = eps_est["avg_estimate"]
        output["forward_eps_period"] = eps_est.get("date")
        output["forward_eps_period_label"] = eps_est.get("period")
        output["forward_eps_period_type"] = "ANNUAL"
        output["forward_eps_basis"] = str(eps_est.get("basis") or "UNKNOWN").upper()
        output["forward_eps_source"] = "TWELVE_DATA"
        output["forward_eps_observed_at"] = fetched_at("earnings_estimate")
        output["forward_eps_evidence_id"] = (families.get("earnings_estimate") or {}).get("evidence_id")
        output["forward_eps_freshness"] = "OBSERVED_AT_RECORDED"
    if rev_est.get("avg_estimate") is not None:
        output["forward_revenue"] = rev_est["avg_estimate"]
        output["forward_revenue_period"] = rev_est.get("date")
        output["forward_revenue_period_label"] = rev_est.get("period")
        output["forward_revenue_period_type"] = "ANNUAL"
        output["forward_revenue_basis"] = str(rev_est.get("basis") or "GAAP").upper()
        output["forward_revenue_source"] = "TWELVE_DATA"
    output["forward_estimate_evidence"] = {
        "eps": dict(eps_est), "revenue": dict(rev_est), "eps_periods": eps_records,
        "revenue_periods": rev_records,
        "as_of": max((value for value in (fetched_at("earnings_estimate"),fetched_at("revenue_estimate")) if value),default=None),
        "evidence_ids": tuple(dossier.get("evidence_ids") or ()),
    }
    output["financial_reporting_period"] = _coalesce(income.get("fiscal_date"), income.get("fiscal_year"), balance.get("fiscal_date"))
    output["professional_evidence_lineage"] = {
        "provider": "TWELVE_DATA", "observed_at": max((value for value in (fetched_at(name) for name in families) if value),default=None),
        "evidence_ids": tuple(dossier.get("evidence_ids") or ()),
        "forward_eps": {"period": eps_est.get("date"), "provider_label": eps_est.get("period"), "period_type": "ANNUAL", "basis": output.get("forward_eps_basis")},
        "forward_revenue": {"period": rev_est.get("date"), "provider_label": rev_est.get("period"), "period_type": "ANNUAL", "basis": output.get("forward_revenue_basis")},
        "financial_reporting_period": output.get("financial_reporting_period"),
    }
    raw_candidates = {
        "latest_revenue": (("statistics", "statistics.financials.income_statement.revenue_ttm", income_stats.get("revenue_ttm")), ("income_statement", "income_statement[0].sales", income.get("sales"))),
        "latest_operating_income": (("income_statement", "income_statement[0].operating_income", income.get("operating_income")),),
        "operating_cash_flow": (("statistics", "statistics.financials.cash_flow.operating_cash_flow_ttm", cash_stats.get("operating_cash_flow_ttm")), ("cash_flow", "cash_flow[0].operating_activities.operating_cash_flow", _nested(cash,"operating_activities","operating_cash_flow"))),
        "free_cash_flow": (),
        "capital_expenditures": (("statistics", "statistics.financials.cash_flow.capital_expenditures_ttm", cash_stats.get("capital_expenditures_ttm")), ("cash_flow", "cash_flow[0].investing_activities.capital_expenditures", _nested(cash,"investing_activities","capital_expenditures")), ("cash_flow", "cash_flow[0].capital_expenditure", cash.get("capital_expenditure"))),
        "total_debt": (("statistics", "statistics.financials.balance_sheet.total_debt_mrq", balance_stats.get("total_debt_mrq")),),
        "cash_and_equivalents": (("statistics", "statistics.financials.balance_sheet.total_cash_mrq", balance_stats.get("total_cash_mrq")), ("balance_sheet", "balance_sheet[0].assets.current_assets.cash_and_cash_equivalents", _nested(balance,"assets","current_assets","cash_and_cash_equivalents"))),
        "market_cap": (("statistics", "statistics.valuations_metrics.market_capitalization", valuation_stats.get("market_capitalization")), ("statistics", "statistics.market_capitalization", stats.get("market_capitalization"))),
        "diluted_shares": (("income_statement", "income_statement[0].diluted_shares_outstanding", income.get("diluted_shares_outstanding")), ("income_statement", "income_statement[0].weighted_average_shares_diluted", income.get("weighted_average_shares_diluted")), ("statistics", "statistics.stock_statistics.shares_outstanding", stock_stats.get("shares_outstanding"))),
        "current_shares_outstanding": (("statistics", "statistics.stock_statistics.shares_outstanding", stock_stats.get("shares_outstanding")),),
        "forward_ebitda": (("statistics", "statistics.financials.income_statement.ebitda", _nested(financials,"income_statement","ebitda")), ("statistics", "statistics.financials.ebitda_ttm", financials.get("ebitda_ttm")), ("income_statement", "income_statement[0].ebitda", income.get("ebitda"))),
        "ebit": (("income_statement", "income_statement[0].ebit", income.get("ebit")), ("income_statement", "income_statement[0].operating_income", income.get("operating_income"))),
        "provider_ev_ebitda": (("statistics", "statistics.valuations_metrics.enterprise_to_ebitda", valuation_stats.get("enterprise_to_ebitda")),),
        "provider_forward_pe": (("statistics", "statistics.valuations_metrics.forward_pe", valuation_stats.get("forward_pe")),),
    }
    field_lineage = {}
    for canonical_field, candidates in raw_candidates.items():
        normalized = output.get(canonical_field)
        selected = next(((endpoint, raw_field, raw) for endpoint, raw_field, raw in candidates if canonical_field in twelve_populated_fields and raw is not None and normalized == raw), None)
        if selected:
            endpoint, raw_field, raw = selected
            is_cash_component = canonical_field in {"operating_cash_flow", "capital_expenditures"}
            field_lineage[canonical_field] = {
                "provider": "TWELVE_DATA", "endpoint": endpoint, "raw_field": raw_field,
                "raw_value": raw, "canonical_field": canonical_field, "normalized_value": normalized,
                "ticker": str(output.get("ticker") or output.get("symbol") or "").upper(),
                "period": cash_period if is_cash_component else ("TTM" if raw_field.endswith("_ttm") else output.get("financial_reporting_period")),
                "period_type": cash_period_type if is_cash_component else ("TTM" if raw_field.endswith("_ttm") else "REPORTED"),
                "basis": "PROVIDER_REPORTED", "currency": "USD", "unit": "CURRENCY" if "shares" not in canonical_field else "SHARES",
                "provider_fetched_at":fetched_at(endpoint),"evidence_as_of":fetched_at(endpoint),
                "as_of": fetched_at(endpoint), "as_of_semantics":"CURRENT_PROVIDER_STATISTIC_OBSERVED_AT_FETCH" if endpoint=="statistics" else "PROVIDER_STATEMENT_OBSERVATION",
                "evidence_id":(families.get(endpoint) or {}).get("evidence_id"),"transformation": "DIRECT_MAP",
                "consuming_methodology": "ATLAS_PROFESSIONAL_VALUATION_V2",
            }
    output["professional_evidence_lineage"]["fields"] = field_lineage
    if output.get("free_cash_flow") is not None:
        output["professional_evidence_lineage"]["fields"]["free_cash_flow"] = {
            "provider": "ATLAS_CALCULATED", "endpoint": "cash_flow", "raw_field": "operating_cash_flow,capital_expenditures",
            "raw_value": {"operating_cash_flow": output.get("operating_cash_flow"), "capital_expenditures": output.get("capital_expenditures")},
            "canonical_field": "free_cash_flow", "normalized_value": output.get("free_cash_flow"),
            "canonical_value": output.get("free_cash_flow"),
            "ticker": str(output.get("ticker") or output.get("symbol") or "").upper(), "period": statement_period,
            "period_type": cash_period_type, "basis": "OCF_MINUS_ABS_CAPEX", "currency": "USD", "unit": "CURRENCY",
            "provider_fetched_at":fetched_at(cash_evidence_endpoint),
            "evidence_as_of":fetched_at(cash_evidence_endpoint),
            "as_of": fetched_at(cash_evidence_endpoint), "transformation": "OCF_MINUS_ABS_CAPEX",
            "evidence_ids": tuple(dossier.get("evidence_ids") or ()), "consuming_methodology": "ATLAS_PROFESSIONAL_VALUATION_V2",
        }
    output["professional_evidence_lineage"]["preexisting_fields_not_attributed_to_twelve"] = sorted(
        key for key, value in values.items() if value is not None and key not in twelve_populated_fields
    )
    for canonical_field, endpoint, estimate in (("forward_eps", "earnings_estimate", eps_est), ("forward_revenue", "revenue_estimate", rev_est)):
        if output.get(canonical_field) is not None and estimate.get("avg_estimate") == output.get(canonical_field):
            output["professional_evidence_lineage"]["fields"][canonical_field] = {
                "provider": "TWELVE_DATA", "endpoint": endpoint,
                "raw_field": f"{endpoint}[period={estimate.get('period')}].avg_estimate",
                "raw_value": estimate.get("avg_estimate"), "canonical_field": canonical_field,
                "normalized_value": output.get(canonical_field), "ticker": str(output.get("ticker") or output.get("symbol") or "").upper(),
                "period": estimate.get("date"), "period_type": "ANNUAL", "basis": estimate.get("basis") or "UNKNOWN",
                "currency": "USD", "unit": "PER_SHARE" if canonical_field == "forward_eps" else "CURRENCY",
                "provider_fetched_at":fetched_at(endpoint),"evidence_as_of":fetched_at(endpoint),
                "as_of": fetched_at(endpoint), "transformation": "SELECT_NEXT_YEAR_THEN_CURRENT_YEAR",
                "consuming_methodology": "ATLAS_PROFESSIONAL_VALUATION_V2",
                "analyst_count": estimate.get("number_of_analysts") or estimate.get("analyst_count"),
            }
    # Current valuation multiples have no provider fiscal date. Their governed
    # evidence timestamp is the statistics-envelope observation time, distinct
    # from statement period ends and the later valuation calculation time.
    output["professional_evidence_as_of"] = fetched_at("statistics")
    output["professional_evidence_fetched_at"] = fetched_at("statistics")
    output["twelve_trial_dossier"] = dict(dossier)
    output["twelve_trial_evidence_ids"] = tuple(dossier.get("evidence_ids") or ())
    output["fundamental_source"] = "TWELVE_DATA_INTERNAL_TRIAL"
    from services.context_evidence import materialize_context_evidence
    from services.share_structure_governance import materialize_share_bridge
    output = materialize_share_bridge(output)
    return materialize_context_evidence(output, families)


__all__ = ["CANONICAL_QUANTITATIVE_FIELDS", "ENDPOINTS", "TWELVE_ANALYST_FIELD_INVENTORY", "VERSION", "acquire_twelve_trial_dossiers", "normalize_trial_dossier"]
