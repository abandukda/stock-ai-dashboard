"""
Atlas V102.1 Canonical Scanner Adapter

Supports both:
1. raw scanner JSON fields; and
2. app-normalized rows containing Title Case fields plus a nested Raw object.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping
import math


EXCLUDED_SECTORS = {
    "financial services",
    "financials",
    "entertainment",
    "gambling",
    "alcohol",
    "tobacco",
}


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {
            "",
            "none",
            "nan",
            "null",
            "n/a",
            "na",
            "unknown",
            "under review",
            "unavailable",
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
    return (row, raw)


def _first(row: Mapping[str, Any], *keys, default=None):
    for source in _sources(row):
        for key in keys:
            if key in source and _present(source.get(key)):
                return source.get(key)
    return default


def _committee(row: Mapping[str, Any]):
    value = _first(row, "ai_committee", "AI Committee", default={})
    return value


def _agent(row: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    committee = _committee(row)

    if isinstance(committee, Mapping):
        value = committee.get(name)
        return value if isinstance(value, Mapping) else {}

    if isinstance(committee, list):
        for item in committee:
            if not isinstance(item, Mapping):
                continue
            agent_name = _text(
                item.get("agent")
                or item.get("name")
                or item.get("Agent")
            )
            if agent_name.lower() == name.lower():
                return item

    return {}


def _agent_score(row: Mapping[str, Any], name: str, *fallback_keys):
    value = _num(_agent(row, name).get("score"))
    if value is None:
        value = _num(_first(row, *fallback_keys))
    return None if value is None else max(0.0, min(100.0, value))


def _research_completeness(row: Mapping[str, Any]) -> float:
    checks = [
        _num(_first(row, "current_price", "price", "Price", "Current Price")),
        _agent_score(
            row,
            "Technical Agent",
            "technical_score",
            "Technical Score",
            "Final Conviction",
            "conviction",
        ),
        _agent_score(
            row,
            "Finance Agent",
            "finance_agent_score",
            "Finance Agent Score",
            "Quality Score",
            "quality_score",
        ),
        _num(
            _first(
                row,
                "analyst_support_score",
                "Analyst Support Score",
                "Final Conviction",
            )
        ),
        _text(_first(row, "investment_thesis", "Investment Thesis")),
        _text(
            _first(
                row,
                "latest_news_headline",
                "top_news_headline",
                "Latest News Headline",
            )
        ),
        _text(_first(row, "guidance", "ai_guidance", "Guidance")),
        _text(
            _first(
                row,
                "earnings_summary",
                "transcript_summary",
                "Latest Earnings Summary",
            )
        ),
        _text(
            _first(
                row,
                "political_support",
                "political_support_summary",
                "Political Support",
            )
        ),
        _text(
            _first(
                row,
                "institutional_activity",
                "institutional_summary",
                "Institutional Activity",
            )
        ),
    ]
    return round(sum(bool(value) for value in checks) / len(checks) * 100.0, 1)


def _policy_score(row: Mapping[str, Any]):
    direct = _num(
        _first(
            row,
            "government_policy_score",
            "political_score",
            "policy_support_score",
            "Government Policy Score",
            "Political Score",
        )
    )
    if direct is not None:
        return max(0.0, min(100.0, direct))

    text = " ".join(
        [
            _text(_first(row, "political_support", "Political Support")),
            _text(
                _first(
                    row,
                    "political_support_summary",
                    "Political Support Summary",
                )
            ),
        ]
    ).lower()

    if not text.strip():
        return None
    if any(
        word in text
        for word in (
            "tailwind",
            "support",
            "benefit",
            "contract",
            "incentive",
            "buying",
        )
    ):
        return 75.0
    if any(
        word in text
        for word in (
            "headwind",
            "restriction",
            "investigation",
            "risk",
            "selling",
        )
    ):
        return 30.0
    return 55.0


def _institutional_score(row: Mapping[str, Any]):
    direct = _num(
        _first(
            row,
            "institutional_score",
            "smart_money_score",
            "Institutional Score",
            "Smart Money Score",
        )
    )
    if direct is not None:
        return max(0.0, min(100.0, direct))

    agent = _agent_score(row, "Institutional Agent")
    if agent is not None:
        return agent

    text = " ".join(
        [
            _text(
                _first(
                    row,
                    "institutional_activity",
                    "Institutional Activity",
                )
            ),
            _text(
                _first(
                    row,
                    "institutional_summary",
                    "Institutional Summary",
                )
            ),
        ]
    ).lower()

    if not text.strip():
        return None
    if any(word in text for word in ("buying", "accumulation", "increased", "added")):
        return 80.0
    if any(word in text for word in ("selling", "distribution", "reduced")):
        return 30.0
    return 55.0


def _policymaker_score(row: Mapping[str, Any]):
    direct = _num(
        _first(
            row,
            "policymaker_disclosure_score",
            "congressional_trading_score",
            "political_buying_score",
            "Political Buying Score",
        )
    )
    if direct is not None:
        return max(0.0, min(100.0, direct))
    return None


def _safe_fair_value(row: Mapping[str, Any], price):
    analyst = _num(
        _first(
            row,
            "analyst_target_mean",
            "finnhub_target_mean",
            "Analyst Target",
        )
    )
    app_fair_value = _num(
        _first(
            row,
            "AI Fair Value",
            "Atlas Fair Value",
            "ai_base_target",
            "target",
        )
    )

    candidates = []
    for value in (analyst, app_fair_value):
        if value and price and 0.65 * price <= value <= 1.75 * price:
            candidates.append(value)

    return round(sum(candidates) / len(candidates), 2) if candidates else None


def _atlas_action(
    row: Mapping[str, Any],
    technical,
    finance,
    completeness,
    expected_return,
):
    passed = sum(
        [
            technical is not None and technical >= 60,
            finance is not None and finance >= 60,
            completeness >= 50,
            expected_return is not None and expected_return >= 8,
        ]
    )

    if passed == 4 and expected_return <= 60:
        return "BUY_NOW"
    if passed >= 3:
        return "ACCUMULATE"
    if finance is not None and finance < 40:
        return "AVOID"
    return "MONITOR"


def adapt_scanner_row(row: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(row)

    ticker = _text(
        _first(row, "ticker", "symbol", "Ticker"),
        "UNKNOWN",
    ).upper()
    company = _text(
        _first(
            row,
            "company",
            "company_name",
            "name",
            "Company",
        ),
        ticker,
    )
    sector = _text(_first(row, "sector", "Sector"), "Unknown")
    industry = _text(_first(row, "industry", "Industry"), sector)
    quote_type = _text(
        _first(row, "quote_type", "quoteType", "Quote Type"),
        "EQUITY",
    ).upper()

    price = _num(
        _first(
            row,
            "current_price",
            "price",
            "last_price",
            "Price",
            "Current Price",
        )
    )

    technical = _agent_score(
        row,
        "Technical Agent",
        "technical_score",
        "Technical Score",
        "Final Conviction",
        "conviction",
    )
    finance = _agent_score(
        row,
        "Finance Agent",
        "finance_agent_score",
        "Finance Agent Score",
        "Quality Score",
        "quality_score",
    )
    analyst = _num(
        _first(
            row,
            "analyst_support_score",
            "Analyst Support Score",
            "Final Conviction",
        )
    )

    valuation = _num(
        _first(
            row,
            "valuation_score",
            "Valuation Score",
        )
    )
    if valuation is None:
        upside = _num(
            _first(
                row,
                "analyst_upside_pct",
                "Target Upside %",
            )
        )
        if upside is not None:
            valuation = max(20.0, min(90.0, 55.0 + upside * 0.5))

    institutional = _institutional_score(row)
    policy = _policy_score(row)
    policymaker = _policymaker_score(row)
    completeness = _research_completeness(row)
    fair_value = _safe_fair_value(row, price)

    expected_return = (
        round((fair_value - price) / price * 100.0, 1)
        if price and fair_value
        else None
    )

    action = _atlas_action(
        row,
        technical,
        finance,
        completeness,
        expected_return,
    )

    excluded_reason = None
    if quote_type not in {"EQUITY", "STOCK"}:
        excluded_reason = "non_equity"
    elif sector.lower() in EXCLUDED_SECTORS:
        excluded_reason = "excluded_sector"

    raw = row.get("Raw")
    raw = raw if isinstance(raw, Mapping) else row

    return {
        "ticker": ticker,
        "company": company,
        "sector": sector,
        "industry": industry,
        "quote_type": quote_type,
        "eligible": excluded_reason is None,
        "excluded_reason": excluded_reason,
        "current_price": price,
        "atlas_fair_value": fair_value,
        "expected_return_pct": expected_return,
        "quality_score": finance,
        "financial_health_score": finance,
        "technical_score": technical,
        "valuation_score": valuation,
        "analyst_score": analyst,
        "institutional_score": institutional,
        "government_policy_score": policy,
        "policymaker_disclosure_score": policymaker,
        "research_completeness_pct": completeness,
        "investment_thesis": _text(
            _first(
                row,
                "investment_thesis",
                "Investment Thesis",
                "committee_conclusion",
            )
        ),
        "setup_tags": (
            raw.get("setup_tags")
            if isinstance(raw.get("setup_tags"), list)
            else []
        ),
        "risk_tags": (
            raw.get("risk_tags")
            if isinstance(raw.get("risk_tags"), list)
            else []
        ),
        "guidance": _text(
            _first(
                row,
                "guidance",
                "ai_guidance",
                "Guidance",
            )
        ),
        "earnings_summary": _text(
            _first(
                row,
                "earnings_summary",
                "transcript_summary",
                "Latest Earnings Summary",
            )
        ),
        "transcript_url": _text(
            _first(
                row,
                "transcript_url",
                "earnings_transcript_url",
            )
        ),
        "next_earnings_date": _text(
            _first(
                row,
                "next_earnings_date",
                "earnings_date",
                "Next Earnings Date",
            )
        ),
        "latest_news_headline": _text(
            _first(
                row,
                "latest_news_headline",
                "top_news_headline",
                "Latest News Headline",
            )
        ),
        "political_support": _text(
            _first(
                row,
                "political_support",
                "political_support_summary",
                "Political Support",
            )
        ),
        "institutional_activity": _text(
            _first(
                row,
                "institutional_activity",
                "institutional_summary",
                "Institutional Activity",
            )
        ),
        "action_code": action,
        "raw": dict(raw),
    }


def adapt_scanner_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        adapt_scanner_row(row)
        for row in rows
        if isinstance(row, Mapping)
    ]


__all__ = [
    "adapt_scanner_row",
    "adapt_scanner_rows",
    "EXCLUDED_SECTORS",
]
