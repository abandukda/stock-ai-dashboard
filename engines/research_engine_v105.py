"""
Atlas V105 — Institutional Research Engine

Builds an evidence-based institutional research report from a V104/V103
scored candidate. The engine is deterministic and read-only. It does not
fabricate missing data; unavailable evidence is explicitly marked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from engines.semantic_fields import canonical_atlas_fair_value
import math


@dataclass(frozen=True)
class ResearchCase:
    label: str
    fair_value: float | None
    expected_return_pct: float | None
    probability_pct: float


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _level(score: float | None, *, inverse: bool = False) -> str:
    if score is None:
        return "Under review"

    adjusted = 100.0 - score if inverse else score

    if adjusted >= 80:
        return "Very Strong"
    if adjusted >= 68:
        return "Strong"
    if adjusted >= 55:
        return "Moderate"
    if adjusted >= 42:
        return "Limited"
    return "Weak"


def _risk_level(score: float | None) -> str:
    if score is None:
        return "Under review"
    if score >= 72:
        return "Low"
    if score >= 58:
        return "Moderate"
    if score >= 42:
        return "Elevated"
    return "High"


def _safe_case(
    label: str,
    fair_value: float | None,
    current_price: float | None,
    probability_pct: float,
) -> ResearchCase:
    expected_return = (
        (fair_value - current_price) / current_price * 100.0
        if fair_value is not None and current_price and current_price > 0
        else None
    )

    return ResearchCase(
        label=label,
        fair_value=round(fair_value, 2) if fair_value is not None else None,
        expected_return_pct=(
            round(expected_return, 1)
            if expected_return is not None
            else None
        ),
        probability_pct=round(probability_pct, 1),
    )


def _fair_value_cases(row: Mapping[str, Any]) -> list[ResearchCase]:
    current_price = _num(row.get("current_price"))
    base_value = canonical_atlas_fair_value(row)

    if current_price is None or base_value is None:
        return [
            _safe_case("Bear", None, current_price, 25.0),
            _safe_case("Base", None, current_price, 50.0),
            _safe_case("Bull", None, current_price, 25.0),
        ]

    confidence = _num(row.get("confidence_pct"), 60.0) or 60.0
    spread = max(0.08, min(0.24, (100.0 - confidence) / 180.0))

    bear_value = base_value * (1.0 - spread)
    bull_value = base_value * (1.0 + spread)

    bear_probability = max(15.0, min(35.0, 40.0 - confidence * 0.18))
    bull_probability = max(15.0, min(35.0, confidence * 0.22))
    base_probability = 100.0 - bear_probability - bull_probability

    return [
        _safe_case(
            "Bear",
            bear_value,
            current_price,
            bear_probability,
        ),
        _safe_case(
            "Base",
            base_value,
            current_price,
            base_probability,
        ),
        _safe_case(
            "Bull",
            bull_value,
            current_price,
            bull_probability,
        ),
    ]


def _executive_summary(row: Mapping[str, Any]) -> str:
    ticker = _text(row.get("ticker"), "The company")
    verdict = _text(
        row.get("committee_verdict")
        or row.get("action_code"),
        "MONITOR",
    ).replace("_", " ")

    score = _num(row.get("opportunity_score"))
    confidence = _num(row.get("confidence_pct"))
    return_pct = _num(row.get("expected_return_pct"))

    positives = list(row.get("positive_drivers") or [])
    blockers = list(row.get("reasons_to_wait") or [])

    positive_text = (
        ", ".join(str(item).rstrip(".") for item in positives[:3])
        if positives
        else "relative opportunity ranking and available evidence"
    )

    blocker_text = (
        str(blockers[0]).rstrip(".")
        if blockers
        else "no material blocker is currently identified"
    )

    score_text = (
        f"an opportunity score of {score:.1f}"
        if score is not None
        else "an incomplete opportunity score"
    )
    confidence_text = (
        f"{confidence:.1f}% confidence"
        if confidence is not None
        else "confidence still under review"
    )
    return_text = (
        f"validated upside of {return_pct:.1f}%"
        if return_pct is not None
        else "validated upside still under review"
    )

    return (
        f"{ticker} currently carries an Atlas {verdict} verdict with "
        f"{score_text}, {confidence_text}, and {return_text}. "
        f"The strongest supporting evidence includes {positive_text}. "
        f"The primary reason for caution is that {blocker_text.lower()}."
    )


def _earnings_intelligence(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("raw") or {}
    if not isinstance(raw, Mapping):
        raw = {}

    eps_surprise = _num(
        raw.get("eps_surprise_pct")
        or raw.get("EPS Surprise %")
    )
    revenue_surprise = _num(
        raw.get("revenue_surprise_pct")
        or raw.get("Revenue Surprise %")
    )
    guidance = _text(
        row.get("guidance")
        or raw.get("guidance")
        or raw.get("Guidance")
    )
    transcript = _text(
        raw.get("transcript_summary")
        or raw.get("Latest Earnings Summary")
        or raw.get("earnings_summary")
    )

    impact = 0.0
    if eps_surprise is not None:
        impact += max(-5.0, min(5.0, eps_surprise * 0.35))
    if revenue_surprise is not None:
        impact += max(-5.0, min(5.0, revenue_surprise * 0.30))
    if guidance:
        lower = guidance.lower()
        if any(word in lower for word in ("raised", "increased", "strong")):
            impact += 3.0
        elif any(word in lower for word in ("cut", "lowered", "weak")):
            impact -= 3.0

    interpretation = "Neutral"
    if impact >= 4:
        interpretation = "Strongly Positive"
    elif impact >= 1:
        interpretation = "Positive"
    elif impact <= -4:
        interpretation = "Strongly Negative"
    elif impact <= -1:
        interpretation = "Negative"

    return {
        "eps_surprise_pct": eps_surprise,
        "revenue_surprise_pct": revenue_surprise,
        "guidance": guidance or "Not included in the current saved scan.",
        "transcript_summary": (
            transcript
            or "No structured transcript summary is available in the current saved scan."
        ),
        "confidence_impact_points": round(impact, 1),
        "interpretation": interpretation,
    }


def _wall_street(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("raw") or {}
    if not isinstance(raw, Mapping):
        raw = {}

    buy = _num(
        raw.get("analyst_buy_count")
        or raw.get("Buy Ratings")
    )
    hold = _num(
        raw.get("analyst_hold_count")
        or raw.get("Hold Ratings")
    )
    sell = _num(
        raw.get("analyst_sell_count")
        or raw.get("Sell Ratings")
    )

    average_target = _num(
        raw.get("analyst_target_mean")
        or raw.get("Analyst Target")
    )
    high_target = _num(
        raw.get("analyst_target_high")
        or raw.get("Analyst Target High")
    )
    low_target = _num(
        raw.get("analyst_target_low")
        or raw.get("Analyst Target Low")
    )

    analyst_component = _num(
        (row.get("components") or {}).get("analyst")
    )

    alignment = "Under review"
    if analyst_component is not None:
        if analyst_component >= 70:
            alignment = "Atlas broadly agrees with Wall Street."
        elif analyst_component <= 45:
            alignment = "Atlas is more cautious than Wall Street."
        else:
            alignment = "Atlas sees mixed Wall Street confirmation."

    return {
        "buy_count": int(buy) if buy is not None else None,
        "hold_count": int(hold) if hold is not None else None,
        "sell_count": int(sell) if sell is not None else None,
        "average_target": average_target,
        "high_target": high_target,
        "low_target": low_target,
        "atlas_alignment": alignment,
    }


def _risk_matrix(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    components = row.get("components") or {}

    fundamentals = _num(components.get("fundamentals"))
    valuation = _num(components.get("valuation"))
    technical = _num(components.get("technical"))
    institutional = _num(components.get("institutional"))
    political = _num(components.get("political"))
    macro = _num(components.get("macro"))
    risk_support = _num(components.get("risk"))

    return [
        {
            "category": "Financial",
            "support_score": fundamentals,
            "risk_level": _risk_level(fundamentals),
        },
        {
            "category": "Valuation",
            "support_score": valuation,
            "risk_level": _risk_level(valuation),
        },
        {
            "category": "Technical",
            "support_score": technical,
            "risk_level": _risk_level(technical),
        },
        {
            "category": "Institutional",
            "support_score": institutional,
            "risk_level": _risk_level(institutional),
        },
        {
            "category": "Political / Regulatory",
            "support_score": political,
            "risk_level": _risk_level(political),
        },
        {
            "category": "Macro",
            "support_score": macro,
            "risk_level": _risk_level(macro),
        },
        {
            "category": "Overall Risk Support",
            "support_score": risk_support,
            "risk_level": _risk_level(risk_support),
        },
    ]


def _checklist(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    components = row.get("components") or {}

    checks = [
        (
            "Fundamental quality",
            _num(components.get("fundamentals")),
            60.0,
        ),
        (
            "Valuation support",
            _num(components.get("valuation")),
            58.0,
        ),
        (
            "Technical confirmation",
            _num(components.get("technical")),
            58.0,
        ),
        (
            "Analyst support",
            _num(components.get("analyst")),
            58.0,
        ),
        (
            "Institutional support",
            _num(components.get("institutional")),
            58.0,
        ),
        (
            "Political / policy support",
            _num(components.get("political")),
            55.0,
        ),
        (
            "Evidence coverage",
            _num(row.get("component_coverage_pct")),
            70.0,
        ),
        (
            "Confidence",
            _num(row.get("confidence_pct")),
            69.0,
        ),
    ]

    output = []
    for label, value, threshold in checks:
        output.append(
            {
                "label": label,
                "value": value,
                "threshold": threshold,
                "passed": value is not None and value >= threshold,
                "status": (
                    "Passed"
                    if value is not None and value >= threshold
                    else "Missing"
                    if value is None
                    else "Not passed"
                ),
            }
        )

    return output


def build_institutional_research(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    components = row.get("components") or {}

    report = {
        "version": "V105",
        "ticker": _text(row.get("ticker"), "UNKNOWN"),
        "company": _text(
            row.get("company"),
            _text(row.get("ticker"), "UNKNOWN"),
        ),
        "sector": _text(row.get("sector"), "Unknown"),
        "industry": _text(row.get("industry"), "Unknown"),
        "committee_verdict": _text(
            row.get("committee_verdict")
            or row.get("action_code"),
            "MONITOR",
        ),
        "opportunity_score": _num(row.get("opportunity_score")),
        "confidence_pct": _num(row.get("confidence_pct")),
        "current_price": _num(row.get("current_price")),
        "validated_fair_value": canonical_atlas_fair_value(row),
        "expected_return_pct": _num(
            row.get("expected_return_pct")
        ),
        "position_size_range": _text(
            row.get("position_size_range"),
            "0–2%",
        ),
        "executive_summary": _executive_summary(row),
        "investment_thesis": _text(
            row.get("investment_thesis"),
            "A structured investment thesis was not included in the current saved scan.",
        ),
        "bull_case": list(row.get("positive_drivers") or []),
        "bear_case": list(row.get("reasons_to_wait") or []),
        "primary_blocker": _text(
            row.get("primary_blocker"),
            "No structured blocker is currently available.",
        ),
        "fair_value_cases": [
            asdict(case)
            for case in _fair_value_cases(row)
        ],
        "earnings_intelligence": _earnings_intelligence(row),
        "wall_street": _wall_street(row),
        "institutional_score": _num(
            components.get("institutional")
        ),
        "insider_score": _num(
            components.get("insider")
        ),
        "political_score": _num(
            components.get("political")
        ),
        "technical_score": _num(
            components.get("technical")
        ),
        "fundamental_score": _num(
            components.get("fundamentals")
        ),
        "valuation_score": _num(
            components.get("valuation")
        ),
        "macro_score": _num(
            components.get("macro")
        ),
        "risk_matrix": _risk_matrix(row),
        "buy_checklist": _checklist(row),
        "component_scorecard": dict(components),
    }

    return report


def validate_research_contract(
    report: Mapping[str, Any],
) -> list[str]:
    errors = []

    if report.get("version") != "V105":
        errors.append("Invalid research version.")

    if not report.get("ticker"):
        errors.append("Ticker is required.")

    confidence = _num(report.get("confidence_pct"))
    if confidence is not None and not 0 <= confidence <= 100:
        errors.append("Confidence must be between 0 and 100.")

    cases = report.get("fair_value_cases") or []
    if len(cases) != 3:
        errors.append("Research report must include bear, base, and bull cases.")

    probabilities = sum(
        _num(case.get("probability_pct"), 0.0) or 0.0
        for case in cases
        if isinstance(case, Mapping)
    )
    if abs(probabilities - 100.0) > 0.2:
        errors.append("Fair-value case probabilities must total 100%.")

    return errors


__all__ = [
    "ResearchCase",
    "build_institutional_research",
    "validate_research_contract",
]
