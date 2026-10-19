"""One read-only source of truth for customer Research financial availability."""
from __future__ import annotations

from typing import Any, Mapping


FAMILIES = (
    "income_statement", "balance_sheet", "cash_flow", "estimates", "valuation_metrics",
)


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seq(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _period(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _history_facts(history: Mapping[str, Any], lane: str) -> tuple[list[Any], set[str]]:
    facts: list[Any] = []
    periods: set[str] = set()
    for frequency in ("annual", "quarterly"):
        projection = _map(history.get(frequency))
        statements = _map(projection.get("statements"))
        rows = statements.get(lane) or ()
        if isinstance(rows, Mapping):
            rows = rows.get("rows") or ()
        facts.extend(_seq(rows))
        for item in _seq(projection.get("visible_periods") or projection.get("periods")):
            if isinstance(item, Mapping):
                candidate = _period(item.get("period") or item.get("end_date") or item.get("fiscal_year"))
            else:
                candidate = _period(item)
            if candidate:
                periods.add(candidate)
    return facts, periods


def _annual_facts(annual: Mapping[str, Any], lane: str) -> tuple[list[Any], set[str]]:
    statements = _map(annual.get("statements"))
    rows = statements.get(lane) or ()
    if isinstance(rows, Mapping):
        rows = rows.get("rows") or ()
    periods = set()
    for item in _seq(annual.get("periods")):
        if isinstance(item, Mapping):
            candidate = _period(item.get("period") or item.get("end_date") or item.get("fiscal_year"))
        else:
            candidate = _period(item)
        if candidate:
            periods.add(candidate)
    return _seq(rows), periods


def _latest_facts(depth: Mapping[str, Any], lane: str) -> tuple[list[Any], set[str]]:
    rows = _seq(_map(depth.get("statements")).get(lane))
    periods = {
        candidate for item in rows if isinstance(item, Mapping)
        if (candidate := _period(item.get("period") or item.get("as_of")))
    }
    return rows, periods


def _explicit_stale(*sources: Mapping[str, Any]) -> bool:
    values = {
        str(source.get(key) or "").upper()
        for source in sources for key in ("freshness_status", "cache_status", "status")
    }
    return bool(values & {"STALE", "STALE_RETAINED", "EXPIRED"})


def build_financial_availability(
    *, ticker: str, snapshot: Mapping[str, Any], depth: Mapping[str, Any],
    statement_history: Mapping[str, Any], annual_statements: Mapping[str, Any],
    freshness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile every rendered financial family without deriving new financial facts."""
    history_ok = statement_history.get("status") == "AVAILABLE"
    annual_ok = annual_statements.get("status") == "AVAILABLE"
    stale = _explicit_stale(statement_history, annual_statements, freshness or {})
    families: dict[str, Any] = {}
    lane_map = {
        "income_statement": "INCOME_STATEMENT",
        "balance_sheet": "BALANCE_SHEET",
        "cash_flow": "CASH_FLOW",
    }
    for family, history_lane in lane_map.items():
        latest, latest_periods = _latest_facts(depth, family)
        retained, retained_periods = _history_facts(statement_history, history_lane) if history_ok else ([], set())
        annual, annual_periods = _annual_facts(annual_statements, history_lane) if annual_ok else ([], set())
        count = len(latest) + len(retained) + len(annual)
        periods = sorted(latest_periods | retained_periods | annual_periods)
        sources = tuple(name for name, present in (
            ("CERTIFIED_LATEST_FACTS", bool(latest)),
            ("SOURCE_BOUND_STATEMENT_HISTORY", bool(retained)),
            ("VALIDATED_ANNUAL_FILINGS", bool(annual)),
        ) if present)
        if not count:
            status = "UNAVAILABLE"
        elif stale:
            status = "STALE"
        elif (history_ok and retained) or (annual_ok and annual) or len(periods) > 1:
            status = "AVAILABLE"
        else:
            status = "PARTIAL"
        families[family] = {
            "status": status, "fact_count": count, "periods": tuple(periods),
            "latest_period": periods[-1] if periods else None, "sources": sources,
            "source_disagreement": depth.get("status") == "NOT_AVAILABLE" and bool(retained or annual),
        }

    snapshot_items = [item for item in _seq(snapshot.get("items")) if isinstance(item, Mapping)]
    estimate_items = [item for item in snapshot_items if str(item.get("field") or "").startswith("forward_")]
    valuation_models = _seq(depth.get("valuation_models"))
    estimate_periods = sorted({candidate for item in estimate_items if (candidate := _period(item.get("period") or item.get("as_of")))})
    valuation_periods = sorted({candidate for item in valuation_models if isinstance(item, Mapping)
                                if (candidate := _period(item.get("fiscal_period") or item.get("as_of")))})
    families["estimates"] = {
        "status": "STALE" if estimate_items and stale else "PARTIAL" if estimate_items else "UNAVAILABLE",
        "fact_count": len(estimate_items), "periods": tuple(estimate_periods),
        "latest_period": estimate_periods[-1] if estimate_periods else None,
        "sources": ("CERTIFIED_FIELD_LEVEL_ESTIMATES",) if estimate_items else (),
        "source_disagreement": False,
    }
    families["valuation_metrics"] = {
        "status": "STALE" if valuation_models and stale else "AVAILABLE" if len(valuation_models) > 1 else "PARTIAL" if valuation_models else "UNAVAILABLE",
        "fact_count": len(valuation_models), "periods": tuple(valuation_periods),
        "latest_period": valuation_periods[-1] if valuation_periods else None,
        "sources": ("CERTIFIED_ATLAS_VALUATION",) if valuation_models else (),
        "source_disagreement": False,
    }
    available = [name for name, item in families.items() if item["status"] != "UNAVAILABLE"]
    overall = "UNAVAILABLE" if not available else "STALE" if stale else "AVAILABLE" if len(available) == len(FAMILIES) else "PARTIAL"
    dated = sorted(str(item["latest_period"]) for item in families.values() if item.get("latest_period"))
    return {
        "contract": "ATLAS_RESEARCH_FINANCIAL_AVAILABILITY_V1", "ticker": ticker,
        "status": overall, "families": families, "available_families": tuple(available),
        "as_of": dated[-1] if dated else None,
        "message": (
            "Verified financial evidence is unavailable for this snapshot." if overall == "UNAVAILABLE"
            else "Verified financial evidence is retained, but some families or periods are unavailable." if overall == "PARTIAL"
            else "Verified financial evidence is retained and explicitly marked stale." if overall == "STALE"
            else "Verified financial evidence is available with source-dated coverage by family."
        ),
    }


def financial_context_sentence(availability: Mapping[str, Any]) -> str:
    """Plain-English summary that cannot contradict the rendered family grid."""
    status = str(availability.get("status") or "UNAVAILABLE")
    families = _map(availability.get("families"))
    labels = {
        "income_statement": "income statements", "balance_sheet": "balance sheets",
        "cash_flow": "cash-flow statements", "estimates": "estimates",
        "valuation_metrics": "valuation metrics",
    }
    present = [labels[name] for name in FAMILIES if _map(families.get(name)).get("status") != "UNAVAILABLE"]
    missing = [labels[name] for name in FAMILIES if _map(families.get(name)).get("status") == "UNAVAILABLE"]
    if status == "UNAVAILABLE":
        return "Verified financial statements, estimates, and valuation metrics are unavailable for this snapshot."
    sentence = "Verified " + ", ".join(present) + " are available with their retained reporting dates."
    if missing:
        sentence += " Unavailable: " + ", ".join(missing) + "."
    if status == "STALE":
        sentence += " This is retained stale evidence, not a fresh acquisition."
    elif status == "PARTIAL":
        sentence += " Coverage is partial and should not be read as a complete filing history."
    return sentence


__all__ = ["FAMILIES", "build_financial_availability", "financial_context_sentence"]
