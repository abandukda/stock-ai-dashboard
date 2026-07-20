"""
Atlas V102 Canonical Scanner Adapter

Converts the current flat scanner output into one stable downstream schema.
No recommendation is created from analyst recommendation labels.
"""
from __future__ import annotations
from typing import Any, Iterable, Mapping
import math

EXCLUDED_SECTORS = {
    "financial services", "financials", "entertainment",
    "gambling", "alcohol", "tobacco",
}

def _num(value: Any, default=None):
    try:
        if value is None or value == "":
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default

def _text(value: Any, default=""):
    if value is None:
        return default
    value = str(value).strip()
    return value if value and value.lower() not in {"none","nan","null","n/a"} else default

def _first(row: Mapping[str, Any], *keys, default=None):
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return default

def _agent(row: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    committee = row.get("ai_committee")
    if not isinstance(committee, Mapping):
        return {}
    value = committee.get(name)
    return value if isinstance(value, Mapping) else {}

def _agent_score(row: Mapping[str, Any], name: str, *fallback_keys):
    score = _num(_agent(row, name).get("score"))
    if score is not None:
        return max(0.0, min(100.0, score))
    score = _num(_first(row, *fallback_keys))
    return None if score is None else max(0.0, min(100.0, score))

def _research_completeness(row: Mapping[str, Any]) -> float:
    checks = [
        _num(_first(row, "current_price", "price")),
        _agent_score(row, "Technical Agent", "technical_score"),
        _agent_score(row, "Finance Agent", "finance_agent_score"),
        _num(_first(row, "analyst_support_score")),
        _text(_first(row, "investment_thesis")),
        _text(_first(row, "latest_news_headline", "top_news_headline")),
        _text(_first(row, "guidance", "ai_guidance")),
        _text(_first(row, "earnings_summary", "transcript_summary")),
        _text(_first(row, "political_support", "political_support_summary")),
        _text(_first(row, "institutional_activity", "institutional_summary")),
    ]
    return round(sum(bool(value) for value in checks) / len(checks) * 100.0, 1)

def _policy_score(row: Mapping[str, Any]):
    direct = _num(_first(row, "government_policy_score", "political_score", "policy_support_score"))
    if direct is not None:
        return max(0.0, min(100.0, direct))
    text = " ".join([
        _text(_first(row, "political_support")),
        _text(_first(row, "political_support_summary")),
        _text(_first(row, "government_policy_summary")),
    ]).lower()
    if not text.strip():
        return None
    if any(word in text for word in ("tailwind","support","benefit","contract","incentive","buying")):
        return 75.0
    if any(word in text for word in ("headwind","restriction","investigation","risk","selling")):
        return 30.0
    return 55.0

def _institutional_score(row: Mapping[str, Any]):
    direct = _num(_first(row, "institutional_score", "smart_money_score"))
    if direct is not None:
        return max(0.0, min(100.0, direct))
    agent = _agent_score(row, "Institutional Agent")
    if agent is not None:
        return agent
    text = " ".join([
        _text(_first(row, "institutional_activity")),
        _text(_first(row, "institutional_summary")),
    ]).lower()
    if not text.strip():
        return None
    if any(word in text for word in ("buying","accumulation","increased","added")):
        return 80.0
    if any(word in text for word in ("selling","distribution","reduced")):
        return 30.0
    return 55.0

def _policymaker_score(row: Mapping[str, Any]):
    direct = _num(_first(
        row, "policymaker_disclosure_score",
        "congressional_trading_score", "political_buying_score",
    ))
    if direct is not None:
        return max(0.0, min(100.0, direct))
    text = " ".join([
        _text(_first(row, "political_buying_summary")),
        _text(_first(row, "congressional_trading_summary")),
    ]).lower()
    if not text.strip():
        return None
    if "buy" in text or "purchase" in text:
        return 70.0
    if "sell" in text or "sale" in text:
        return 35.0
    return 50.0

def _safe_fair_value(row: Mapping[str, Any], price):
    analyst = _num(_first(row, "analyst_target_mean", "finnhub_target_mean"))
    ai_target = _num(_first(row, "ai_base_target", "target"))
    candidates = []
    if analyst and price and 0.5 * price <= analyst <= 2.0 * price:
        candidates.append(analyst)
    if ai_target and price and 0.5 * price <= ai_target <= 2.0 * price:
        candidates.append(ai_target)
    if not candidates:
        return None
    return round(sum(candidates) / len(candidates), 2)

def _atlas_action(row: Mapping[str, Any], technical, finance, completeness, expected_return):
    # Never copy recommendation_key; that is analyst consensus.
    score = _num(_first(row, "v89_action_score", "atlas_decision_score"))
    if score is not None:
        if score >= 80: return "BUY_NOW"
        if score >= 68: return "ACCUMULATE"
        if score < 40: return "AVOID"
        return "MONITOR"
    passed = sum([
        technical is not None and technical >= 60,
        finance is not None and finance >= 60,
        completeness >= 60,
        expected_return is not None and expected_return >= 10,
    ])
    if passed == 4 and expected_return <= 60:
        return "BUY_NOW"
    if passed >= 3:
        return "ACCUMULATE"
    if finance is not None and finance < 40:
        return "AVOID"
    return "MONITOR"

def adapt_scanner_row(row: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(row)
    ticker = _text(_first(row, "ticker", "symbol", "Ticker"), "UNKNOWN").upper()
    company = _text(_first(row, "company", "company_name", "name", "Company"), ticker)
    sector = _text(_first(row, "sector", "Sector"), "Unknown")
    industry = _text(_first(row, "industry", "Industry"), sector)
    quote_type = _text(_first(row, "quote_type", "quoteType"), "EQUITY").upper()

    price = _num(_first(row, "current_price", "price", "last_price"))
    technical = _agent_score(row, "Technical Agent", "technical_score")
    finance = _agent_score(row, "Finance Agent", "finance_agent_score")
    analyst = _num(_first(row, "analyst_support_score"))
    valuation = _num(_first(row, "valuation_score"))
    if valuation is None:
        peg = _num(_first(row, "peg_ratio"))
        forward_pe = _num(_first(row, "forward_pe"))
        if peg is not None:
            valuation = max(20.0, min(90.0, 85.0 - max(0.0, peg - 1.0) * 25.0))
        elif forward_pe is not None:
            valuation = max(20.0, min(85.0, 80.0 - max(0.0, forward_pe - 20.0)))
    institutional = _institutional_score(row)
    policy = _policy_score(row)
    policymaker = _policymaker_score(row)
    completeness = _research_completeness(row)
    fair_value = _safe_fair_value(row, price)
    expected_return = (
        round((fair_value - price) / price * 100.0, 1)
        if price and fair_value else None
    )
    action = _atlas_action(row, technical, finance, completeness, expected_return)

    excluded_reason = None
    if quote_type not in {"EQUITY", "STOCK"}:
        excluded_reason = "non_equity"
    elif sector.lower() in EXCLUDED_SECTORS:
        excluded_reason = "excluded_sector"

    canonical = {
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
        "investment_thesis": _text(_first(row, "investment_thesis", "committee_conclusion")),
        "setup_tags": row.get("setup_tags") if isinstance(row.get("setup_tags"), list) else [],
        "risk_tags": row.get("risk_tags") if isinstance(row.get("risk_tags"), list) else [],
        "guidance": _text(_first(row, "guidance", "ai_guidance")),
        "earnings_summary": _text(_first(row, "earnings_summary", "transcript_summary")),
        "transcript_url": _text(_first(row, "transcript_url", "earnings_transcript_url")),
        "next_earnings_date": _text(_first(row, "next_earnings_date", "earnings_date")),
        "latest_news_headline": _text(_first(row, "latest_news_headline", "top_news_headline")),
        "political_support": _text(_first(row, "political_support", "political_support_summary")),
        "institutional_activity": _text(_first(row, "institutional_activity", "institutional_summary")),
        "action_code": action,
        "raw": row,
    }
    return canonical

def adapt_scanner_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [adapt_scanner_row(row) for row in rows if isinstance(row, Mapping)]

__all__ = ["adapt_scanner_row", "adapt_scanner_rows", "EXCLUDED_SECTORS"]
