"""
Atlas V103 — Institutional Scoring Engine

Scores both raw scanner rows and app-normalized rows.
It does not require the V102 canonical adapter to succeed first.
"""

from __future__ import annotations

from typing import Any, Mapping
import math


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {
            "", "none", "nan", "null", "n/a", "na",
            "unknown", "under review", "unavailable",
        }
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return True


def _num(value: Any, default=None):
    try:
        if not _present(value):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default=""):
    return str(value).strip() if _present(value) else default


def _sources(row: Mapping[str, Any]):
    raw = row.get("Raw")
    raw = raw if isinstance(raw, Mapping) else {}
    nested = row.get("raw")
    nested = nested if isinstance(nested, Mapping) else {}
    return (row, raw, nested)


def _first(row: Mapping[str, Any], *keys, default=None):
    for source in _sources(row):
        for key in keys:
            if key in source and _present(source.get(key)):
                return source.get(key)
    return default


def _committee_score(row: Mapping[str, Any], agent_name: str):
    committee = _first(row, "AI Committee", "ai_committee", default={})

    if isinstance(committee, Mapping):
        item = committee.get(agent_name)
        if isinstance(item, Mapping):
            return _num(item.get("score"))

    if isinstance(committee, list):
        for item in committee:
            if not isinstance(item, Mapping):
                continue
            name = _text(
                item.get("agent")
                or item.get("name")
                or item.get("Agent")
            )
            if name.lower() == agent_name.lower():
                return _num(item.get("score"))

    return None


def _clamp(value: float, low=0.0, high=100.0):
    return max(low, min(high, value))


def _pct_score(value, neutral=50.0, scale=1.0):
    value = _num(value)
    if value is None:
        return None
    return _clamp(neutral + value * scale)


def score_stock(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = _text(_first(row, "Ticker", "ticker", "symbol"), "UNKNOWN").upper()
    company = _text(
        _first(row, "Company", "company", "company_name", "name"),
        ticker,
    )
    sector = _text(_first(row, "Sector", "sector"), "Unknown")
    industry = _text(_first(row, "Industry", "industry"), sector)

    price = _num(
        _first(
            row,
            "Price",
            "Current Price",
            "current_price",
            "price",
            "last_price",
        )
    )
    conviction = _num(
        _first(
            row,
            "Final Conviction",
            "conviction",
            "conviction_score",
            "ai_score",
            "score",
        )
    )

    technical = (
        _committee_score(row, "Technical Agent")
        or _num(_first(row, "Technical Score", "technical_score"))
    )
    if technical is None:
        rsi = _num(_first(row, "RSI", "rsi"))
        trend_20 = _num(_first(row, "20D %", "twenty_day_pct"))
        volume = _num(_first(row, "Volume Ratio", "volume_ratio"))
        parts = []
        if rsi is not None:
            parts.append(_clamp(100 - abs(rsi - 58) * 2.2))
        if trend_20 is not None:
            parts.append(_clamp(50 + trend_20 * 2.0))
        if volume is not None:
            parts.append(_clamp(45 + volume * 20))
        technical = sum(parts) / len(parts) if parts else conviction

    fundamentals = (
        _committee_score(row, "Finance Agent")
        or _num(
            _first(
                row,
                "Finance Agent Score",
                "finance_agent_score",
                "Quality Score",
                "quality_score",
            )
        )
    )
    if fundamentals is None:
        revenue_growth = _num(
            _first(row, "Revenue Growth", "revenue_growth", "Revenue QoQ %")
        )
        eps_beats = _num(_first(row, "EPS Beats Last 4", "eps_beats_last4"))
        current_ratio = _num(_first(row, "Current Ratio", "current_ratio"))
        fcf = _num(_first(row, "Free Cash Flow", "free_cash_flow"))
        parts = []
        if revenue_growth is not None:
            parts.append(_clamp(50 + revenue_growth * 1.3))
        if eps_beats is not None:
            parts.append(_clamp(40 + eps_beats * 15))
        if current_ratio is not None and current_ratio > 0:
            parts.append(_clamp(40 + min(current_ratio, 3) * 15))
        if fcf is not None:
            parts.append(72 if fcf > 0 else 30)
        fundamentals = sum(parts) / len(parts) if parts else conviction

    analyst = _num(
        _first(
            row,
            "Analyst Support Score",
            "analyst_support_score",
            "Analyst Support",
        )
    )
    if analyst is None:
        analyst_count = _num(_first(row, "Analyst Count", "analyst_count"))
        analyst_upside = _num(
            _first(
                row,
                "analyst_upside_pct",
                "Target Upside %",
                "expected_upside_pct",
            )
        )
        parts = []
        if analyst_count is not None:
            parts.append(_clamp(45 + min(analyst_count, 40) * 1.1))
        if analyst_upside is not None:
            parts.append(_clamp(50 + analyst_upside * 0.7))
        analyst = sum(parts) / len(parts) if parts else conviction

    target = _num(
        _first(
            row,
            "Analyst Target",
            "analyst_target_mean",
            "AI Fair Value",
            "ai_base_target",
            "target",
        )
    )
    expected_return = (
        (target - price) / price * 100.0
        if price and target and price > 0
        else _num(
            _first(
                row,
                "Target Upside %",
                "expected_upside_pct",
                "upside",
            )
        )
    )
    valuation = (
        _clamp(48 + expected_return * 0.65)
        if expected_return is not None
        else conviction
    )

    institutional = _num(
        _first(
            row,
            "Institutional Score",
            "institutional_score",
            "smart_money_score",
        )
    )
    if institutional is None:
        institutional = _committee_score(row, "Institutional Agent")

    political = _num(
        _first(
            row,
            "Political Buying Score",
            "political_buying_score",
            "policymaker_disclosure_score",
            "congressional_trading_score",
        )
    )

    insider = _num(
        _first(
            row,
            "Insider Score",
            "insider_score",
        )
    )

    risk_reward = _num(_first(row, "Risk/Reward", "risk_reward"))
    risk = (
        _clamp(75 - risk_reward * 12)
        if risk_reward is not None and risk_reward > 0
        else 50.0
    )

    momentum = _num(_first(row, "20D %", "twenty_day_pct"))
    macro = 55.0
    if momentum is not None:
        macro = _clamp(52 + momentum * 0.8)

    components = {
        "fundamentals": fundamentals,
        "valuation": valuation,
        "technical": technical,
        "analyst": analyst,
        "institutional": institutional,
        "political": political,
        "insider": insider,
        "risk": 100 - risk if risk is not None else None,
        "macro": macro,
        "legacy_conviction": conviction,
    }

    weights = {
        "fundamentals": 0.20,
        "valuation": 0.15,
        "technical": 0.16,
        "analyst": 0.12,
        "institutional": 0.10,
        "political": 0.05,
        "insider": 0.05,
        "risk": 0.07,
        "macro": 0.05,
        "legacy_conviction": 0.05,
    }

    available = {
        key: _clamp(value)
        for key, value in components.items()
        if _num(value) is not None
    }
    coverage = (
        len(available) / len(components) * 100.0
        if components
        else 0.0
    )

    if len(available) < 3:
        opportunity_score = None
    else:
        total_weight = sum(weights[key] for key in available)
        opportunity_score = sum(
            available[key] * weights[key]
            for key in available
        ) / total_weight

    quote_type = _text(
        _first(row, "Quote Type", "quote_type", "quoteType"),
        "EQUITY",
    ).upper()

    excluded = quote_type not in {"EQUITY", "STOCK"}
    if sector.lower() in {
        "financial services",
        "financials",
        "entertainment",
        "gambling",
        "alcohol",
        "tobacco",
    }:
        excluded = True

    return {
        "ticker": ticker,
        "company": company,
        "sector": sector,
        "industry": industry,
        "quote_type": quote_type,
        "eligible": not excluded,
        "current_price": price,
        "validated_fair_value": target if price and target and 0.6 * price <= target <= 1.8 * price else None,
        "expected_return_pct": (
            round(expected_return, 1)
            if expected_return is not None and -60 <= expected_return <= 80
            else None
        ),
        "opportunity_score": (
            round(opportunity_score, 1)
            if opportunity_score is not None
            else None
        ),
        "component_coverage_pct": round(coverage, 1),
        "components": components,
        "investment_thesis": _text(
            _first(
                row,
                "Investment Thesis",
                "investment_thesis",
                "Committee Conclusion",
                "committee_conclusion",
            )
        ),
        "primary_risk": _text(
            _first(
                row,
                "Primary Risk",
                "what_could_go_wrong",
            )
        ),
        "guidance": _text(_first(row, "Guidance", "guidance", "ai_guidance")),
        "next_earnings_date": _text(
            _first(
                row,
                "Next Earnings Date",
                "next_earnings_date",
                "earnings_date",
            )
        ),
        "raw": dict(row),
    }


__all__ = ["score_stock"]
