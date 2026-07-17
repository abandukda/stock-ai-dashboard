"""
Atlas V89 — Final AI Decision Engine

New file:
    engines/ai_decision_engine.py

Purpose
-------
Convert the complete Atlas intelligence stack into one explainable,
risk-controlled investment decision.

Primary entry point
-------------------
    from engines.ai_decision_engine import build_ai_decision

    decision = build_ai_decision(stock_row)

The engine consumes the V88 narrative output when available and returns:
- final action;
- conviction;
- probability of thesis success;
- expected return;
- expected drawdown;
- entry guidance;
- position-size guidance;
- time horizon;
- risk level;
- strongest reason;
- biggest risk;
- what would change Atlas's mind;
- a plain-language "Would Atlas buy today?" answer.

Design principles
-----------------
1. Missing data remains missing; it is never converted into fake zeroes.
2. A large fair-value gap alone cannot create a Buy Now decision.
3. Weak technical confirmation reduces urgency, not necessarily long-term quality.
4. Position sizing is capped by risk, completeness, and conviction.
5. The result is deterministic and testable; it makes no external API calls.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence
import math
import re


_MISSING = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "nan",
    "unavailable",
    "under review",
    "not available",
    "not reported",
    "-",
    "—",
}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text.lower() in _MISSING else text


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    text = (
        str(value)
        .replace(",", "")
        .replace("$", "")
        .replace("%", "")
        .strip()
    )
    if text.lower() in _MISSING:
        return default
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    try:
        return float(match.group(0))
    except ValueError:
        return default


def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in _MISSING:
            continue
        return value
    return default


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\n|•]+", value)
        return [part.strip(" -\t") for part in parts if part.strip(" -\t")]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        result: List[str] = []
        for item in value:
            if isinstance(item, Mapping):
                item = _first(item, "headline", "title", "summary", "text", "reason")
            text = _text(item)
            if text:
                result.append(text)
        return result
    text = _text(value)
    return [text] if text else []


def _dedupe(items: Iterable[str], limit: int | None = None) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        text = _text(item)
        if not text:
            continue
        key = re.sub(r"\s+", " ", text.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _pct(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f}%"


def _money(value: float | None) -> str:
    return "Unavailable" if value is None else f"${value:,.2f}"


def _upside(price: float | None, target: float | None) -> float | None:
    if price is None or target is None or price <= 0:
        return None
    return ((target - price) / price) * 100.0


def _safe_narrative(row: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        from engines.atlas_narrative_engine import build_atlas_narrative

        output = build_atlas_narrative(row)
        if isinstance(output, Mapping):
            return dict(output)
    except Exception:
        pass
    return {}


def _normalized_action(value: Any) -> str:
    text = _text(value, "Wait for Confirmation").replace("_", " ").strip().title()
    aliases = {
        "Strong Buy": "High Conviction Buy",
        "High Conviction Buy": "High Conviction Buy",
        "Buy": "Buy Now",
        "Buy Now": "Buy Now",
        "Accumulate": "Buy on Weakness",
        "Buy On Weakness": "Buy on Weakness",
        "Hold": "Wait for Confirmation",
        "Wait": "Wait for Confirmation",
        "Wait For Confirmation": "Wait for Confirmation",
        "Avoid": "Avoid",
        "Sell": "Avoid",
    }
    return aliases.get(text, text)


def _bool(row: Mapping[str, Any], *keys: str) -> bool | None:
    value = _first(row, *keys)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    number = _num(value)
    if number is not None:
        return number > 0
    text = _text(value).lower()
    if text in {"true", "yes", "above", "bullish"}:
        return True
    if text in {"false", "no", "below", "bearish"}:
        return False
    return None


def _research_completeness(narrative: Mapping[str, Any], row: Mapping[str, Any]) -> float:
    completeness = narrative.get("research_completeness")
    if isinstance(completeness, Mapping):
        pct = _num(completeness.get("percent"))
        if pct is not None:
            return _clamp(pct)

    verified = sum(
        [
            _first(row, "Revenue Growth", "revenue_growth") is not None,
            _first(row, "Operating Margin", "operating_margin") is not None,
            _first(row, "Free Cash Flow", "free_cash_flow") is not None,
            _first(row, "Atlas Fair Value", "atlas_fair_value") is not None,
            _first(row, "Wall Street Consensus", "analyst_target") is not None,
            _first(row, "RSI", "rsi") is not None,
            _first(row, "news_items", "latest_news", "news") is not None,
            _first(row, "earnings_summary", "guidance_summary") is not None,
        ]
    )
    return verified / 8 * 100.0


def _technical_confirmation(row: Mapping[str, Any], narrative: Mapping[str, Any]) -> float:
    scorecard = narrative.get("evidence_scorecard")
    if isinstance(scorecard, Mapping):
        score = _num(scorecard.get("technicals"))
        if score is not None:
            return _clamp(score)

    score = 50.0
    above_50 = _bool(row, "Above 50DMA", "above_50dma", "price_above_sma50")
    above_200 = _bool(row, "Above 200DMA", "above_200dma", "price_above_sma200")
    rsi = _num(_first(row, "RSI", "rsi"))
    relative_volume = _num(
        _first(row, "Relative Volume", "relative_volume", "relativeVolume")
    )

    if above_50 is True:
        score += 12
    elif above_50 is False:
        score -= 10

    if above_200 is True:
        score += 14
    elif above_200 is False:
        score -= 14

    if rsi is not None:
        if 45 <= rsi <= 65:
            score += 8
        elif rsi >= 75:
            score -= 10
        elif rsi < 35:
            score -= 5

    if relative_volume is not None:
        if relative_volume >= 1.2:
            score += 6
        elif relative_volume < 0.7:
            score -= 4

    return _clamp(score)


def _fundamental_confirmation(row: Mapping[str, Any], narrative: Mapping[str, Any]) -> float:
    scorecard = narrative.get("evidence_scorecard")
    if isinstance(scorecard, Mapping):
        business = _num(scorecard.get("business"))
        financials = _num(scorecard.get("financials"))
        values = [value for value in (business, financials) if value is not None]
        if values:
            return _clamp(sum(values) / len(values))

    score = 50.0
    revenue_growth = _num(
        _first(row, "Revenue Growth", "revenue_growth", "revenueGrowth")
    )
    eps_growth = _num(_first(row, "EPS Growth", "eps_growth", "earningsGrowth"))
    operating_margin = _num(
        _first(row, "Operating Margin", "operating_margin", "operatingMargins")
    )
    free_cash_flow = _num(
        _first(row, "Free Cash Flow", "free_cash_flow", "freeCashflow")
    )

    if revenue_growth is not None:
        score += 16 if revenue_growth >= 15 else 7 if revenue_growth > 0 else -10
    if eps_growth is not None:
        score += 14 if eps_growth >= 15 else 6 if eps_growth > 0 else -10
    if operating_margin is not None:
        score += 12 if operating_margin >= 20 else 5 if operating_margin > 5 else -8
    if free_cash_flow is not None:
        score += 12 if free_cash_flow > 0 else -16

    return _clamp(score)


def _valuation_confirmation(
    row: Mapping[str, Any],
    narrative: Mapping[str, Any],
) -> tuple[float, float | None]:
    scorecard = narrative.get("evidence_scorecard")
    score = None
    if isinstance(scorecard, Mapping):
        score = _num(scorecard.get("valuation"))

    expected_return = _num(
        narrative.get("expected_return_pct"),
        _num(
            _first(
                row,
                "Expected Return",
                "expected_return",
                "Atlas Expected Return",
            )
        ),
    )

    if expected_return is None:
        price = _num(_first(row, "Current Price", "current_price", "Price", "Close"))
        fair_value = _num(
            _first(row, "Atlas Fair Value", "atlas_fair_value", "fair_value")
        )
        expected_return = _upside(price, fair_value)

    if score is None:
        score = 50.0
        if expected_return is not None:
            if 15 <= expected_return <= 60:
                score += 25
            elif 5 <= expected_return < 15:
                score += 10
            elif expected_return < 0:
                score -= 15
            elif expected_return > 60:
                score += 7

    return _clamp(score), expected_return


def _risk_penalty(
    row: Mapping[str, Any],
    risks: Sequence[str],
    technical_score: float,
    completeness: float,
) -> float:
    penalty = 0.0

    current_ratio = _num(
        _first(row, "Current Ratio", "current_ratio", "currentRatio")
    )
    debt_to_equity = _num(
        _first(row, "Debt to Equity", "debt_to_equity", "debtToEquity")
    )
    forward_pe = _num(_first(row, "Forward P/E", "forward_pe", "forwardPE"))
    beta = _num(_first(row, "Beta", "beta"))

    if current_ratio is not None and 0 < current_ratio < 1:
        penalty += 6
    if debt_to_equity is not None and debt_to_equity > 200:
        penalty += 7
    if forward_pe is not None and forward_pe > 50:
        penalty += 6
    if beta is not None and beta > 1.8:
        penalty += 5
    if technical_score < 45:
        penalty += 7
    if completeness < 50:
        penalty += 8

    penalty += min(len(risks), 5) * 1.5
    return min(30.0, penalty)


def _position_size(
    action: str,
    conviction: float,
    risk_level: str,
    completeness: float,
) -> Dict[str, Any]:
    if action == "Avoid":
        return {
            "recommended_pct": 0.0,
            "range": "0%",
            "guidance": "Do not initiate a position under the current evidence set.",
        }

    base = {
        "High Conviction Buy": 4.0,
        "Buy Now": 3.0,
        "Buy on Weakness": 2.0,
        "Wait for Confirmation": 0.75,
    }.get(action, 1.0)

    if conviction >= 90:
        base += 0.5
    elif conviction < 65:
        base -= 0.5

    if risk_level == "High":
        base *= 0.50
    elif risk_level == "Moderate":
        base *= 0.75

    if completeness < 60:
        base *= 0.70

    base = max(0.0, min(5.0, round(base, 2)))
    low = max(0.0, round(base * 0.75, 1))
    high = round(base * 1.25, 1)

    return {
        "recommended_pct": base,
        "range": f"{low:.1f}%–{high:.1f}%",
        "guidance": (
            "Use the lower end when entering before earnings or without technical confirmation."
        ),
    }


def _entry_guidance(
    row: Mapping[str, Any],
    action: str,
    risk_level: str,
) -> Dict[str, Any]:
    price = _num(_first(row, "Current Price", "current_price", "Price", "Close"))
    support = _num(
        _first(row, "Support", "support", "Ideal Entry", "ideal_entry")
    )
    atr_pct = _num(_first(row, "ATR %", "atr_pct", "ATR Percent"))
    sma20 = _num(_first(row, "SMA20", "sma20", "20DMA"))
    sma50 = _num(_first(row, "SMA50", "sma50", "50DMA"))

    references = [value for value in (support, sma20, sma50) if value is not None and value > 0]
    anchor = min(references, key=lambda value: abs(value - price)) if price is not None and references else support

    if price is None:
        return {
            "current_price": None,
            "ideal_entry": None,
            "entry_zone": "Unavailable",
            "instruction": "Current price is unavailable; do not generate a precise entry.",
        }

    if atr_pct is None or atr_pct <= 0:
        atr_pct = 3.0 if risk_level != "High" else 4.5

    if action in {"High Conviction Buy", "Buy Now"}:
        center = price if anchor is None else min(price, anchor * 1.02)
        low = center * (1 - atr_pct / 200)
        high = center * (1 + atr_pct / 300)
        instruction = "Begin with a partial position inside the zone; add only if the thesis confirms."
    elif action == "Buy on Weakness":
        center = anchor if anchor is not None else price * 0.96
        low = center * (1 - atr_pct / 200)
        high = center * (1 + atr_pct / 300)
        instruction = "Wait for price to move into the preferred zone rather than chasing."
    elif action == "Avoid":
        return {
            "current_price": price,
            "ideal_entry": None,
            "entry_zone": "No entry",
            "instruction": "Do not initiate a position while the recommendation remains Avoid.",
        }
    else:
        center = anchor if anchor is not None else price * 0.97
        low = center * (1 - atr_pct / 250)
        high = center * (1 + atr_pct / 350)
        instruction = "Wait for technical or catalyst confirmation before initiating more than a starter position."

    return {
        "current_price": round(price, 2),
        "ideal_entry": round(center, 2),
        "entry_low": round(low, 2),
        "entry_high": round(high, 2),
        "entry_zone": f"${low:,.2f}–${high:,.2f}",
        "instruction": instruction,
    }


def _expected_drawdown(
    row: Mapping[str, Any],
    risk_level: str,
    technical_score: float,
) -> float:
    atr_pct = _num(_first(row, "ATR %", "atr_pct", "ATR Percent"))
    beta = _num(_first(row, "Beta", "beta"))

    drawdown = 8.0
    if atr_pct is not None:
        drawdown += min(atr_pct * 1.5, 12)
    if beta is not None and beta > 1:
        drawdown += min((beta - 1) * 5, 8)
    if technical_score < 45:
        drawdown += 5
    if risk_level == "High":
        drawdown += 6
    elif risk_level == "Moderate":
        drawdown += 3

    return round(min(35.0, max(5.0, drawdown)), 1)


def _risk_level(score: float, penalty: float, completeness: float) -> str:
    if penalty >= 18 or score < 50 or completeness < 40:
        return "High"
    if penalty >= 8 or score < 72 or completeness < 70:
        return "Moderate"
    return "Low to Moderate"


def _final_action(
    base_action: str,
    conviction: float,
    expected_return: float | None,
    technical_score: float,
    fundamental_score: float,
    completeness: float,
    risk_level: str,
) -> str:
    if conviction < 45 or fundamental_score < 40:
        return "Avoid"

    if expected_return is not None and expected_return < 0:
        return "Avoid" if conviction < 70 else "Wait for Confirmation"

    if completeness < 45:
        return "Wait for Confirmation"

    if (
        conviction >= 86
        and fundamental_score >= 68
        and technical_score >= 58
        and expected_return is not None
        and expected_return >= 15
        and risk_level != "High"
    ):
        return "High Conviction Buy"

    if (
        conviction >= 77
        and fundamental_score >= 62
        and technical_score >= 52
        and expected_return is not None
        and expected_return >= 10
        and risk_level != "High"
    ):
        return "Buy Now"

    if (
        conviction >= 65
        and fundamental_score >= 55
        and expected_return is not None
        and expected_return > 0
    ):
        return "Buy on Weakness"

    if base_action == "Avoid" and conviction < 60:
        return "Avoid"

    return "Wait for Confirmation"


def build_ai_decision(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Build one final explainable V89 investment decision."""

    narrative = _safe_narrative(row)

    ticker = _text(_first(row, "Ticker", "ticker", "symbol"), "UNKNOWN").upper()
    company = _text(
        _first(row, "Company", "company", "Name", "longName"),
        ticker,
    )

    evidence = _dedupe(
        _listify(narrative.get("why_atlas_likes_it"))
        + _listify(narrative.get("supporting_evidence")),
        8,
    )
    risks = _dedupe(
        _listify(narrative.get("primary_risks"))
        + _listify(narrative.get("bear_case")),
        6,
    )

    completeness = _research_completeness(narrative, row)
    technical_score = _technical_confirmation(row, narrative)
    fundamental_score = _fundamental_confirmation(row, narrative)
    valuation_score, expected_return = _valuation_confirmation(row, narrative)

    narrative_score = _num(
        narrative.get("overall_score"),
        _num(_first(row, "Confidence", "confidence"), 50),
    ) or 50.0

    base_action = _normalized_action(
        _first(
            narrative,
            "decision",
            default=_first(row, "Decision", "decision", "Verdict"),
        )
    )

    raw_conviction = (
        narrative_score * 0.28
        + fundamental_score * 0.25
        + valuation_score * 0.20
        + technical_score * 0.17
        + completeness * 0.10
    )

    penalty = _risk_penalty(row, risks, technical_score, completeness)
    conviction = _clamp(raw_conviction - penalty)

    provisional_risk = _risk_level(conviction, penalty, completeness)
    action = _final_action(
        base_action=base_action,
        conviction=conviction,
        expected_return=expected_return,
        technical_score=technical_score,
        fundamental_score=fundamental_score,
        completeness=completeness,
        risk_level=provisional_risk,
    )
    risk_level = _risk_level(conviction, penalty, completeness)

    # Probability is intentionally more conservative than conviction.
    probability = _clamp(
        conviction * 0.82
        + completeness * 0.10
        + max(0.0, min(8.0, (expected_return or 0.0) / 10.0))
    )

    drawdown = _expected_drawdown(row, risk_level, technical_score)
    entry = _entry_guidance(row, action, risk_level)
    position = _position_size(action, conviction, risk_level, completeness)

    strongest_reason = evidence[0] if evidence else (
        "The current evidence set does not contain a sufficiently strong positive driver."
    )
    biggest_risk = risks[0] if risks else (
        "Execution may fall short of the assumptions embedded in the valuation."
    )

    would_buy_today = action in {"High Conviction Buy", "Buy Now"}
    buy_answer = "YES" if would_buy_today else "NO"

    if action == "Buy on Weakness":
        buy_answer = "NOT YET — WAIT FOR A BETTER ENTRY"
    elif action == "Wait for Confirmation":
        buy_answer = "NOT YET — WAIT FOR CONFIRMATION"
    elif action == "Avoid":
        buy_answer = "NO"

    what_changes_mind = _dedupe(
        _listify(narrative.get("thesis_invalidation"))
        + [
            "A material deterioration in revenue, earnings, margins, or free cash flow.",
            "Management lowers guidance or analysts cut estimates materially.",
            "The stock loses long-term technical support without a fundamental explanation.",
            "Atlas Fair Value falls below the market price after refreshed fundamentals.",
        ],
        5,
    )

    verdict_reason = (
        f"{strongest_reason} The biggest offsetting risk is that {biggest_risk.lower()}"
    )

    summary = (
        f"Atlas rates {company} ({ticker}) as {action} with conviction of "
        f"{conviction:.0f}/100 and an estimated {probability:.0f}% probability that "
        f"the thesis succeeds over the stated horizon. "
        + (
            f"Modeled upside is {_pct(expected_return)}. "
            if expected_return is not None
            else "Modeled upside is unavailable. "
        )
        + f"Would Atlas buy today? {buy_answer}."
    )

    return {
        "version": "V89",
        "ticker": ticker,
        "company": company,
        "action": action,
        "base_action": base_action,
        "conviction": round(conviction),
        "probability_thesis_success": round(probability),
        "expected_return_pct": expected_return,
        "expected_drawdown_pct": drawdown,
        "risk_level": risk_level,
        "time_horizon": _text(
            _first(narrative, "verdict", default={}).get("time_horizon")
            if isinstance(narrative.get("verdict"), Mapping)
            else None,
            "12–18 months",
        ),
        "would_atlas_buy_today": would_buy_today,
        "buy_today_answer": buy_answer,
        "entry": entry,
        "position_size": position,
        "strongest_reason": strongest_reason,
        "biggest_risk": biggest_risk,
        "supporting_evidence": evidence,
        "primary_risks": risks,
        "what_would_change_atlas_mind": what_changes_mind,
        "decision_reason": verdict_reason,
        "research_completeness_pct": round(completeness),
        "component_scores": {
            "narrative": round(narrative_score, 1),
            "fundamentals": round(fundamental_score, 1),
            "valuation": round(valuation_score, 1),
            "technicals": round(technical_score, 1),
            "completeness": round(completeness, 1),
            "risk_penalty": round(penalty, 1),
        },
        "summary": summary,
        "card": {
            "rating": action,
            "conviction": f"{conviction:.0f}/100",
            "probability": f"{probability:.0f}%",
            "expected_return": _pct(expected_return),
            "expected_drawdown": _pct(drawdown),
            "risk": risk_level,
            "entry_zone": entry.get("entry_zone", "Unavailable"),
            "position_size": position.get("range", "Unavailable"),
            "time_horizon": _text(
                _first(narrative, "verdict", default={}).get("time_horizon")
                if isinstance(narrative.get("verdict"), Mapping)
                else None,
                "12–18 months",
            ),
            "would_buy_today": buy_answer,
        },
        "narrative": narrative,
    }


# Compatibility aliases.
build_final_decision = build_ai_decision
generate_ai_decision = build_ai_decision


__all__ = [
    "build_ai_decision",
    "build_final_decision",
    "generate_ai_decision",
]
