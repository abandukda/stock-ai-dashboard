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
    reporting_date = _text(_first(row, "date", "reportingDate"))
    filing_date = _text(_first(row, "filingDate", "acceptedDate"))
    values = {
        "investor_name": _text(_first(row, "investorName", "holder", "holderName", "fundName", "name")),
        "investor_cik": _text(_first(row, "cik", "investorCik")),
        "security_symbol": _text(_first(row, "symbol", "securitySymbol")),
        "security_name": _text(_first(row, "securityName", "asset")),
        "security_cusip": _text(_first(row, "securityCusip", "cusip")),
        "shares": _number(_first(row, "sharesNumber", "shares", "numberOfShares")),
        "weight": _number(_first(row, "weight", "weightPercentage", "portfolioWeight")),
        "market_value": _number(_first(row, "marketValue", "value", "reportedValue")),
        "reporting_date": reporting_date,
        "filing_date": filing_date,
        "evidence_available_from": filing_date,
        "evidence_type": "INSTITUTIONAL_FUND_HOLDING",
    }
    available = bool(values["investor_name"] and values["security_symbol"] and filing_date)
    values["provenance"] = _provenance(
        "funds/disclosure-holders-latest", fetched_at=fetched_at,
        reporting_date=reporting_date, filing_date=filing_date, available=available,
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
    "latest_valid_transcript_period", "normalize_analyst_estimate", "normalize_fund_disclosure",
    "normalize_ratios", "normalize_transcript_period",
]
