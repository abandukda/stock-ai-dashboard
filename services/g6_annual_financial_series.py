"""Period-correct annual statement series from normalized retained evidence.

This module never changes ratings or publication state. Taxonomy mappings are
explicit and fail closed; projections are mechanical presentation aids, not
analyst forecasts.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping


CONTRACT = "ATLAS_G6_ANNUAL_FINANCIAL_SERIES_V1"

CONCEPTS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
        "SalesRevenueNet", "SalesRevenueGoodsNet",
    ),
    "operating_income": ("OperatingIncomeLoss",),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capital_expenditure": (
        "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ),
    "total_debt": ("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtAndFinanceLeaseObligations"),
    "debt_current": (
        "LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings", "LinesOfCreditCurrent",
        "NotesPayableCurrent", "NotesAndLoansPayableCurrent", "FinanceLeaseLiabilityCurrent",
        "ConvertibleDebtCurrent",
    ),
    "debt_noncurrent": (
        "LongTermDebtNoncurrent", "LongTermDebt", "LongTermNotesAndLoans", "NotesPayable",
        "LongTermLineOfCredit", "FinanceLeaseLiabilityNoncurrent", "ConvertibleDebtNoncurrent",
    ),
}


def local_concept(value: str) -> str:
    return str(value).split("_")[-1].split(":")[-1]


def _date(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _fact(facts: Iterable[Mapping[str, Any]], names: tuple[str, ...]) -> Mapping[str, Any] | None:
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for fact in facts:
        by_name.setdefault(local_concept(str(fact.get("concept", ""))), []).append(fact)
    for name in names:
        candidates = by_name.get(name, [])
        # Multiple facts for one canonical concept in one annual report are
        # ambiguous dimensions. Do not select one silently.
        if len(candidates) == 1:
            return candidates[0]
    return None


def _metric(fact: Mapping[str, Any] | None) -> dict[str, Any]:
    if fact is None:
        return {"status": "UNAVAILABLE", "value": None, "unit": None, "provenance": None}
    return {"status": "AVAILABLE", "value": fact["value"], "unit": fact["unit"],
            "provenance": fact["provenance"], "concept": fact["concept"]}


def _derived(value: float | None, unit: Mapping[str, Any] | None, sources: list[Mapping[str, Any]], method: str) -> dict[str, Any]:
    if value is None:
        return {"status": "UNAVAILABLE", "value": None, "unit": unit, "provenance": None}
    return {"status": "AVAILABLE", "value": value, "unit": unit,
            "provenance": {"derivation": method, "source_facts": [x["provenance"] for x in sources]}}


def _projection(points: list[dict[str, Any]], key: str) -> dict[str, Any]:
    usable = [p for p in points if p["metrics"][key]["status"] == "AVAILABLE"][-5:]
    if len(usable) < 3:
        return {"status": "UNAVAILABLE", "reason": "THREE_PERIODS_REQUIRED"}
    units = {p["metrics"][key]["unit"].get("canonical") for p in usable}
    if len(units) != 1:
        return {"status": "UNAVAILABLE", "reason": "UNIT_MISMATCH"}
    ys = [float(p["metrics"][key]["value"]) for p in usable]
    n = len(ys); mean_x = (n - 1) / 2; mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in range(n))
    slope = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(ys)) / denominator
    return {"status": "AVAILABLE", "value": mean_y + slope * (n - mean_x),
            "unit": usable[-1]["metrics"][key]["unit"], "method": "OLS_LAST_UP_TO_5_ANNUAL_PERIODS",
            "classification": "MECHANICAL_TREND_NOT_ANALYST_FORECAST",
            "source_periods": [p["fiscal_period_end"] for p in usable]}


def build_annual_series(record: Mapping[str, Any]) -> dict[str, Any]:
    if record.get("contract") != "ATLAS_G6_ANNUAL_STATEMENT_NORMALIZATION_V1":
        raise ValueError("NORMALIZED_CONTRACT_MISMATCH")
    selected: dict[str, Mapping[str, Any]] = {}
    restatements: dict[str, int] = {}
    for filing in record.get("filings", []):
        identity = filing["identity"]
        end = str(identity["endDate"])
        restatements[end] = restatements.get(end, 0) + 1
        current = selected.get(end)
        rank = (_date(identity["acceptedDate"]), str(identity["accessNumber"]))
        if current is None or rank > (_date(current["identity"]["acceptedDate"]), str(current["identity"]["accessNumber"])):
            selected[end] = filing
    points = []
    for end, filing in sorted(selected.items()):
        facts = filing["facts"]
        raw = {key: _fact(facts, names) for key, names in CONCEPTS.items()}
        metrics = {key: _metric(raw[key]) for key in ("revenue", "operating_income", "operating_cash_flow", "capital_expenditure")}
        rev, op = raw["revenue"], raw["operating_income"]
        compatible = rev and op and rev["unit"].get("currency") == op["unit"].get("currency") and float(rev["value"]) != 0
        metrics["operating_margin"] = _derived(float(op["value"]) / float(rev["value"]) if compatible else None,
                                                        {"kind": "RATIO", "canonical": "PERCENT_DECIMAL", "currency": None, "original": None},
                                                        [rev, op] if compatible else [], "operating_income/revenue")
        cfo, capex = raw["operating_cash_flow"], raw["capital_expenditure"]
        compatible = cfo and capex and cfo["unit"].get("currency") == capex["unit"].get("currency")
        metrics["free_cash_flow"] = _derived(float(cfo["value"]) - abs(float(capex["value"])) if compatible else None,
                                                      cfo["unit"] if compatible else None, [cfo, capex] if compatible else [],
                                                      "operating_cash_flow-abs(capital_expenditure)")
        total = raw["total_debt"]
        debt_sources = [x for x in (raw["debt_current"], raw["debt_noncurrent"]) if x]
        if total:
            metrics["total_debt"] = _metric(total)
        elif debt_sources and len({x["unit"].get("currency") for x in debt_sources}) == 1:
            metrics["total_debt"] = _derived(sum(float(x["value"]) for x in debt_sources), debt_sources[0]["unit"], debt_sources,
                                                     "current_debt+noncurrent_debt")
        else:
            metrics["total_debt"] = _derived(None, None, [], "current_debt+noncurrent_debt")
        points.append({"fiscal_year": filing["identity"]["year"], "fiscal_period_end": end,
                       "filed_date": filing["identity"]["filedDate"], "accepted_date": filing["identity"]["acceptedDate"],
                       "accession": filing["identity"]["accessNumber"], "restatement_candidates": restatements[end],
                       "selection": "LATEST_ACCEPTED_FOR_FISCAL_END", "metrics": metrics})
    projections = {key: _projection(points, key) for key in ("revenue", "operating_margin", "free_cash_flow", "total_debt")}
    return {"contract": CONTRACT, "ticker": record["ticker"], "source_normalized_sha256": record["normalized_sha256"],
            "periods": points, "projections": projections}


__all__ = ["CONCEPTS", "CONTRACT", "build_annual_series", "local_concept"]
