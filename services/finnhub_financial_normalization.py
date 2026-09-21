"""Deterministic normalization of Finnhub reported facts for shadow comparison."""
from __future__ import annotations

from typing import Any, Mapping, Sequence


CONCEPTS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
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


def canonical_financial_facts(facts: Sequence[Mapping[str, Any]], report: Mapping[str, Any]) -> dict[str, Any]:
    by_concept = {str(f.get("concept") or "").split("_")[-1]: f for f in facts if f.get("value") is not None}
    def select(name: str) -> Mapping[str, Any] | None:
        return next((by_concept[c] for c in CONCEPTS[name] if c in by_concept), None)
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
    ebitda = by_concept.get("EBITDA")
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


__all__ = ["canonical_financial_facts", "canonical_period", "currency_from_facts"]
