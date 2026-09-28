"""Deterministic normalization of Finnhub reported facts for shadow comparison."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


VALID_NUMERIC_FACT = "VALID_NUMERIC_FACT"
MISSING_PROVIDER_FACT = "MISSING_PROVIDER_FACT"
NONNUMERIC_PROVIDER_VALUE = "NONNUMERIC_PROVIDER_VALUE"
_MISSING_TEXT = frozenset({"", "N/A", "NA", "NAN", "NULL", "-"})


CONCEPTS = {
    # ``Revenues`` is the SEC total-revenue concept.  Some issuers (for example
    # pharma issuers with alliance revenue) also report a narrower contract-
    # revenue component, so the total concept must win when both are present.
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "cost_of_revenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    "ebit": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "debt_current": ("DebtCurrent", "ShortTermBorrowings", "LongTermDebtCurrent", "ShortTermDebtCurrent"),
    "debt_long_term": ("LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
    "shares_outstanding": ("CommonStockSharesOutstanding",),
    "weighted_average_shares_basic": ("WeightedAverageNumberOfSharesOutstandingBasic",),
    "weighted_average_shares_diluted": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}


def canonical_period(report: Mapping[str, Any]) -> str | None:
    try:
        number = int(report.get("quarter"))
    except (TypeError, ValueError):
        number = -1
    if number == 0 or str(report.get("form") or "").upper() in {"10-K", "20-F", "40-F"}:
        return "FY"
    return f"Q{number}" if number in {1, 2, 3, 4} else None


def currency_from_facts(facts: Sequence[Mapping[str, Any]]) -> str | None:
    units = {str(f.get("unit") or "").lower() for f in facts}
    return "USD" if units & {"usd", "u_usd"} else None


def safe_numeric(value: Any) -> tuple[float | None, str]:
    """Return a finite provider number or classify it as missing evidence."""
    if value is None:
        return None, MISSING_PROVIDER_FACT
    if isinstance(value, bool):
        return None, NONNUMERIC_PROVIDER_VALUE
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.upper() in _MISSING_TEXT:
            return None, MISSING_PROVIDER_FACT if not candidate else NONNUMERIC_PROVIDER_VALUE
        value = candidate
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, NONNUMERIC_PROVIDER_VALUE
    if not math.isfinite(number):
        return None, NONNUMERIC_PROVIDER_VALUE
    return number, VALID_NUMERIC_FACT


def canonical_financial_facts(
    facts: Sequence[Mapping[str, Any]], report: Mapping[str, Any],
    *, diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_concept = {
        str(f.get("concept") or "").split("_")[-1]: f
        for f in facts if str(f.get("concept") or "").strip()
    }
    selected: dict[str, Mapping[str, Any] | None] = {}
    observations = diagnostics if diagnostics is not None else []

    def select(name: str, concepts: Sequence[str] | None = None) -> Mapping[str, Any] | None:
        if name in selected:
            return selected[name]
        candidates = tuple(concepts or CONCEPTS[name])
        observed = False
        for concept in candidates:
            fact = by_concept.get(concept)
            if fact is None:
                continue
            observed = True
            number, classification = safe_numeric(fact.get("value"))
            observations.append({
                "canonical_field": name, "source_concept": str(fact.get("concept") or concept),
                "raw_value_classification": classification,
            })
            if classification == VALID_NUMERIC_FACT:
                selected[name] = {**fact, "value": number}
                return selected[name]
        if not observed:
            observations.append({
                "canonical_field": name, "source_concept": None,
                "raw_value_classification": MISSING_PROVIDER_FACT,
            })
        selected[name] = None
        return None
    period = canonical_period(report)
    currency = report.get("currency") or currency_from_facts(facts)
    result: dict[str, Any] = {}
    for name in (
        "revenue", "gross_profit", "cost_of_revenue", "ebit", "net_income", "cash",
        "operating_cash_flow", "capex", "shares_outstanding",
        "weighted_average_shares_basic", "weighted_average_shares_diluted",
    ):
        fact = select(name)
        if fact:
            result[name] = _envelope(name, fact, report, period, currency)
    current, long_term = select("debt_current"), select("debt_long_term")
    if current or long_term:
        total = sum(float(item.get("value") or 0) for item in (current, long_term) if item)
        result["total_debt"] = {
            "value": total, "source_fields": [str(item.get("concept")) for item in (current, long_term) if item],
            "source_unit": (current or long_term).get("unit"), "normalized_unit": currency,
            "source_period": report.get("quarter"), "canonical_period": period,
            "period_end": report.get("endDate"), "currency": currency, "scale_transformation": "NONE",
            "effective_date": report.get("endDate"), "filed_date": report.get("filedDate"),
            "source_record_version": report.get("accessNumber"), "restatement_status": "UNRESOLVED",
        }
    if result.get("operating_cash_flow") and result.get("capex"):
        ocf, capex = result["operating_cash_flow"], result["capex"]
        result["free_cash_flow"] = {
            **ocf, "value": float(ocf["value"]) - abs(float(capex["value"])),
            "source_fields": [ocf["source_field"], capex["source_field"]],
            "scale_transformation": "OCF_MINUS_ABS_CAPEX",
        }
    ebitda = select("ebitda", ("EBITDA",))
    if ebitda:
        result["ebitda"] = _envelope("ebitda", ebitda, report, period, currency)
    return result


def _envelope(name: str, fact: Mapping[str, Any], report: Mapping[str, Any], period: str | None,
              currency: str | None) -> dict[str, Any]:
    return {
        "value": fact.get("value"), "source_field": fact.get("concept"), "source_unit": fact.get("unit"),
        "normalized_unit": "SHARES" if "shares" in name else currency,
        "source_period": report.get("quarter"), "canonical_period": period,
        "period_end": report.get("endDate"), "currency": currency, "scale_transformation": "NONE",
        "effective_date": report.get("endDate"), "filed_date": report.get("filedDate"),
        "source_record_version": report.get("accessNumber"), "restatement_status": "UNRESOLVED",
    }


__all__ = [
    "MISSING_PROVIDER_FACT", "NONNUMERIC_PROVIDER_VALUE", "VALID_NUMERIC_FACT",
    "canonical_financial_facts", "canonical_period", "currency_from_facts", "safe_numeric",
]
