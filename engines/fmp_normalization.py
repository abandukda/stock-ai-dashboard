"""Canonical, reporting-only normalization for proven FMP stable schemas."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence


AVAILABLE = "AVAILABLE"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
PROVIDER = "FMP"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number >= 0 else None


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _provenance(
    endpoint_family: str,
    *,
    fetched_at: str | None,
    observation_date: Any = None,
    reporting_date: Any = None,
    filing_date: Any = None,
    available: bool,
) -> dict[str, Any]:
    result = {
        "provider": PROVIDER,
        "endpoint_family": endpoint_family,
        "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
        "semantic_status": AVAILABLE if available else DATA_UNAVAILABLE,
    }
    for key, value in (
        ("observation_date", observation_date),
        ("reporting_date", reporting_date),
        ("filing_date", filing_date),
    ):
        if _text(value):
            result[key] = _text(value)
    return result


def normalize_analyst_estimate(row: Mapping[str, Any], *, fetched_at: str | None = None) -> dict[str, Any]:
    """Normalize current stable names first, retaining legacy aliases.

    Fiscal-period estimates are explicitly not historical observation vintages.
    """
    values = {
        "fiscal_date": _text(_first(row, "date", "fiscalDateEnding")),
        "fiscal_period": _text(_first(row, "period", "fiscalPeriod")),
        "eps_estimate_avg": _number(_first(row, "epsAvg", "estimatedEpsAvg", "epsEstimatedAvg")),
        "eps_estimate_high": _number(_first(row, "epsHigh", "estimatedEpsHigh")),
        "eps_estimate_low": _number(_first(row, "epsLow", "estimatedEpsLow")),
        "revenue_estimate_avg": _number(_first(row, "revenueAvg", "estimatedRevenueAvg", "revenueEstimatedAvg")),
        "revenue_estimate_high": _number(_first(row, "revenueHigh", "estimatedRevenueHigh")),
        "revenue_estimate_low": _number(_first(row, "revenueLow", "estimatedRevenueLow")),
        "eps_analyst_count": _integer(_first(row, "numAnalystsEps", "numberAnalystsEstimatedEps", "numberAnalystsEstimatedEPS")),
        "revenue_analyst_count": _integer(_first(row, "numAnalystsRevenue", "numberAnalystEstimatedRevenue", "numberAnalystsEstimatedRevenue")),
        "ebit_estimate_avg": _number(_first(row, "ebitAvg", "estimatedEbitAvg", "estimatedEBITAvg")),
        "ebit_estimate_high": _number(_first(row, "ebitHigh", "estimatedEbitHigh", "estimatedEBITHigh")),
        "ebit_estimate_low": _number(_first(row, "ebitLow", "estimatedEbitLow", "estimatedEBITLow")),
        "ebitda_estimate_avg": _number(_first(row, "ebitdaAvg", "estimatedEbitdaAvg", "estimatedEBITDAAvg")),
        "ebitda_estimate_high": _number(_first(row, "ebitdaHigh", "estimatedEbitdaHigh", "estimatedEBITDAHigh")),
        "ebitda_estimate_low": _number(_first(row, "ebitdaLow", "estimatedEbitdaLow", "estimatedEBITDALow")),
        "net_income_estimate_avg": _number(_first(row, "netIncomeAvg", "estimatedNetIncomeAvg")),
        "net_income_estimate_high": _number(_first(row, "netIncomeHigh", "estimatedNetIncomeHigh")),
        "net_income_estimate_low": _number(_first(row, "netIncomeLow", "estimatedNetIncomeLow")),
        "estimate_vintage_status": "NOT_POINT_IN_TIME_VINTAGE",
    }
    available = any(value is not None for key, value in values.items() if key.endswith(("_avg", "_high", "_low", "_count")))
    values["provenance"] = _provenance(
        "analyst-estimates", fetched_at=fetched_at, observation_date=values["fiscal_date"], available=available
    )
    return values


def normalize_ratios(row: Mapping[str, Any], *, fetched_at: str | None = None) -> dict[str, Any]:
    """Return FMP ratios in provider-native decimal-ratio units.

    No percentage multiplication or heuristic scaling occurs here, preventing
    scheduled and explicit Research paths from scaling the same ratio twice.
    """
    values = {
        "return_on_equity": _number(_first(row, "returnOnEquity", "returnOnEquityRatio", "roe")),
        "return_on_assets": _number(_first(row, "returnOnAssets", "returnOnAssetsRatio", "roa")),
        "current_ratio": _number(_first(row, "currentRatio", "currentRatioTTM")),
        "gross_profit_margin": _number(_first(row, "grossProfitMargin", "grossProfitRatio")),
        "operating_profit_margin": _number(_first(row, "operatingProfitMargin", "operatingIncomeRatio")),
        "net_profit_margin": _number(_first(row, "netProfitMargin", "netIncomeRatio")),
        "debt_to_equity": _number(_first(row, "debtToEquityRatio", "debtToEquity", "debtEquityRatio")),
        "roic": _number(_first(row, "returnOnInvestedCapital", "roic")),
        "ratio_unit": "DECIMAL_RATIO",
    }
    available = any(values[key] is not None for key in values if key != "ratio_unit")
    values["provenance"] = _provenance(
        "ratios", fetched_at=fetched_at, observation_date=_first(row, "date", "fiscalDateEnding"), available=available
    )
    return values


def normalize_fund_disclosure(row: Mapping[str, Any], *, fetched_at: str | None = None) -> dict[str, Any]:
    # Stable ``funds/disclosure-holders-latest`` currently uses the
    # ``reporting*``/``filing*`` names below.  Keep the older aliases for
    # cached evidence produced before Phase 9FMP.2A.
    reporting_date = _text(_first(
        row, "dateReported", "reportingDate", "reportDate", "reportingPeriod", "periodOfReport", "date",
    ))
    filing_date = _text(_first(
        row, "filingDate", "filedAt", "acceptedDate", "acceptedAt", "filing_date",
    ))
    values = {
        "investor_name": _text(_first(
            row, "investorName", "investor", "holder", "holderName", "fundName", "entityName", "name",
        )),
        "investor_cik": _text(_first(row, "investorCik", "holderCik", "cik")),
        "security_symbol": _text(_first(row, "securitySymbol", "ticker", "symbol")),
        "security_name": _text(_first(row, "securityName", "security", "issuerName", "asset", "titleOfClass")),
        "security_cusip": _text(_first(row, "securityCusip", "cusip", "cusipNumber")),
        "shares": _number(_first(row, "sharesNumber", "shares", "numberOfShares", "sharesHeld")),
        "weight": _number(_first(
            row, "weightPercent", "weight", "weightPercentage", "portfolioWeight", "portfolioWeightPercentage",
        )),
        "market_value": _number(_first(row, "marketValue", "value", "reportedValue", "marketValueUSD")),
        "reporting_date": reporting_date,
        "filing_date": filing_date,
        "evidence_available_from": filing_date,
        "availability_limitation": None if filing_date else "FILING_DATE_UNAVAILABLE",
        "evidence_type": "INSTITUTIONAL_FUND_HOLDING",
    }
    security_identified = any(values[key] for key in ("security_symbol", "security_name", "security_cusip"))
    available = bool(values["investor_name"] and security_identified and filing_date)
    values["provenance"] = _provenance(
        "funds/disclosure-holders-latest", fetched_at=fetched_at,
        reporting_date=reporting_date, filing_date=filing_date, available=available,
    )
    return values


def normalize_institutional_ownership_summary(
    row: Mapping[str, Any], *, fetched_at: str | None = None
) -> dict[str, Any]:
    reporting_date = _text(_first(
        row, "reportingDate", "reportDate", "reportingPeriod", "periodOfReport", "date",
    ))
    filing_date = _text(_first(
        row, "filingDate", "filedAt", "acceptedDate", "acceptedAt", "filing_date",
    ))
    values = {
        "symbol": (_text(_first(row, "symbol", "ticker")) or "").upper() or None,
        "investors_holding": _integer(_first(row, "investorsHolding", "holdersCount")),
        "institutional_ownership_pct": _number(_first(row, "ownershipPercent", "institutionalOwnershipPercent")),
        "shares_held": _number(_first(row, "shares", "sharesHeld", "totalShares")),
        "reporting_date": reporting_date,
        "filing_date": filing_date,
        "evidence_available_from": filing_date,
        "availability_limitation": None if filing_date else "FILING_DATE_UNAVAILABLE",
        "evidence_type": "INSTITUTIONAL_OWNERSHIP_SUMMARY",
    }
    available = bool(values["symbol"] and filing_date and any(
        values[key] is not None for key in ("investors_holding", "institutional_ownership_pct", "shares_held")
    ))
    values["provenance"] = _provenance(
        "institutional-ownership/symbol-positions-summary", fetched_at=fetched_at,
        reporting_date=reporting_date, filing_date=filing_date, available=available,
    )
    return values


def normalize_analyst_consensus(row: Mapping[str, Any], *, fetched_at: str | None = None) -> dict[str, Any]:
    values = {
        "strong_buy": _integer(_first(row, "strongBuy", "strongBuyCount")),
        "buy": _integer(_first(row, "buy", "buyCount")),
        "hold": _integer(_first(row, "hold", "holdCount")),
        "sell": _integer(_first(row, "sell", "sellCount")),
        "strong_sell": _integer(_first(row, "strongSell", "strongSellCount")),
        "consensus": _text(_first(row, "consensus", "rating", "consensusRating")),
        "observation_date": _text(_first(row, "date", "publishedDate")),
    }
    available = bool(values["consensus"] or any(values[key] is not None for key in ("strong_buy", "buy", "hold", "sell", "strong_sell")))
    values["provenance"] = _provenance(
        "grades-consensus", fetched_at=fetched_at, observation_date=values["observation_date"], available=available
    )
    return values


def normalize_analyst_action(row: Mapping[str, Any], *, fetched_at: str | None = None) -> dict[str, Any]:
    observation_date = _text(_first(row, "date", "publishedDate"))
    values = {
        "date": observation_date,
        "firm": _text(_first(row, "gradingCompany", "firm", "company")),
        "action": _text(_first(row, "action", "gradingAction")),
        "from_grade": _text(_first(row, "previousGrade", "fromGrade")),
        "to_grade": _text(_first(row, "newGrade", "toGrade")),
    }
    available = bool(observation_date and values["firm"] and (values["action"] or values["to_grade"]))
    values["provenance"] = _provenance(
        "grades", fetched_at=fetched_at, observation_date=observation_date, available=available
    )
    return values


def normalize_price_target(
    row: Mapping[str, Any], *, endpoint_family: str, fetched_at: str | None = None
) -> dict[str, Any]:
    observation_date = _text(_first(row, "date", "publishedDate", "lastUpdated"))
    values = {
        "target_consensus": _number(_first(row, "targetConsensus", "targetMean", "consensus")),
        "target_median": _number(_first(row, "targetMedian", "medianPriceTarget")),
        "target_high": _number(_first(row, "targetHigh", "highPriceTarget")),
        "target_low": _number(_first(row, "targetLow", "lowPriceTarget")),
        "last_month_average_target": _number(row.get("lastMonthAvgPriceTarget")),
        "last_quarter_average_target": _number(row.get("lastQuarterAvgPriceTarget")),
        "last_year_average_target": _number(row.get("lastYearAvgPriceTarget")),
        "all_time_average_target": _number(row.get("allTimeAvgPriceTarget")),
        "analyst_count": _integer(_first(row, "analystCount", "numAnalysts")),
        "observation_date": observation_date,
    }
    available = any(values[key] is not None for key in (
        "target_consensus", "target_median", "target_high", "target_low",
        "last_month_average_target", "last_quarter_average_target",
        "last_year_average_target", "all_time_average_target",
    ))
    values["provenance"] = _provenance(
        endpoint_family, fetched_at=fetched_at, observation_date=observation_date, available=available
    )
    return values


def normalize_fmp_news(
    row: Mapping[str, Any], *, symbol: str, endpoint_family: str, fetched_at: str | None = None
) -> dict[str, Any]:
    published_at = _text(_first(row, "publishedDate", "date", "publishedAt"))
    values = {
        "headline": _text(_first(row, "title", "headline")),
        "source": _text(_first(row, "site", "source", "publisher")),
        "published_at": published_at,
        "url": _text(_first(row, "url", "link")),
        "ticker": str(symbol or "").strip().upper(),
        "ticker_relevance": "VERIFIED_ENTITY_MATCH",
        "provider": PROVIDER,
    }
    available = bool(values["headline"] and published_at and values["url"])
    values["provenance"] = _provenance(
        endpoint_family, fetched_at=fetched_at, observation_date=published_at, available=available
    )
    return values


def normalize_transcript_period(row: Mapping[str, Any], *, fetched_at: str | None = None) -> dict[str, Any]:
    year = _integer(_first(row, "year", "fiscalYear", "calendarYear"))
    quarter = _integer(_first(row, "quarter", "fiscalQuarter"))
    valid = bool(year and 1900 <= year <= datetime.now(timezone.utc).year + 1 and quarter in {1, 2, 3, 4})
    result = {
        "symbol": (_text(_first(row, "symbol", "ticker")) or "").upper() or None,
        "fiscal_year": year if valid else None,
        "fiscal_quarter": quarter if valid else None,
        "transcript_date": _text(_first(row, "date", "publishedDate", "transcriptDate")),
    }
    result["provenance"] = _provenance(
        "earning-call-transcript-dates", fetched_at=fetched_at,
        observation_date=result["transcript_date"], available=valid,
    )
    return result


def latest_valid_transcript_period(rows: Sequence[Mapping[str, Any]], *, fetched_at: str | None = None) -> dict[str, Any] | None:
    normalized = [normalize_transcript_period(row, fetched_at=fetched_at) for row in rows if isinstance(row, Mapping)]
    valid = [row for row in normalized if row["fiscal_year"] is not None and row["fiscal_quarter"] is not None]
    if not valid:
        return None
    return max(valid, key=lambda row: (row["fiscal_year"], row["fiscal_quarter"], row.get("transcript_date") or ""))


__all__ = [
    "latest_valid_transcript_period", "normalize_analyst_action", "normalize_analyst_consensus",
    "normalize_analyst_estimate", "normalize_fmp_news", "normalize_fund_disclosure",
    "normalize_institutional_ownership_summary", "normalize_price_target", "normalize_ratios",
    "normalize_transcript_period",
]
