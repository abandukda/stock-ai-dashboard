"""
Atlas V88 — Narrative Orchestration Engine

New file: engines/atlas_narrative_engine.py
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence
import math
import re

_MISSING = {"", "n/a", "na", "none", "null", "nan", "unavailable", "under review", "not available", "not reported", "-", "—"}

def _text(value: Any, default: str = "") -> str:
    if value is None: return default
    text = str(value).strip()
    return default if text.lower() in _MISSING else text

def _num(value: Any, default: float | None = None) -> float | None:
    if value is None: return default
    if isinstance(value, bool): return float(value)
    if isinstance(value, (int, float)):
        value = float(value)
        return default if math.isnan(value) or math.isinf(value) else value
    text = str(value).replace(",", "").replace("$", "").replace("%", "").strip()
    if text.lower() in _MISSING: return default
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else default

def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key not in row: continue
        value = row.get(key)
        if value is None: continue
        if isinstance(value, str) and value.strip().lower() in _MISSING: continue
        return value
    return default

def _listify(value: Any) -> List[str]:
    if value is None: return []
    if isinstance(value, str):
        return [p.strip(" -\t") for p in re.split(r"[\n|•]+", value) if p.strip(" -\t")]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out = []
        for item in value:
            if isinstance(item, Mapping):
                item = _first(item, "headline", "title", "summary", "text", "reason")
            text = _text(item)
            if text: out.append(text)
        return out
    text = _text(value)
    return [text] if text else []

def _dedupe(items: Iterable[str], limit: int | None = None) -> List[str]:
    seen, out = set(), []
    for item in items:
        text = _text(item)
        if not text: continue
        key = re.sub(r"\s+", " ", text.lower()).strip()
        if key in seen: continue
        seen.add(key); out.append(text)
        if limit is not None and len(out) >= limit: break
    return out

def _pct(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f}%"

def _money(value: float | None) -> str:
    if value is None: return "Unavailable"
    a = abs(value)
    if a >= 1_000_000_000: return f"${value/1_000_000_000:.1f}B"
    if a >= 1_000_000: return f"${value/1_000_000:.1f}M"
    return f"${value:,.2f}"

def _upside(price: float | None, target: float | None) -> float | None:
    if price is None or target is None or price <= 0: return None
    return ((target - price) / price) * 100.0

def _safe_import_reports(row: Mapping[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    equity, evidence = {}, {}
    try:
        from engines.equity_research_engine import build_equity_research_report
        built = build_equity_research_report(row)
        if isinstance(built, Mapping): equity = dict(built)
    except Exception:
        pass
    try:
        from engines.evidence_engine import build_evidence
        built = build_evidence(row)
        if isinstance(built, Mapping): evidence = dict(built)
    except Exception:
        pass
    return equity, evidence

def _normalize_decision(value: Any) -> str:
    text = _text(value, "Wait for Confirmation").replace("_", " ").strip().title()
    aliases = {
        "Strong Buy": "High Conviction Buy", "High Conviction Buy": "High Conviction Buy",
        "Buy": "Buy Now", "Buy Now": "Buy Now", "Accumulate": "Buy on Weakness",
        "Buy On Weakness": "Buy on Weakness", "Wait": "Wait for Confirmation",
        "Wait For Confirmation": "Wait for Confirmation", "Hold": "Wait for Confirmation",
        "Avoid": "Avoid", "Sell": "Avoid",
    }
    return aliases.get(text, text)

def _decision_reason(decision: str, evidence: Sequence[str], risks: Sequence[str]) -> str:
    strongest = evidence[0] if evidence else "the evidence set remains incomplete"
    risk = risks[0] if risks else "execution risk remains"
    if decision in {"High Conviction Buy", "Buy Now"}:
        return f"{strongest} The recommendation remains risk-controlled because {risk.lower()}"
    if decision == "Buy on Weakness":
        return f"The long-term case has support, led by {strongest.lower()} However, Atlas prefers a better entry because {risk.lower()}"
    if decision == "Avoid":
        return f"Current downside evidence outweighs the available upside. The key concern is that {risk.lower()}"
    return f"Atlas sees some support, but not enough independent confirmation for an immediate purchase. The key issue is that {risk.lower()}"

def _fallback_evidence(row: Mapping[str, Any]) -> List[str]:
    out = []
    price = _num(_first(row, "Current Price", "current_price", "Price", "Close"))
    fair = _num(_first(row, "Atlas Fair Value", "atlas_fair_value", "fair_value"))
    target = _num(_first(row, "Wall Street Consensus", "analyst_target", "targetMeanPrice"))
    rev = _num(_first(row, "Revenue Growth", "revenue_growth", "revenueGrowth"))
    eps = _num(_first(row, "EPS Growth", "eps_growth", "earningsGrowth"))
    margin = _num(_first(row, "Operating Margin", "operating_margin", "operatingMargins"))
    fcf = _num(_first(row, "Free Cash Flow", "free_cash_flow", "freeCashflow"))
    rsi = _num(_first(row, "RSI", "rsi"))
    fv_u, ws_u = _upside(price, fair), _upside(price, target)
    if fv_u is not None and fv_u > 0: out.append(f"Atlas Fair Value implies approximately {_pct(fv_u)} upside.")
    if ws_u is not None and ws_u > 0: out.append(f"Wall Street consensus implies approximately {_pct(ws_u)} upside.")
    if rev is not None: out.append(f"Revenue {'growth' if rev > 0 else 'change'} is {_pct(rev)}.")
    if eps is not None and eps > 0: out.append(f"EPS growth of {_pct(eps)} supports the operating thesis.")
    if margin is not None and margin >= 15: out.append(f"Operating margin of {_pct(margin)} demonstrates attractive profitability.")
    if fcf is not None and fcf > 0: out.append(f"Positive free cash flow of {_money(fcf)} supports reinvestment and capital returns.")
    if rsi is not None and 45 <= rsi <= 65: out.append(f"RSI of {rsi:.0f} shows constructive momentum without looking overheated.")
    news = _listify(_first(row, "news_items", "latest_news", "news", "latest_news_headline"))
    if news: out.append(f"Latest verified catalyst: {news[0]}")
    policy = _listify(_first(row, "political_support", "political_context", "policy_context"))
    if policy: out.append(f"Policy context: {policy[0]}")
    return _dedupe(out, 8)

def _fallback_risks(row: Mapping[str, Any]) -> List[str]:
    risks = []
    cr = _num(_first(row, "Current Ratio", "current_ratio", "currentRatio"))
    debt = _num(_first(row, "Debt to Equity", "debt_to_equity", "debtToEquity"))
    pe = _num(_first(row, "Forward P/E", "forward_pe", "forwardPE"))
    rsi = _num(_first(row, "RSI", "rsi"))
    rv = _num(_first(row, "Relative Volume", "relative_volume", "relativeVolume"))
    if cr is not None and 0 < cr < 1: risks.append(f"Current ratio of {cr:.2f} indicates a tighter short-term liquidity cushion.")
    if debt is not None and debt > 200: risks.append(f"Debt-to-equity of {debt:.0f}% increases balance-sheet sensitivity.")
    if pe is not None and pe > 45: risks.append(f"Forward valuation of {pe:.1f}x leaves limited room for execution mistakes.")
    if rsi is not None and rsi >= 75: risks.append(f"RSI of {rsi:.0f} suggests the shares may be technically overheated.")
    if rv is not None and rv < 0.7: risks.append(f"Relative volume of {rv:.2f}x shows limited confirmation behind the move.")
    if not _listify(_first(row, "earnings_summary", "transcript_summary", "guidance_summary")):
        risks.append("Recent earnings and management-guidance context is incomplete.")
    if not _listify(_first(row, "news_items", "latest_news", "news")):
        risks.append("No material recent company-specific catalyst was verified.")
    if not risks: risks.append("Execution may fall short of the growth assumptions embedded in the valuation.")
    return _dedupe(risks, 5)

def _movement(row: Mapping[str, Any], decision: str, evidence: Sequence[str], risks: Sequence[str]) -> Dict[str, str]:
    current = _num(_first(row, "Current Rank", "current_rank", "Rank", "rank"))
    prior = _num(_first(row, "Previous Rank", "prior_rank", "Prior Rank"))
    new_today = bool(_first(row, "New Today", "new_today", default=False))
    if current is not None and prior is not None:
        delta = int(prior-current)
        if delta > 0:
            label = f"Rank improved: #{int(prior)} → #{int(current)}"
            explanation = f"The stock moved up {delta} ranks because newer evidence improved its relative setup. {evidence[0] if evidence else ''}".strip()
        elif delta < 0:
            label = f"Rank declined: #{int(prior)} → #{int(current)}"
            explanation = f"The stock moved down {abs(delta)} ranks because competing ideas improved or this setup weakened. {risks[0] if risks else ''}".strip()
        else:
            label = f"Rank unchanged at #{int(current)}"
            explanation = "No material score or catalyst change was verified."
    elif new_today:
        label = "New discovery today"
        explanation = "Atlas surfaced this company because it was absent from prior ranking history and passed today's discovery threshold."
    else:
        label = "No verified ranking change"
        explanation = "Atlas has not accumulated enough prior-history evidence to explain a precise rank movement yet."
    return {"label": label, "explanation": explanation, "decision_context": f"Current action: {decision}. {_decision_reason(decision, evidence, risks)}"}

def build_atlas_narrative(row: Mapping[str, Any]) -> Dict[str, Any]:
    equity, v87 = _safe_import_reports(row)
    ticker = _text(_first(row, "Ticker", "ticker", "symbol"), "UNKNOWN").upper()
    company = _text(_first(row, "Company", "company", "Name", "longName"), ticker)
    decision = _normalize_decision(_first(equity, "decision", default=_first(v87, "decision", default=_first(row, "Decision", "decision", "Verdict"))))
    evidence = _dedupe(_listify(v87.get("why_atlas_likes_it")) + _listify(equity.get("bull_case")) + _fallback_evidence(row), 8)
    risks = _dedupe(_listify(v87.get("primary_risks")) + _listify(equity.get("primary_risks")) + _listify(equity.get("bear_case")) + _fallback_risks(row), 5)
    overall = _num(equity.get("overall_score"), _num(v87.get("score"), _num(_first(row, "Confidence", "confidence"), 50))) or 50
    confidence = _num(equity.get("confidence"), _num(_first(row, "Confidence", "confidence"), overall)) or overall
    expected_return = _num(equity.get("expected_return_pct"), _num(_first(row, "Expected Return", "expected_return", "Atlas Expected Return")))
    completeness = equity.get("research_completeness")
    if not isinstance(completeness, Mapping):
        verified = sum([bool(evidence), bool(risks), bool(_first(row, "Revenue Growth", "revenue_growth")), bool(_first(row, "Operating Margin", "operating_margin")), bool(_first(row, "Atlas Fair Value", "atlas_fair_value")), bool(_first(row, "RSI", "rsi")), bool(_first(row, "news_items", "latest_news", "news")), bool(_first(row, "earnings_summary", "guidance_summary"))])
        completeness = {"verified_pillars": verified, "total_pillars": 8, "percent": round(verified/8*100)}
    executive = _text(equity.get("executive_thesis"), f"Atlas rates {company} ({ticker}) as {decision}. The case is supported by {'; '.join(evidence[:3]) if evidence else 'a developing evidence set'}. The most important risk is {risks[0].lower() if risks else 'execution remains uncertain.'}")
    why_now_parts = ([f"Modeled upside is approximately {_pct(expected_return)}."] if expected_return is not None and expected_return > 0 else []) + evidence[:3]
    why_now = " ".join(_dedupe(why_now_parts, 4)) or "Atlas has not verified a sufficiently strong near-term catalyst, so patience remains appropriate."
    movement = _movement(row, decision, evidence, risks)
    scorecard = equity.get("evidence_scorecard") if isinstance(equity.get("evidence_scorecard"), Mapping) else {}
    return {
        "ticker": ticker, "company": company, "version": "V88", "decision": decision,
        "confidence": round(confidence), "overall_score": round(overall, 1), "expected_return_pct": expected_return,
        "executive_summary": executive, "why_now": why_now, "why_atlas_likes_it": evidence,
        "supporting_evidence": evidence, "primary_risks": risks,
        "short_card_summary": " ".join(evidence[:3]) if evidence else "Atlas has not verified enough independent evidence to support an immediate purchase.",
        "movement": movement, "movement_explanation": movement["explanation"],
        "evidence_scorecard": dict(scorecard), "research_completeness": dict(completeness),
        "verdict": {"rating": decision, "confidence": round(confidence), "expected_return_pct": expected_return,
                    "reason": _decision_reason(decision, evidence, risks),
                    "risk": _text(equity.get("risk_level"), "Moderate"),
                    "time_horizon": _text(equity.get("time_horizon"), "12–18 months")},
        "business_summary": _text(equity.get("business_summary")),
        "quality_summary": _text(equity.get("quality_summary")),
        "valuation_summary": _text(equity.get("valuation_summary")),
        "technical_summary": _text(equity.get("technical_summary")),
        "wall_street_summary": _text(equity.get("wall_street_summary")),
        "institutional_summary": _text(equity.get("institutional_summary")),
        "management_summary": _text(equity.get("management_summary")),
        "macro_policy_summary": _text(equity.get("macro_policy_summary")),
        "news_summary": _text(equity.get("news_summary")),
        "bull_case": _listify(equity.get("bull_case")) or evidence,
        "bear_case": _listify(equity.get("bear_case")) or risks,
        "catalyst_timeline": equity.get("catalyst_timeline", {}),
        "thesis_invalidation": _listify(equity.get("thesis_invalidation")),
        "bottom_line": _text(equity.get("bottom_line"), f"{ticker} is a {decision} with an Atlas score of {overall:.0f}/100 and confidence of {confidence:.0f}%.")
    }

build_narrative = build_atlas_narrative
generate_atlas_narrative = build_atlas_narrative
__all__ = ["build_atlas_narrative", "build_narrative", "generate_atlas_narrative"]
