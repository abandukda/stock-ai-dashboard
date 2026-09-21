"""Explicit unit semantics for financial ratios consumed by Atlas scoring.

Canonical scoring consumes percentage points. Provider and accounting inputs
may be ratio decimals, but conversion is driven only by the declared field or
lineage contract; value magnitude is never used to infer a unit.
"""
from __future__ import annotations

from enum import Enum
import math
from typing import Any, Mapping


CONTRACT_VERSION = "ATLAS_FINANCIAL_UNIT_CONTRACT_V1"


class FinancialUnit(str, Enum):
    RATIO_DECIMAL = "RATIO_DECIMAL"
    PERCENTAGE_POINTS = "PERCENTAGE_POINTS"
    GROWTH_PERCENT = "GROWTH_PERCENT"
    BASIS_POINTS = "BASIS_POINTS"


SCORING_UNIT = FinancialUnit.PERCENTAGE_POINTS


FIELD_ALIASES: dict[str, tuple[tuple[str, FinancialUnit], ...]] = {
    "revenue_growth_pct": (
        ("Revenue Growth", FinancialUnit.GROWTH_PERCENT),
        ("Revenue Growth %", FinancialUnit.GROWTH_PERCENT),
        ("revenue_growth", FinancialUnit.GROWTH_PERCENT),
        ("revenue_growth_pct", FinancialUnit.GROWTH_PERCENT),
        ("Revenue QoQ %", FinancialUnit.GROWTH_PERCENT),
        ("revenueGrowth", FinancialUnit.RATIO_DECIMAL),
    ),
    "eps_growth_pct": (
        ("EPS Growth", FinancialUnit.GROWTH_PERCENT),
        ("EPS Growth %", FinancialUnit.GROWTH_PERCENT),
        ("eps_growth", FinancialUnit.GROWTH_PERCENT),
        ("eps_growth_pct", FinancialUnit.GROWTH_PERCENT),
        ("earnings_growth", FinancialUnit.GROWTH_PERCENT),
        ("Earnings Growth", FinancialUnit.GROWTH_PERCENT),
        ("earningsGrowth", FinancialUnit.RATIO_DECIMAL),
    ),
    "ebitda_growth_pct": (
        ("EBITDA Growth", FinancialUnit.GROWTH_PERCENT),
        ("EBITDA Growth %", FinancialUnit.GROWTH_PERCENT),
        ("ebitda_growth_pct", FinancialUnit.GROWTH_PERCENT),
        ("ebitda_growth", FinancialUnit.GROWTH_PERCENT),
        ("ebitdaGrowth", FinancialUnit.RATIO_DECIMAL),
    ),
    "fcf_growth_pct": (
        ("FCF Growth", FinancialUnit.GROWTH_PERCENT),
        ("FCF Growth %", FinancialUnit.GROWTH_PERCENT),
        ("fcf_growth_pct", FinancialUnit.GROWTH_PERCENT),
        ("fcf_growth", FinancialUnit.GROWTH_PERCENT),
        ("freeCashFlowGrowth", FinancialUnit.RATIO_DECIMAL),
    ),
    "gross_margin_pct": (
        ("Gross Margin", FinancialUnit.PERCENTAGE_POINTS),
        ("Gross Margin %", FinancialUnit.PERCENTAGE_POINTS),
        ("gross_margin_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("gross_margin", FinancialUnit.RATIO_DECIMAL),
        ("gross_profit_margin", FinancialUnit.RATIO_DECIMAL),
        ("grossMargins", FinancialUnit.RATIO_DECIMAL),
    ),
    "operating_margin_pct": (
        ("Operating Margin", FinancialUnit.PERCENTAGE_POINTS),
        ("Operating Margin %", FinancialUnit.PERCENTAGE_POINTS),
        ("operating_margin_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("operating_margin", FinancialUnit.RATIO_DECIMAL),
        ("operating_profit_margin", FinancialUnit.RATIO_DECIMAL),
        ("operatingMargins", FinancialUnit.RATIO_DECIMAL),
    ),
    "net_margin_pct": (
        ("Net Margin", FinancialUnit.PERCENTAGE_POINTS),
        ("Net Margin %", FinancialUnit.PERCENTAGE_POINTS),
        ("net_margin_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("net_margin", FinancialUnit.RATIO_DECIMAL),
        ("net_profit_margin", FinancialUnit.RATIO_DECIMAL),
        ("profitMargins", FinancialUnit.RATIO_DECIMAL),
    ),
    "ebitda_margin_pct": (
        ("EBITDA Margin", FinancialUnit.PERCENTAGE_POINTS),
        ("ebitda_margin_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("ebitda_margin", FinancialUnit.RATIO_DECIMAL),
    ),
    "ebit_margin_pct": (
        ("EBIT Margin", FinancialUnit.PERCENTAGE_POINTS),
        ("ebit_margin_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("ebit_margin", FinancialUnit.RATIO_DECIMAL),
    ),
    "fcf_margin_pct": (
        ("FCF Margin", FinancialUnit.PERCENTAGE_POINTS),
        ("fcf_margin_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("fcf_margin", FinancialUnit.RATIO_DECIMAL),
    ),
    "roe_pct": (
        ("ROE", FinancialUnit.PERCENTAGE_POINTS),
        ("roe_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("roe", FinancialUnit.RATIO_DECIMAL),
        ("return_on_equity", FinancialUnit.RATIO_DECIMAL),
        ("returnOnEquity", FinancialUnit.RATIO_DECIMAL),
    ),
    "roa_pct": (
        ("ROA", FinancialUnit.PERCENTAGE_POINTS),
        ("roa_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("roa", FinancialUnit.RATIO_DECIMAL),
        ("return_on_assets", FinancialUnit.RATIO_DECIMAL),
        ("returnOnAssets", FinancialUnit.RATIO_DECIMAL),
    ),
    "roic_pct": (
        ("ROIC", FinancialUnit.PERCENTAGE_POINTS),
        ("roic_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("roic", FinancialUnit.RATIO_DECIMAL),
        ("return_on_invested_capital", FinancialUnit.RATIO_DECIMAL),
        ("returnOnInvestedCapital", FinancialUnit.RATIO_DECIMAL),
    ),
    "payout_ratio_pct": (
        ("Payout Ratio", FinancialUnit.PERCENTAGE_POINTS),
        ("payout_ratio_pct", FinancialUnit.PERCENTAGE_POINTS),
        ("payout_ratio", FinancialUnit.RATIO_DECIMAL),
    ),
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace("%", "").replace(",", "").strip())
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def unit(value: Any) -> FinancialUnit | None:
    try:
        return FinancialUnit(str(value or "").upper())
    except ValueError:
        return None


def convert(value: Any, *, source_unit: FinancialUnit, target_unit: FinancialUnit = SCORING_UNIT) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if source_unit == target_unit or {source_unit, target_unit} == {
        FinancialUnit.GROWTH_PERCENT, FinancialUnit.PERCENTAGE_POINTS,
    }:
        return number
    if source_unit == FinancialUnit.RATIO_DECIMAL and target_unit == FinancialUnit.PERCENTAGE_POINTS:
        return number * 100.0
    if source_unit == FinancialUnit.BASIS_POINTS and target_unit == FinancialUnit.PERCENTAGE_POINTS:
        return number / 100.0
    raise ValueError(f"unsupported financial-unit conversion: {source_unit.value} -> {target_unit.value}")


def normalize_field(
    row: Mapping[str, Any], field: str, *, lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one scoring-ready value plus auditable unit provenance."""
    aliases = FIELD_ALIASES[field]
    selected_key = None
    raw_value = None
    declared_unit = None
    for key, alias_unit in aliases:
        if key in row and row.get(key) not in (None, "", "Unavailable"):
            selected_key, raw_value, declared_unit = key, row.get(key), alias_unit
            break
    lineage_unit = unit((lineage or {}).get("scale") or (lineage or {}).get("unit"))
    source_unit = lineage_unit or declared_unit
    normalized = convert(raw_value, source_unit=source_unit) if source_unit is not None else None
    return {
        "field": field,
        "source_key": selected_key,
        "raw_value": _number(raw_value),
        "source_unit": source_unit.value if source_unit else None,
        "normalized_value": normalized,
        "normalized_unit": SCORING_UNIT.value,
        "contract_version": CONTRACT_VERSION,
    }


__all__ = [
    "CONTRACT_VERSION", "FIELD_ALIASES", "FinancialUnit", "SCORING_UNIT",
    "convert", "normalize_field", "unit",
]
