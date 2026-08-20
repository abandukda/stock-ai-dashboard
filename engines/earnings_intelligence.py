"""Deterministic Phase 9C earnings, guidance, and transcript intelligence.

This module consumes normalized evidence only.  It never calls a provider,
calculates an investment score, or asks an LLM to calculate financial trends.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping, Sequence

from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE, NOT_APPLICABLE


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", "").strip())
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _date_key(value: Any) -> tuple[int, str]:
    text = str(value or "").strip()
    try:
        return (1, datetime.fromisoformat(text[:10]).date().isoformat())
    except ValueError:
        return (0, text)


def _surprise(actual: Any, estimate: Any, supplied: Any) -> float | None:
    explicit = _number(supplied)
    if explicit is not None:
        return round(explicit, 4)
    actual_num, estimate_num = _number(actual), _number(estimate)
    if actual_num is None or estimate_num in (None, 0):
        return None
    return round((actual_num - estimate_num) / abs(estimate_num) * 100.0, 4)


def _outcome(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value > 0:
        return "BEAT"
    if value < 0:
        return "MISS"
    return "MET"


def _combined(eps: str, revenue: str) -> str:
    measured = [item for item in (eps, revenue) if item != "UNAVAILABLE"]
    if not measured:
        return "UNAVAILABLE"
    if all(item in {"BEAT", "MET"} for item in measured):
        return "BEAT" if "BEAT" in measured else "MET"
    if all(item in {"MISS", "MET"} for item in measured):
        return "MISS" if "MISS" in measured else "MET"
    return "MIXED"


def _sequence_trend(values: Sequence[float | None]) -> str:
    measured = [value for value in values[:4] if value is not None]
    if len(measured) < 3:
        return "UNAVAILABLE"
    changes = [measured[index] - measured[index + 1] for index in range(len(measured) - 1)]
    if all(change >= 0 for change in changes) and any(change > 0 for change in changes):
        return "IMPROVING"
    if all(change <= 0 for change in changes) and any(change < 0 for change in changes):
        return "DETERIORATING"
    return "VOLATILE"


def _streak(outcomes: Sequence[str], target: str) -> int:
    count = 0
    for outcome in outcomes:
        if outcome != target:
            break
        count += 1
    return count


def _growth(newer: float | None, older: float | None) -> float | None:
    if newer is None or older in (None, 0):
        return None
    return round((newer - older) / abs(older) * 100.0, 2)


def _growth_trend(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    if len(rows) < 6:
        return {"status": DATA_UNAVAILABLE, "direction": "UNAVAILABLE", "latest_yoy_pct": None, "prior_yoy_pct": None}
    values = [_number(row.get(field)) for row in rows]
    latest = _growth(values[0], values[4]) if len(values) > 4 else None
    prior = _growth(values[1], values[5]) if len(values) > 5 else None
    if latest is None or prior is None:
        direction = "UNAVAILABLE"
    elif latest > prior:
        direction = "ACCELERATING"
    elif latest < prior:
        direction = "DECELERATING"
    else:
        direction = "STABLE"
    return {
        "status": AVAILABLE if direction != "UNAVAILABLE" else DATA_UNAVAILABLE,
        "direction": direction,
        "latest_yoy_pct": latest,
        "prior_yoy_pct": prior,
    }


def _quarter(row: Mapping[str, Any]) -> dict[str, Any]:
    eps_actual = _number(row.get("eps_actual"))
    eps_estimate = _number(row.get("eps_estimate"))
    revenue_actual = _number(row.get("revenue_actual"))
    revenue_estimate = _number(row.get("revenue_estimate"))
    eps_surprise = _surprise(eps_actual, eps_estimate, row.get("eps_surprise_pct"))
    revenue_surprise = _surprise(revenue_actual, revenue_estimate, row.get("revenue_surprise_pct"))
    eps_outcome, revenue_outcome = _outcome(eps_surprise), _outcome(revenue_surprise)
    return {
        "fiscal_period": row.get("fiscal_period") or row.get("period"),
        "report_date": row.get("report_date"),
        "eps_actual": eps_actual,
        "eps_estimate": eps_estimate,
        "eps_surprise_pct": eps_surprise,
        "eps_outcome": eps_outcome,
        "revenue_actual": revenue_actual,
        "revenue_estimate": revenue_estimate,
        "revenue_surprise_pct": revenue_surprise,
        "revenue_outcome": revenue_outcome,
        "quarter_outcome": _combined(eps_outcome, revenue_outcome),
        "provider": row.get("provider"),
        "evidence_timestamp": row.get("evidence_timestamp"),
    }


def build_earnings_intelligence(
    history: Sequence[Mapping[str, Any]] | None,
    *,
    is_etf: bool = False,
) -> dict[str, Any]:
    if is_etf:
        return {
            "version": "EARNINGS_INTELLIGENCE_V1",
            "semantic_status": NOT_APPLICABLE,
            "status_detail": "Corporate earnings intelligence does not apply to ETFs.",
            "history": [],
        }
    rows = [_quarter(row) for row in (history or []) if isinstance(row, Mapping)]
    # Provider histories can include an upcoming estimate-only fiscal period.
    # Earnings Intelligence describes reported experience only, so a row needs
    # at least one reported actual.  Estimate-only rows are never recast as a
    # historical quarter or used to calculate streaks and trends.
    rows = [
        row for row in rows
        if row.get("eps_actual") is not None or row.get("revenue_actual") is not None
    ]
    rows.sort(key=lambda row: _date_key(row.get("report_date") or row.get("fiscal_period")), reverse=True)
    rows = rows[:8]
    if not rows:
        return {
            "version": "EARNINGS_INTELLIGENCE_V1",
            "semantic_status": DATA_UNAVAILABLE,
            "status_detail": "No normalized reported-quarter history is available.",
            "history": [],
            "latest_quarter": None,
        }
    eps_outcomes = [row["eps_outcome"] for row in rows]
    revenue_outcomes = [row["revenue_outcome"] for row in rows]
    eps_surprises = [row["eps_surprise_pct"] for row in rows]
    revenue_surprises = [row["revenue_surprise_pct"] for row in rows]
    latest, prior = rows[0], rows[1] if len(rows) > 1 else None
    return {
        "version": "EARNINGS_INTELLIGENCE_V1",
        "semantic_status": AVAILABLE,
        "status_detail": f"{len(rows)} normalized reported quarter(s) available.",
        "latest_quarter": latest,
        "latest_quarter_classification": latest["quarter_outcome"],
        "eps_surprise_sequence_4q": eps_surprises[:4],
        "revenue_surprise_sequence_4q": revenue_surprises[:4],
        "consecutive_eps_beats": _streak(eps_outcomes, "BEAT"),
        "consecutive_eps_misses": _streak(eps_outcomes, "MISS"),
        "consecutive_revenue_beats": _streak(revenue_outcomes, "BEAT"),
        "consecutive_revenue_misses": _streak(revenue_outcomes, "MISS"),
        "eps_surprise_trend": _sequence_trend(eps_surprises),
        "revenue_surprise_trend": _sequence_trend(revenue_surprises),
        "revenue_growth_trend": _growth_trend(rows, "revenue_actual"),
        "earnings_growth_trend": _growth_trend(rows, "eps_actual"),
        "latest_vs_prior": {
            "eps_actual_change": (
                round(latest["eps_actual"] - prior["eps_actual"], 4)
                if prior and latest["eps_actual"] is not None and prior["eps_actual"] is not None else None
            ),
            "revenue_actual_change": (
                round(latest["revenue_actual"] - prior["revenue_actual"], 2)
                if prior and latest["revenue_actual"] is not None and prior["revenue_actual"] is not None else None
            ),
            "eps_surprise_change_pct": (
                round(latest["eps_surprise_pct"] - prior["eps_surprise_pct"], 4)
                if prior and latest["eps_surprise_pct"] is not None and prior["eps_surprise_pct"] is not None else None
            ),
            "revenue_surprise_change_pct": (
                round(latest["revenue_surprise_pct"] - prior["revenue_surprise_pct"], 4)
                if prior and latest["revenue_surprise_pct"] is not None and prior["revenue_surprise_pct"] is not None else None
            ),
        },
        "history": rows,
    }


def build_earnings_summary(intelligence: Mapping[str, Any], *, ticker: str = "This company") -> dict[str, Any]:
    status = intelligence.get("semantic_status")
    if status == NOT_APPLICABLE:
        return {"semantic_status": NOT_APPLICABLE, "summary": "Corporate earnings intelligence does not apply to this ETF."}
    latest = intelligence.get("latest_quarter")
    if status != AVAILABLE or not isinstance(latest, Mapping):
        return {
            "semantic_status": DATA_UNAVAILABLE,
            "summary": "Reported earnings history is unavailable, so Atlas cannot verify whether the earnings trend is improving or deteriorating.",
            "management_evidence_note": "Atlas has not verified management guidance or transcript evidence.",
        }
    eps = latest.get("eps_surprise_pct")
    revenue = latest.get("revenue_surprise_pct")
    happened = f"{ticker}'s latest reported quarter was {str(latest.get('quarter_outcome') or 'UNAVAILABLE').lower()}."
    details = []
    if eps is not None:
        details.append(f"EPS was {eps:+.1f}% versus estimate")
    if revenue is not None:
        details.append(f"revenue was {revenue:+.1f}% versus estimate")
    strengthening = str(intelligence.get("eps_surprise_trend") or "UNAVAILABLE")
    revenue_trend = str(intelligence.get("revenue_surprise_trend") or "UNAVAILABLE")
    trend = (
        "strengthening" if strengthening == "IMPROVING" and revenue_trend in {"IMPROVING", "UNAVAILABLE"}
        else "weakening" if strengthening == "DETERIORATING" or revenue_trend == "DETERIORATING"
        else "mixed or volatile"
    )
    watch = "Watch the next reported EPS and revenue surprises and whether the current surprise trend persists."
    return {
        "semantic_status": AVAILABLE,
        "what_happened": happened + (" " + "; ".join(details) + "." if details else ""),
        "what_improved": "EPS surprise momentum improved." if strengthening == "IMPROVING" else "No consistently improving EPS-surprise sequence is verified.",
        "what_deteriorated": "At least one surprise sequence is deteriorating." if "DETERIORATING" in {strengthening, revenue_trend} else "No consistently deteriorating surprise sequence is verified.",
        "trend_assessment": f"The reported earnings trend is {trend}.",
        "watch_next": watch,
        "management_evidence_note": "Atlas has not verified management guidance or transcript evidence.",
        "summary": f"{happened} The reported earnings trend is {trend}. {watch}",
    }


def build_management_guidance(row: Mapping[str, Any], *, is_etf: bool = False) -> dict[str, Any]:
    if is_etf:
        return {"version": "MANAGEMENT_GUIDANCE_V1", "semantic_status": NOT_APPLICABLE, "status_detail": "Management guidance does not apply to ETFs."}
    candidate = row.get("management_guidance")
    if not isinstance(candidate, Mapping):
        return {"version": "MANAGEMENT_GUIDANCE_V1", "semantic_status": DATA_UNAVAILABLE, "status_detail": "No verified company or filing guidance evidence is available."}
    source, date = candidate.get("source"), candidate.get("date") or candidate.get("as_of")
    fields = {key: candidate.get(key) for key in ("revenue_guidance", "eps_guidance", "margin_guidance", "capex_guidance", "guidance_direction", "previous_guidance")}
    if not source or not date or not any(value not in (None, "", [], {}) for value in fields.values()):
        return {"version": "MANAGEMENT_GUIDANCE_V1", "semantic_status": DATA_UNAVAILABLE, "status_detail": "Guidance was not published because verified source/date evidence is incomplete."}
    return {"version": "MANAGEMENT_GUIDANCE_V1", "semantic_status": AVAILABLE, **fields, "source": source, "date": date}


def build_transcript_intelligence(row: Mapping[str, Any], *, is_etf: bool = False) -> dict[str, Any]:
    if is_etf:
        return {"version": "TRANSCRIPT_INTELLIGENCE_V1", "semantic_status": NOT_APPLICABLE, "status_detail": "Corporate transcripts do not apply to ETFs."}
    candidate = row.get("transcript_intelligence")
    content_fields = (
        "management_themes", "demand_commentary", "margin_commentary", "pricing",
        "capex", "product_commentary", "risks", "analyst_qa_concerns",
    )
    if (
        not isinstance(candidate, Mapping)
        or not candidate.get("verified_source")
        or not candidate.get("call_date")
        or not any(candidate.get(key) not in (None, "", [], {}) for key in content_fields)
    ):
        return {"version": "TRANSCRIPT_INTELLIGENCE_V1", "semantic_status": DATA_UNAVAILABLE, "status_detail": "Transcript intelligence not yet available."}
    fields = ("fiscal_quarter", "call_date", "verified_source", "provider", "management_themes", "demand_commentary", "margin_commentary", "pricing", "capex", "product_commentary", "risks", "analyst_qa_concerns")
    return {"version": "TRANSCRIPT_INTELLIGENCE_V1", "semantic_status": AVAILABLE, **{key: candidate.get(key) for key in fields}}


__all__ = [
    "build_earnings_intelligence", "build_earnings_summary",
    "build_management_guidance", "build_transcript_intelligence",
]
