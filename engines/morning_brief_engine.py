"""Atlas Morning Brief engine.

Builds a concise daily briefing from the current Atlas pipeline payload.
This initial release does not make live external API calls and does not alter
committee verdicts, rankings, confidence, or opportunity scores.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import math


VERDICT_PRIORITY = {
    "BUY_NOW": 4,
    "ACCUMULATE": 3,
    "MONITOR": 2,
    "AVOID": 1,
}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _rank_key(row: Mapping[str, Any]) -> tuple:
    return (
        VERDICT_PRIORITY.get(_text(row.get("committee_verdict")), 0),
        _num(row.get("confidence_pct"), 0) or 0,
        _num(row.get("opportunity_score"), 0) or 0,
        _num(row.get("expected_return_pct"), -999) or -999,
    )


def _market_bias(rows: list[Mapping[str, Any]]) -> tuple[str, str]:
    actionable = sum(
        row.get("committee_verdict") in {"BUY_NOW", "ACCUMULATE"}
        for row in rows
    )
    avoid = sum(
        row.get("committee_verdict") == "AVOID"
        for row in rows
    )
    monitor = sum(
        row.get("committee_verdict") == "MONITOR"
        for row in rows
    )

    if actionable >= max(3, avoid * 1.5):
        return (
            "Constructive",
            "Atlas currently sees more actionable opportunities than confirmed avoid setups.",
        )
    if avoid > actionable and avoid >= monitor:
        return (
            "Defensive",
            "Confirmed weak setups currently outnumber actionable opportunities.",
        )
    return (
        "Selective",
        "Atlas sees a mixed environment where stock selection matters more than broad risk-taking.",
    )


def _themes(rows: list[Mapping[str, Any]]) -> list[str]:
    sectors = Counter(
        _text(row.get("sector"), "Unknown")
        for row in rows
        if row.get("committee_verdict") in {"BUY_NOW", "ACCUMULATE"}
    )
    return [
        sector
        for sector, _ in sectors.most_common(4)
        if sector != "Unknown"
    ]


def build_morning_brief(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    normalized = [
        dict(row)
        for row in (rows or [])
        if isinstance(row, Mapping)
    ]
    ranked = sorted(normalized, key=_rank_key, reverse=True)

    top_opportunities = [
        row
        for row in ranked
        if row.get("committee_verdict") in {"BUY_NOW", "ACCUMULATE"}
    ][:5]

    monitor_list = [
        row
        for row in ranked
        if row.get("committee_verdict") == "MONITOR"
    ][:5]

    top_risks = sorted(
        [
            row
            for row in normalized
            if row.get("committee_verdict") == "AVOID"
        ],
        key=lambda row: (
            _num(row.get("opportunity_score"), 100) or 100,
            _num(row.get("confidence_pct"), 100) or 100,
        ),
    )[:5]

    bias, bias_reason = _market_bias(normalized)
    themes = _themes(normalized)

    buy_now_count = sum(
        row.get("committee_verdict") == "BUY_NOW"
        for row in normalized
    )
    accumulate_count = sum(
        row.get("committee_verdict") == "ACCUMULATE"
        for row in normalized
    )

    summary = (
        f"Atlas reviewed {len(normalized)} eligible opportunities. "
        f"The current research set contains {buy_now_count} Buy Now and "
        f"{accumulate_count} Accumulate ideas. "
        f"Market posture is {bias.lower()}: {bias_reason}"
    )

    return {
        "market_bias": bias,
        "market_bias_reason": bias_reason,
        "summary": summary,
        "top_themes": themes,
        "top_opportunities": top_opportunities,
        "monitor_list": monitor_list,
        "top_risks": top_risks,
        "counts": {
            "buy_now": buy_now_count,
            "accumulate": accumulate_count,
            "monitor": sum(
                row.get("committee_verdict") == "MONITOR"
                for row in normalized
            ),
            "avoid": sum(
                row.get("committee_verdict") == "AVOID"
                for row in normalized
            ),
        },
    }


def build_certified_morning_brief(
    rows: Iterable[Mapping[str, Any]], *, generated_at: str | None = None,
    watchlist_events: Iterable[Mapping[str, Any]] = (),
    market_context: Mapping[str, Any] | None = None,
    major_events: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the future internal brief solely from certified canonical rows."""
    opportunities = []
    for source in rows or ():
        row = dict(source)
        certification = row.get("publication_certification") if isinstance(row.get("publication_certification"), Mapping) else {}
        evaluation = row.get("canonical_investment_evaluation") if isinstance(row.get("canonical_investment_evaluation"), Mapping) else {}
        action = str(((evaluation.get("guidance") or {}).get("state") or ""))
        if certification.get("customer_publication_allowed") is not True or certification.get("certified_action") != action:
            continue
        if action != "BUY_NOW":
            continue
        evidence_ids = tuple(str(value) for value in row.get("evidence_ids", ()) if value)
        candidate_id = row.get("candidate_digest") or row.get("decision_digest") or evaluation.get("decision_digest")
        if not candidate_id or not evidence_ids:
            continue
        valuation = ((evaluation.get("atlas_valuation") or {}).get("professional_valuation_v2") or {})
        guidance = evaluation.get("guidance") or {}
        opportunities.append({
            "ticker": str(row.get("ticker") or row.get("symbol") or "").upper(),
            "canonical_action": action, "certified_candidate_identity": candidate_id,
            "current_display_price": row.get("display_price") or row.get("current_price"),
            "atlas_fair_value": valuation.get("atlas_base_fair_value") or row.get("atlas_fair_value"),
            "potential": valuation.get("atlas_expected_return") or row.get("potential"),
            "opportunity": evaluation.get("opportunity"), "decision_confidence": evaluation.get("decision_confidence"),
            "short_rationale": guidance.get("opportunity_thesis") or row.get("why_atlas_likes_it"),
            "main_risk": guidance.get("main_risk") or row.get("main_risk"),
            "evidence_ids": list(evidence_ids), "research_deep_link": f"/research?ticker={str(row.get('ticker') or '').upper()}",
        })
    opportunities.sort(key=lambda item: (item["canonical_action"] == "BUY_NOW", item.get("opportunity") or 0, item.get("decision_confidence") or 0), reverse=True)
    governed_watchlist = [dict(item) for item in watchlist_events if item.get("evidence_ids") and item.get("candidate_digest")]
    governed_events = [dict(item) for item in major_events if item.get("evidence_ids")]
    context = dict(market_context or {})
    if context and not (context.get("evidence_ids") or context.get("status") == "DATA_UNAVAILABLE"):
        context = {"status": "DATA_UNAVAILABLE", "limitations": ["Governed market-context evidence identity is required."]}
    return {
        "version": "ATLAS_MORNING_BRIEF_CONTRACT_V1", "status": "INTERNAL_NOT_DELIVERED",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "strongest_daily_opportunities": opportunities,
        "watchlist_state_changes": governed_watchlist,
        "market_context": context, "major_context_events": governed_events,
        "delivery_enabled": False, "financial_truth_source": "CERTIFIED_ATLAS_ONLY",
    }


__all__ = ["build_certified_morning_brief", "build_morning_brief"]
