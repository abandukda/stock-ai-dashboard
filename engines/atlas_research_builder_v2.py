
"""
Atlas V2 Phase 1 — Canonical Research Builder

One deterministic, read-only object for the full research UI. It consolidates
the active V104/V105 row data, enriched sections, analyst intelligence,
individualized scoring, valuation cases, trade planning, and educational
interpretations.

This phase consumes data already present in the Atlas row. Provider-specific
live fetches can be attached later through the optional enrichers argument.
Missing data is never fabricated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
import math

from engines.canonical_market_data import attach_price_history
from engines.research_enrichment_v105 import build_enriched_research_report
from engines.research_engine_v105 import build_institutional_research
from engines.analyst_engine import build_analyst_snapshot, build_analyst_summary
from engines.semantic_fields import atlas_valuation_status, canonical_atlas_fair_value, valuation_families
from engines.trade_plan_v1052 import build_trade_plan
from engines.atlas_intelligence_engine import build_executive_intelligence
from engines.guidance_summary import build_guidance_summary, guidance_summary_text


Enricher = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
        number = float(text)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if text.lower() in {"", "none", "null", "nan", "n/a", "na", "unknown", "unavailable", "under review"}:
        return default
    return text


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _sources(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = [
        row,
        _mapping(row.get("raw")),
        _mapping(row.get("Raw")),
        _mapping(row.get("financials")),
        _mapping(row.get("earnings")),
        _mapping(row.get("analysts")),
        _mapping(row.get("political")),
        _mapping(row.get("ownership")),
        _mapping(row.get("technical")),
    ]
    return [value for value in values if value]


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for source in _sources(row):
        for key in keys:
            if key in source:
                value = source.get(key)
                if value not in (None, ""):
                    return value
    return None


def _section_status(data: Any, required: Sequence[str] = ()) -> dict[str, Any]:
    if isinstance(data, Mapping):
        populated = sum(data.get(key) not in (None, "", [], {}) for key in required)
        completeness = round(populated / len(required) * 100, 1) if required else (100.0 if data else 0.0)
    elif isinstance(data, list):
        completeness = 100.0 if data else 0.0
    else:
        completeness = 100.0 if data not in (None, "") else 0.0

    status = "available" if completeness >= 70 else "partial" if completeness > 0 else "unavailable"
    return {"status": status, "completeness_pct": completeness}


def _evidence_registry(
    sections: Mapping[str, Mapping[str, Any]],
    *,
    validated_fair_value: Any,
    fair_value_cases: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Canonical availability registry used by coverage and completeness."""
    def entry(status: str, detail: str) -> dict[str, Any]:
        return {"status": status, "detail": detail}

    def section_entry(name: str) -> dict[str, Any]:
        section = sections.get(name) or {}
        return entry(str(section.get("status") or "unavailable"), f"{section.get('completeness_pct', 0):.1f}% populated")

    earnings_data = _mapping((sections.get("earnings") or {}).get("data"))
    ownership_data = _mapping((sections.get("ownership") or {}).get("data"))
    political_data = _mapping((sections.get("political") or {}).get("data"))
    valid_cases = sum(_num(case.get("fair_value")) is not None for case in fair_value_cases if isinstance(case, Mapping))
    valuation_status = "available" if _num(validated_fair_value) is not None and valid_cases >= 1 else "unavailable"
    guidance_status = "available" if any(
        earnings_data.get(key) not in (None, "", [], {})
        for key in ("guidance", "management_tone", "transcript_summary")
    ) else "unavailable"
    insider_status = "available" if any(
        ownership_data.get(key) not in (None, "", [], {})
        for key in ("insider_transactions", "insider_buy_count", "insider_sell_count", "insider_support_score")
    ) else "unavailable"
    return {
        "fundamentals": section_entry("financials"),
        "valuation": entry(valuation_status, f"{valid_cases} populated fair-value cases"),
        "technicals": section_entry("technical"),
        "analysts": section_entry("analysts"),
        "earnings": section_entry("earnings"),
        "guidance": entry(guidance_status, "Genuine guidance/transcript evidence only"),
        "news": section_entry("news"),
        "ownership": section_entry("ownership"),
        "insider_activity": entry(insider_status, "Structured insider evidence"),
        "policy": entry("available" if political_data else "not_applicable", "Not critical financial evidence"),
    }


def _registry_coverage(registry: Mapping[str, Mapping[str, Any]]) -> float:
    points = {"available": 100.0, "partial": 50.0, "unavailable": 0.0}
    applicable = [points[item["status"]] for item in registry.values() if item.get("status") in points]
    return round(sum(applicable) / len(applicable), 1) if applicable else 0.0


def _financial_interpretation(data: Mapping[str, Any]) -> str:
    strengths, risks = [], []
    growth = _num(data.get("revenue_growth_pct"))
    eps = _num(data.get("eps_growth_pct"))
    gross = _num(data.get("gross_margin_pct"))
    operating = _num(data.get("operating_margin_pct"))
    roic = _num(data.get("roic_pct"))
    cash = _num(data.get("cash"))
    debt = _num(data.get("debt"))
    pe = _num(data.get("forward_pe"))
    peg = _num(data.get("peg_ratio"))

    if growth is not None:
        (strengths if growth >= 10 else risks if growth < 0 else strengths).append(
            f"revenue growth is {growth:.1f}%"
        )
    if eps is not None:
        (strengths if eps >= 10 else risks if eps < 0 else strengths).append(
            f"EPS growth is {eps:.1f}%"
        )
    if gross is not None and gross >= 50:
        strengths.append(f"gross margin is strong at {gross:.1f}%")
    if operating is not None and operating < 10:
        risks.append(f"operating margin is relatively thin at {operating:.1f}%")
    if roic is not None and roic >= 15:
        strengths.append(f"ROIC of {roic:.1f}% indicates efficient capital deployment")
    if cash is not None and debt is not None:
        if cash >= debt:
            strengths.append("cash covers total debt")
        else:
            risks.append("debt exceeds cash")
    if pe is not None and pe >= 35:
        risks.append(f"forward P/E of {pe:.1f} requires continued execution")
    if peg is not None and peg > 2:
        risks.append(f"PEG of {peg:.2f} suggests growth may be richly valued")

    if not strengths and not risks:
        return "Atlas does not yet have enough populated financial metrics to form a reliable interpretation."
    result = "Atlas views "
    if strengths:
        result += "; ".join(strengths) + " as supportive"
    if risks:
        result += (", while " if strengths else "") + "; ".join(risks) + " remain key risks"
    return result + "."


def _earnings_history(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        row.get("earnings_history")
        or row.get("historical_earnings")
        or row.get("quarterly_earnings")
        or _first(row, "Earnings History", "Historical Earnings", "earningsHistory")
        or []
    )
    output = []
    for item in _sequence(candidates):
        if not isinstance(item, Mapping):
            continue
        output.append(
            {
                "period": _text(item.get("period") or item.get("quarter") or item.get("date")),
                "eps_actual": _num(item.get("eps_actual") or item.get("epsActual") or item.get("actual_eps")),
                "eps_estimate": _num(item.get("eps_estimate") or item.get("epsEstimated") or item.get("estimated_eps")),
                "revenue_actual": _num(item.get("revenue_actual") or item.get("revenueActual")),
                "revenue_estimate": _num(item.get("revenue_estimate") or item.get("revenueEstimated")),
                "reaction_pct": _num(item.get("reaction_pct") or item.get("price_change_pct")),
            }
        )
    return output[:8]


def _earnings_interpretation(data: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> str:
    eps = _num(data.get("eps_surprise_pct"))
    revenue = _num(data.get("revenue_surprise_pct"))
    guidance = _text(data.get("guidance"))
    tone = _text(data.get("management_tone"))
    observations = []
    if eps is not None:
        observations.append(f"EPS {'beat' if eps >= 0 else 'missed'} expectations by {abs(eps):.1f}%")
    if revenue is not None:
        observations.append(f"revenue {'beat' if revenue >= 0 else 'missed'} expectations by {abs(revenue):.1f}%")
    if guidance:
        observations.append(f"guidance was described as {guidance}")
    if tone:
        observations.append(f"management tone was {tone}")
    if history:
        beats = 0
        measured = 0
        for item in history:
            actual, estimate = _num(item.get("eps_actual")), _num(item.get("eps_estimate"))
            if actual is not None and estimate is not None:
                measured += 1
                beats += actual >= estimate
        if measured:
            observations.append(f"EPS met or beat estimates in {beats} of {measured} populated quarters")
    return (
        "Atlas does not yet have enough structured earnings evidence to summarize the prior quarter."
        if not observations
        else "Atlas earnings assessment: " + "; ".join(observations) + "."
    )


def _news_interpretation(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return "No recent high-confidence company-specific news available."
    positive = negative = material = 0
    for item in items:
        sentiment = _text(item.get("sentiment")).lower()
        if "positive" in sentiment or "bull" in sentiment:
            positive += 1
        if "negative" in sentiment or "bear" in sentiment:
            negative += 1
        impact = _num(item.get("impact"))
        if impact is not None and impact >= 60:
            material += 1
    if positive > negative:
        direction = "supportive"
    elif negative > positive:
        direction = "cautious"
    else:
        direction = "mixed"
    return (
        f"Atlas views the current news flow as {direction}. "
        f"{positive} positive and {negative} negative items were identified, "
        f"with {material} marked as highly material where impact data was supplied."
    )


def _political_interpretation(data: Mapping[str, Any]) -> str:
    transactions = _sequence(data.get("transactions"))
    buyers = _num(data.get("buyers"), 0) or 0
    sellers = _num(data.get("sellers"), 0) or 0
    exposures = [
        _text(data.get("government_contract_exposure")),
        _text(data.get("regulatory_exposure")),
        _text(data.get("tariff_exposure")),
        _text(data.get("export_control_exposure")),
    ]
    exposures = [item for item in exposures if item]
    policy = _sequence(data.get("policy_evidence"))
    if not transactions and not buyers and not sellers and not exposures and not policy:
        return (
            "No material company-specific policy evidence currently available. "
            "A numeric political component alone is not evidence of policy support."
        )
    parts = []
    if transactions:
        parts.append(f"{len(transactions)} recent political transaction records are available")
    if buyers or sellers:
        parts.append(f"the aggregate signal contains {buyers:.0f} buyers and {sellers:.0f} sellers")
    if exposures:
        parts.append("policy exposure includes " + "; ".join(exposures))
    if policy:
        parts.append(f"{len(policy)} sourced company-specific policy event(s) are available")
    return "Atlas political assessment: " + ". ".join(parts) + "."


def _analyst_details(row: Mapping[str, Any], data: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions = _sequence(data.get("actions"))
    if actions:
        return [dict(item) for item in actions if isinstance(item, Mapping)][:20]
    raw = (
        row.get("analyst_details")
        or row.get("Analyst Details")
        or row.get("Analyst Ratings Detail")
        or row.get("analyst_grades")
        or []
    )
    details = [dict(item) for item in _sequence(raw) if isinstance(item, Mapping)]
    if details:
        return details[:20]
    # Aggregate consensus is displayed in the consensus metrics, not invented
    # as an individual analyst action.
    return []


def _analyst_interpretation(row: Mapping[str, Any], data: Mapping[str, Any]) -> str:
    summary = build_analyst_summary(dict(row))
    atlas_target = _num(row.get("validated_fair_value") or row.get("atlas_fair_value"))
    average = _num(data.get("average_target"))
    comparison = ""
    if atlas_target is not None and average is not None:
        if atlas_target > average:
            comparison = " Atlas is more bullish than the current Wall Street average."
        elif atlas_target < average:
            comparison = " Atlas is more conservative than the current Wall Street average."
        else:
            comparison = " Atlas is aligned with the Wall Street average."
    return summary + comparison


def _risk_interpretations(risk_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in risk_rows:
        if not isinstance(item, Mapping):
            continue
        factor = _text(item.get("factor") or item.get("risk") or item.get("category"), "Risk")
        level = _text(item.get("level") or item.get("rating") or item.get("status"), "Under review")
        detail = _text(item.get("detail") or item.get("description") or item.get("reason"))
        if not detail:
            detail = (
                f"{factor} is rated {level}. Atlas recommends monitoring changes in this factor "
                "because deterioration could weaken the thesis or require a smaller position."
            )
        output.append({"factor": factor, "level": level, "atlas_interpretation": detail})
    return output


def _history(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        row.get("price_history"),
        row.get("historical_prices"),
        row.get("chart_data"),
        row.get("historical_data"),
    ]
    raw = row.get("raw") or row.get("Raw")
    if isinstance(raw, Mapping):
        candidates.extend(
            [
                raw.get("price_history"),
                raw.get("historical_prices"),
                raw.get("chart_data"),
                raw.get("historical_data"),
            ]
        )

    history = next(
        (
            value
            for value in candidates
            if isinstance(value, list) and value
        ),
        [],
    )
    return [
        dict(item)
        for item in history
        if isinstance(item, Mapping)
    ]


def build_atlas_research_v2(
    row: Mapping[str, Any],
    *,
    enrichers: Sequence[Enricher] = (),
) -> dict[str, Any]:
    ticker = _text(row.get("ticker") or row.get("Ticker"), "UNKNOWN")
    enriched_row = attach_price_history(row)
    # Normalize canonical valuation inputs before the institutional builder.
    # This reconciles saved/live aliases without changing valuation formulas.
    if _num(enriched_row.get("current_price")) is None:
        current_price = _num(_first(enriched_row, "Price", "price", "last_price"))
        if current_price is not None:
            enriched_row["current_price"] = current_price
    # Full Research uses only canonical Atlas valuation in its Atlas-FV slot.
    # This deliberately replaces the V103 compatibility alias, which can hold
    # analyst consensus, without changing V103 scoring or recommendations.
    enriched_row["validated_fair_value"] = canonical_atlas_fair_value(enriched_row)

    enricher_errors = []
    for enricher in enrichers:
        try:
            result = enricher(ticker, enriched_row)
            if isinstance(result, Mapping):
                enriched_row.update(result)
        except Exception as exc:
            enricher_errors.append(str(exc))

    enriched = build_enriched_research_report(enriched_row)
    institutional = build_institutional_research(enriched_row)
    # Authoritative customer-facing V103 values pass through unchanged.  The
    # individualized calculator remains available to legacy/internal callers.
    scores = {
        "opportunity_score": _num(enriched_row.get("opportunity_score")),
        "confidence_pct": _num(enriched_row.get("confidence_pct")),
        "source": "Authoritative V103 fields",
    }

    quote = {
        "price": _num(
            _first(enriched_row, "current_price", "Price", "price", "last_price")
        ),
        "price_as_of": _text(
            _first(enriched_row, "price_as_of", "quote_timestamp", "updated_at"),
            datetime.now(timezone.utc).isoformat(),
        ),
        "quote_source": _text(
            _first(enriched_row, "quote_source", "price_source"),
            "Current Atlas scan",
        ),
        "market_status": _text(
            _first(enriched_row, "market_status"),
            "UNKNOWN",
        ),
    }
    trade_plan = build_trade_plan(enriched_row, quote)

    financial_data = _mapping(enriched["financials"].get("data"))
    earnings_data = _mapping(enriched["earnings"].get("data"))
    news_items = _sequence(enriched["news"].get("data"))
    political_data = _mapping(enriched["political"].get("data"))
    analyst_data = _mapping(enriched["analysts"].get("data"))
    ownership_data = _mapping(enriched["ownership"].get("data"))
    technical_data = _mapping(enriched["technical"].get("data"))
    earnings_history = _earnings_history(enriched_row)
    analyst_details = _analyst_details(enriched_row, analyst_data)
    risk_rows = _risk_interpretations(institutional.get("risk_matrix") or [])

    sections = {
        "financials": {
            **enriched["financials"],
            **_section_status(
                financial_data,
                ("revenue_growth_pct", "eps_growth_pct", "gross_margin_pct", "free_cash_flow", "forward_pe"),
            ),
            "interpretation": _financial_interpretation(financial_data),
        },
        "earnings": {
            **enriched["earnings"],
            **_section_status(
                earnings_data,
                ("eps_surprise_pct", "revenue_surprise_pct", "guidance", "transcript_summary"),
            ),
            "history": earnings_history,
            "interpretation": _earnings_interpretation(earnings_data, earnings_history),
        },
        "analysts": {
            **enriched["analysts"],
            **_section_status(
                analyst_data,
                ("average_target", "buy_count", "hold_count", "sell_count"),
            ),
            "details": analyst_details,
            "interpretation": _analyst_interpretation(enriched_row, analyst_data),
        },
        "news": {
            **enriched["news"],
            **_section_status(news_items),
            "interpretation": _news_interpretation(news_items),
        },
        "political": {
            **enriched["political"],
            **_section_status(political_data, ("political_support_score", "transactions")),
            "interpretation": _political_interpretation(political_data),
        },
        "ownership": {
            **enriched["ownership"],
            **_section_status(ownership_data, ("institutional_ownership_pct", "major_holders")),
            "interpretation": (
                "Ownership evidence should be evaluated through holder concentration, recent institutional change, "
                "and whether insider activity is discretionary buying or routine compensation selling."
                if ownership_data
                else f"{ticker} ownership evidence is not populated in the current payload; this is a data limitation, not a negative signal."
            ),
        },
        "technical": {
            **enriched["technical"],
            **_section_status(technical_data, ("price", "sma50", "sma200", "rsi", "volume_confirmation")),
            "history": _history(enriched_row),
            "history_provenance": _mapping(
                enriched_row.get("history_provenance")
            ),
            "interpretation": (
                _text(_first(enriched_row, "technical_summary", "Technical Summary", "v42_chart_guidance"))
                or "Atlas will assess trend, momentum, moving averages, support, resistance, and volume when populated."
            ),
        },
        "risk": {
            "status": "available" if risk_rows else "unavailable",
            "completeness_pct": 100.0 if risk_rows else 0.0,
            "data": risk_rows,
            "interpretation": (
                "Risk should determine position size and invalidation levels, not merely appear as a score."
                if risk_rows
                else f"No structured {ticker} risk matrix was supplied; Atlas will not infer that risk is absent."
            ),
        },
    }

    valuation = valuation_families(enriched_row)
    fair_value_cases = []
    for label, key in (("Bear", "scenario_bear"), ("Base", "scenario_base"), ("Bull", "scenario_bull")):
        value = valuation.get(key)
        implied = ((value / quote["price"]) - 1) * 100 if value is not None and quote.get("price") else None
        fair_value_cases.append({
            "label": label,
            "fair_value": value,
            "expected_return_pct": round(implied, 1) if implied is not None else None,
            "probability_pct": None,
            "source": "Analyst-driven scenario model",
        })
    validated_fair_value = institutional.get("validated_fair_value")
    evidence_registry = _evidence_registry(
        sections,
        validated_fair_value=validated_fair_value,
        fair_value_cases=fair_value_cases,
    )
    completeness = _registry_coverage(evidence_registry)
    committee_verdict = institutional.get("committee_verdict") or enriched.get("committee_verdict")

    report = {
        "version": "V2.1-AI-INTELLIGENCE",
        "ticker": ticker,
        "company": (
            enriched.get("company")
            or _text(_first(enriched_row, "company", "Company", "company_name", "name"), ticker)
        ),
        "sector": (
            enriched.get("sector")
            or _text(_first(enriched_row, "sector", "Sector", "industry", "Industry"))
        ),
        "committee_verdict": committee_verdict,
        "opportunity_score": scores["opportunity_score"],
        "confidence_pct": scores["confidence_pct"],
        "score_attribution": scores,
        "position_size_range": institutional.get("position_size_range") or enriched.get("position_size_range"),
        "executive_summary": institutional.get("executive_summary") or enriched.get("executive_summary"),
        "investment_thesis": institutional.get("investment_thesis") or enriched.get("executive_summary"),
        "bull_case": institutional.get("bull_case") or enriched.get("positive_drivers"),
        "bear_case": institutional.get("bear_case") or enriched.get("reasons_to_wait"),
        "fair_value_cases": fair_value_cases,
        "validated_fair_value": validated_fair_value,
        "atlas_fair_value": validated_fair_value,
        "atlas_valuation_status": atlas_valuation_status(enriched_row),
        "atlas_fv_upside_pct": valuation.get("atlas_fv_upside_pct"),
        "atlas_expected_return_pct": valuation.get("atlas_expected_return_pct"),
        "analyst_upside_pct": valuation.get("analyst_upside_pct"),
        "scenario_base_upside_pct": valuation.get("scenario_base_upside_pct"),
        "expected_return_pct": valuation.get("atlas_expected_return_pct"),
        "valuation_families": valuation,
        "current_price": quote.get("price"),
        "quote": quote,
        "trade_plan": trade_plan,
        "sections": sections,
        "research_completeness_pct": completeness,
        "evidence_coverage_pct": completeness,
        "evidence_registry": evidence_registry,
        "enricher_errors": enricher_errors,
        "upgrade_triggers": institutional.get("upgrade_triggers") or enriched_row.get("upgrade_triggers") or [],
        "downgrade_triggers": institutional.get("downgrade_triggers") or enriched_row.get("downgrade_triggers") or [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "narrative_context": {
            "ticker": ticker,
            "company": (
                enriched.get("company")
                or _text(_first(enriched_row, "company", "Company", "company_name", "name"), ticker)
            ),
            "sector": (
                enriched.get("sector")
                or _text(_first(enriched_row, "sector", "Sector", "industry", "Industry"))
            ),
            "current_price": quote.get("price"),
            "validated_fair_value": institutional.get("validated_fair_value"),
            "atlas_valuation_status": atlas_valuation_status(enriched_row),
            "expected_return_pct": institutional.get("expected_return_pct"),
            "research_completeness_pct": completeness,
        },
    }
    report["intelligence"] = build_executive_intelligence(report)
    guidance_input = dict(enriched_row)
    guidance_input.update({
        "committee_verdict": report.get("committee_verdict"),
        "confidence_pct": report.get("confidence_pct"),
        "position_size_range": report.get("position_size_range"),
        "trade_plan": report.get("trade_plan") or {},
    })
    report["guidance_summary"] = build_guidance_summary(guidance_input)
    report["executive_summary"] = guidance_summary_text(report["guidance_summary"])
    report["source_investment_thesis"] = report.get("investment_thesis")
    report["source_bull_case"] = report.get("bull_case")
    report["source_bear_case"] = report.get("bear_case")
    report["investment_thesis"] = report["executive_summary"]
    report["bull_case"] = [
        f"{item.get('fact')} {item.get('why_it_matters')}"
        for item in report["guidance_summary"].get("supporting_facts") or []
    ]
    report["bear_case"] = [
        f"{item.get('risk')} {item.get('consequence')}"
        for item in report["guidance_summary"].get("key_risks") or []
    ]
    return report


def validate_atlas_research_v2(report: Mapping[str, Any]) -> list[str]:
    errors = []
    if report.get("version") not in {"V2.0-PHASE1", "V2.1-AI-INTELLIGENCE"}:
        errors.append("Unexpected report version.")
    if not report.get("ticker"):
        errors.append("Ticker is required.")
    sections = report.get("sections")
    if not isinstance(sections, Mapping):
        errors.append("Sections are required.")
        return errors
    for name in ("financials", "earnings", "analysts", "news", "political", "ownership", "technical", "risk"):
        if name not in sections:
            errors.append(f"Missing section: {name}")
    return errors


__all__ = ["build_atlas_research_v2", "validate_atlas_research_v2"]
