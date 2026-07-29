
"""Grounded Atlas intelligence for executive summaries and today's move.

This module never invents current events. It derives narrative only from the
normalized V2 research report and labels conclusions as facts, inferences, or
data limitations.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import math


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text and text.lower() not in {
        "none", "null", "nan", "unavailable", "under review"
    } else default


def _first_sentence(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    for separator in (". ", "\n", "; "):
        if separator in text:
            return text.split(separator, 1)[0].strip() + "."
    return text


def _news_items(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    section = (report.get("sections") or {}).get("news") or {}
    data = section.get("data") or []
    return [item for item in data if isinstance(item, Mapping)]


def _today_change(report: Mapping[str, Any]) -> float | None:
    quote = report.get("quote") or {}
    for key in (
        "change_pct", "percent_change", "day_change_pct",
        "regular_market_change_percent", "regularMarketChangePercent",
    ):
        value = _num(quote.get(key))
        if value is not None:
            return value
    technical = ((report.get("sections") or {}).get("technical") or {}).get("data") or {}
    for key in ("day_change_pct", "change_pct", "one_day_pct"):
        value = _num(technical.get(key))
        if value is not None:
            return value
    return None


def _relative_volume(report: Mapping[str, Any]) -> float | None:
    technical = ((report.get("sections") or {}).get("technical") or {}).get("data") or {}
    for key in ("volume_ratio", "relative_volume", "relative_volume_ratio"):
        value = _num(technical.get(key))
        if value is not None:
            return value
    return None


def build_today_move(report: Mapping[str, Any]) -> dict[str, Any]:
    change = _today_change(report)
    relative_volume = _relative_volume(report)
    news = _news_items(report)

    verified: list[str] = []
    inferences: list[str] = []
    limitations: list[str] = []

    if change is not None:
        direction = "higher" if change > 0 else "lower" if change < 0 else "flat"
        verified.append(
            f"The stock is trading {direction} by {abs(change):.1f}% in the loaded market data."
        )
    else:
        limitations.append("A verified intraday percentage move was not included.")

    if relative_volume is not None:
        verified.append(f"Relative volume is {relative_volume:.2f}× normal.")
        if relative_volume >= 2:
            inferences.append("Trading participation is unusually elevated.")
        elif relative_volume >= 1.25:
            inferences.append("Volume confirms above-average investor attention.")
        elif relative_volume < 0.75:
            inferences.append("The move is occurring on relatively light participation.")
    else:
        limitations.append("Relative-volume data were not populated.")

    material_headlines = []
    for item in news[:8]:
        headline = _text(item.get("headline") or item.get("title"))
        if headline:
            material_headlines.append(headline)
    if material_headlines:
        verified.append(f"Atlas reviewed {len(material_headlines)} recent verified news items.")
    else:
        limitations.append("No recent verified news items were loaded for cause attribution.")

    sentiment_values = [
        _text(item.get("sentiment")).lower()
        for item in news
        if _text(item.get("sentiment"))
    ]
    positive = sum("positive" in value or "bull" in value for value in sentiment_values)
    negative = sum("negative" in value or "bear" in value for value in sentiment_values)

    if change is not None and change <= -3:
        if negative == 0 and material_headlines:
            inferences.append(
                "The decline appears larger than the negative company-specific news currently loaded; "
                "technical selling, profit-taking, sector pressure, or an unverified catalyst may be contributing."
            )
        elif negative > positive:
            inferences.append("Negative news flow is consistent with part of the selling pressure.")
    elif change is not None and change >= 3:
        if positive > negative:
            inferences.append("Positive news flow is directionally consistent with the advance.")
        elif material_headlines:
            inferences.append(
                "The advance is not fully explained by the sentiment labels in the loaded news set."
            )

    if not inferences:
        inferences.append(
            "Atlas does not yet have enough evidence to assign one dominant cause to today's move."
        )

    confidence = 35
    if change is not None:
        confidence += 20
    if relative_volume is not None:
        confidence += 15
    if material_headlines:
        confidence += 20
    if sentiment_values:
        confidence += 10
    confidence = min(95, confidence)

    headline = (
        f"Today's move: {change:+.1f}%"
        if change is not None
        else "Today's move is under review"
    )

    return {
        "headline": headline,
        "verified_facts": verified,
        "atlas_inferences": inferences,
        "data_limitations": limitations,
        "explanation_confidence_pct": confidence,
        "top_headlines": material_headlines[:5],
    }


def build_executive_intelligence(report: Mapping[str, Any]) -> dict[str, Any]:
    sections = report.get("sections") or {}
    financial = sections.get("financials") or {}
    earnings = sections.get("earnings") or {}
    analysts = sections.get("analysts") or {}
    news = sections.get("news") or {}
    technical = sections.get("technical") or {}
    risk = sections.get("risk") or {}

    verdict = _text(report.get("committee_verdict"), "MONITOR").replace("_", " ").title()
    opportunity = _num(report.get("opportunity_score"))
    confidence = _num(report.get("confidence_pct"))
    expected_return = _num(report.get("expected_return_pct"))

    supports: list[str] = []
    concerns: list[str] = []

    for section in (financial, earnings, analysts, news, technical):
        interpretation = _first_sentence(section.get("interpretation"))
        if interpretation and len(supports) < 5:
            supports.append(interpretation)

    bull_case = report.get("bull_case") or []
    for item in bull_case:
        text = _text(item)
        if text and text not in supports and len(supports) < 6:
            supports.append(text)

    bear_case = report.get("bear_case") or []
    for item in bear_case:
        text = _text(item)
        if text and len(concerns) < 5:
            concerns.append(text)

    risk_interpretation = _first_sentence(risk.get("interpretation"))
    if risk_interpretation and len(concerns) < 5:
        concerns.append(risk_interpretation)

    if expected_return is not None:
        if expected_return >= 12:
            supports.insert(0, f"Validated expected return is {expected_return:.1f}%.")
        elif expected_return < 5:
            concerns.insert(0, f"Validated expected return is limited at {expected_return:.1f}%.")

    upgrade_triggers = list(report.get("upgrade_triggers") or [])
    downgrade_triggers = list(report.get("downgrade_triggers") or [])

    if not upgrade_triggers:
        plan = report.get("trade_plan") or {}
        if not plan.get("actionable"):
            upgrade_triggers.append("A reliable current quote and actionable entry plan become available.")
        if confidence is not None and confidence < 66:
            upgrade_triggers.append("Research confidence improves above 66%.")
        upgrade_triggers.append("Earnings, guidance, or technical confirmation improves without valuation deterioration.")

    if not downgrade_triggers:
        downgrade_triggers = [
            "Management guidance or earnings estimates deteriorate materially.",
            "Validated fair value falls below the current market price.",
            "Price breaks key support on sustained heavy selling volume.",
        ]

    today_move = build_today_move(report)

    summary_parts = [f"Atlas currently rates this stock {verdict}."]
    if opportunity is not None and confidence is not None:
        summary_parts.append(
            f"The opportunity score is {opportunity:.1f}/100 with {confidence:.1f}% confidence."
        )
    if supports:
        summary_parts.append("The strongest support is: " + " ".join(supports[:2]))
    if concerns:
        summary_parts.append("The main caution is: " + concerns[0])
    summary = " ".join(summary_parts)

    return {
        "executive_summary": summary,
        "why_atlas_supports_it": supports[:6],
        "key_risks": concerns[:6],
        "upgrade_triggers": upgrade_triggers[:5],
        "downgrade_triggers": downgrade_triggers[:5],
        "today_move": today_move,
        "evidence_note": (
            "Narrative is grounded in the current normalized Atlas report. "
            "Unavailable evidence is not inferred as positive or negative."
        ),
    }


__all__ = ["build_executive_intelligence", "build_today_move"]
