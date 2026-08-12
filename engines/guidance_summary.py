"""Deterministic, reporting-only Atlas guidance synthesis.

This layer selects and explains evidence already present in a normalized Atlas
row.  It never calculates or changes scores, verdicts, recommendations,
valuation, expected returns, trade levels, rankings, or provider data.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping, Sequence

from engines.research_enrichment_v105 import accepted_company_news


_MISSING = {"", "n/a", "na", "none", "null", "nan", "unknown", "unavailable", "under review", "—", "-"}
_GENERIC_NEWS = ("no recent", "no high-confidence", "not returned", "unavailable")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sources(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    sources = [row, _mapping(row.get("raw")), _mapping(row.get("Raw"))]
    for key in ("financials", "earnings", "analysts", "news", "ownership", "technical"):
        section = _mapping(row.get(key))
        data = _mapping(section.get("data"))
        sources.extend(value for value in (section, data) if value)
    return [source for source in sources if source]


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for source in _sources(row):
        for key in keys:
            if key not in source:
                continue
            value = source.get(key)
            if value is None:
                continue
            if isinstance(value, str) and value.strip().lower() in _MISSING:
                continue
            return value
    return None


def _num(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text.lower() in _MISSING else text


def _ratio_pct(value: Any) -> float | None:
    number = _num(value)
    if number is None:
        return None
    return number * 100.0 if abs(number) <= 3 else number


def _money(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.2f}"


def _pct(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f}%"


def _verified_date(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return parsed.date().isoformat()


def _as_of(row: Mapping[str, Any], fallback: str = "Current saved Atlas row") -> str:
    return _text(_first(row, "generated_at", "as_of", "price_as_of", "data_as_of"), fallback)


def _canonical_fair_value(row: Mapping[str, Any]) -> float | None:
    # Deliberately exclude generic target/ai_base_target and the V104
    # validated_fair_value adapter, which may represent analyst consensus.
    return _num(_first(row, "atlas_fair_value", "Atlas Fair Value"))


def _fact(fact: str, why: str, source: str, as_of: str, domain: str) -> dict[str, Any]:
    return {"fact": fact, "why_it_matters": why, "source": source, "as_of": as_of, "domain": domain}


def _risk(risk: str, consequence: str, evidence: str, domain: str) -> dict[str, Any]:
    return {"risk": risk, "consequence": consequence, "monitored_evidence": evidence, "domain": domain}


def _normalized_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
    price = _num(_first(row, "current_price", "price", "Price", "Current Price"))
    fair_value = _canonical_fair_value(row)
    analyst_mean = _num(_first(row, "analyst_target_mean", "Analyst Target", "Wall Street Consensus"))
    accepted_news = accepted_company_news(row)
    lead_news = accepted_news[0] if accepted_news else {}
    return {
        "ticker": _text(_first(row, "ticker", "symbol", "Ticker"), "UNKNOWN").upper(),
        "company": _text(_first(row, "company", "company_name", "Company")),
        "verdict": _text(_first(row, "committee_verdict", "action_code", "recommendation"), "MONITOR"),
        "confidence": _num(_first(row, "confidence_pct", "Confidence")),
        "position_size": _text(_first(row, "position_size_range", "Position Size")),
        "entry_status": _text(_first(row, "entry_status", "Entry Status", "buy_zone_status")),
        "entry_zone": _first(row, "entry_zone", "Entry Zone"),
        "trade_plan": _mapping(row.get("trade_plan")),
        "price": price,
        "fair_value": fair_value,
        "expected_return": _num(_first(row, "expected_return_pct", "Expected Return %")),
        "analyst_mean": analyst_mean,
        "analyst_high": _num(_first(row, "analyst_target_high", "Analyst Target High")),
        "analyst_low": _num(_first(row, "analyst_target_low", "Analyst Target Low")),
        "analyst_count": _num(_first(row, "analyst_count", "Analyst Count")),
        "revenue_growth": _ratio_pct(_first(row, "revenue_growth", "Revenue Growth", "revenueGrowth")),
        "earnings_growth": _ratio_pct(_first(row, "earnings_growth", "eps_growth_pct", "Earnings Growth", "EPS Growth")),
        "gross_margin": _ratio_pct(_first(row, "gross_margin", "gross_profit_margin", "Gross Margin")),
        "operating_margin": _ratio_pct(_first(row, "operating_profit_margin", "operating_margin", "Operating Margin")),
        "fcf": _num(_first(row, "free_cash_flow", "Free Cash Flow", "freeCashflow")),
        "ocf": _num(_first(row, "operating_cash_flow", "Operating Cash Flow", "operatingCashflow")),
        "reported_eps": _num(_first(row, "reported_eps", "eps_actual", "Reported EPS")),
        "estimated_eps": _num(_first(row, "estimated_eps", "eps_estimate", "Estimated EPS")),
        "eps_surprise": _num(_first(row, "eps_surprise_pct", "EPS Surprise %")),
        "revenue_surprise": _num(_first(row, "revenue_surprise_pct", "Revenue Surprise %")),
        "latest_earnings_date": _verified_date(_first(row, "latest_earnings_date", "Latest Earnings Date")),
        "next_earnings_date": _verified_date(_first(row, "next_earnings_date", "Next Earnings Date", "earnings_date")),
        "institutional_ownership": _num(_first(row, "institutional_ownership_pct", "Institutional Ownership %")),
        "insider_ownership": _num(_first(row, "insider_ownership_pct", "Insider Ownership %")),
        "news_headline": _text(lead_news.get("headline")),
        "news_date": _verified_date(lead_news.get("date")),
        "news_classification": _text(lead_news.get("classification")),
        "rsi": _num(_first(row, "rsi", "RSI")),
        "sma50": _num(_first(row, "sma50", "SMA50")),
        "sma200": _num(_first(row, "sma200", "SMA200")),
        "primary_risk": _text(_first(row, "primary_risk", "Primary Risk", "what_could_go_wrong")),
        "upgrade_triggers": list(row.get("upgrade_triggers") or []),
        "downgrade_triggers": list(row.get("downgrade_triggers") or []),
        "as_of": _as_of(row),
    }


def _supporting_facts(e: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    as_of = str(e["as_of"])
    revenue, earnings = e["revenue_growth"], e["earnings_growth"]
    if revenue is not None or earnings is not None:
        pieces = []
        if revenue is not None:
            pieces.append(f"revenue growth is {_pct(revenue)}")
        if earnings is not None:
            pieces.append(f"earnings growth is {_pct(earnings)}")
        delivery = ""
        if e["eps_surprise"] is not None:
            direction = "beat" if e["eps_surprise"] >= 0 else "missed"
            delivery = f" Latest EPS {direction} estimates by {abs(e['eps_surprise']):.1f}%."
        candidates.append(_fact(
            f"Reported growth: {' and '.join(pieces)}.{delivery}",
            "This shows whether operating expansion is reaching both sales and earnings.",
            "Yahoo/FMP normalized fundamentals", as_of, "earnings_growth",
        ))
    if e["eps_surprise"] is not None and revenue is None and earnings is None:
        direction = "beat" if e["eps_surprise"] >= 0 else "missed"
        candidates.append(_fact(
            f"Latest reported EPS {direction} estimates by {abs(e['eps_surprise']):.1f}%"
            + (f" on {e['latest_earnings_date']}." if e["latest_earnings_date"] else "."),
            "The latest earnings result tests whether the current growth thesis is translating into delivery.",
            "FMP/Yahoo earnings history", e["latest_earnings_date"] or as_of, "earnings",
        ))
    margins = []
    if e["gross_margin"] is not None:
        margins.append(f"gross margin {_pct(e['gross_margin'])}")
    if e["operating_margin"] is not None:
        margins.append(f"operating margin {_pct(e['operating_margin'])}")
    cash = e["fcf"] if e["fcf"] is not None else e["ocf"]
    if margins or cash is not None:
        fact = "Profitability evidence: " + ", ".join(margins)
        if cash is not None:
            fact += (", " if margins else "") + f"and {'free' if e['fcf'] is not None else 'operating'} cash flow of {_money(cash)}"
        candidates.append(_fact(
            fact + ".", "Margins and cash generation show the quality and financing durability of growth.",
            "FMP Stable/Yahoo fundamentals", as_of, "profitability_cash",
        ))
    if e["fair_value"] is not None:
        relationship = "above" if e["price"] is not None and e["fair_value"] >= e["price"] else "below"
        consensus = (
            f" Wall Street's average target is {_money(e['analyst_mean'])}; it remains a separate analyst measure."
            if e["analyst_mean"] is not None else ""
        )
        candidates.append(_fact(
            f"Canonical Atlas Fair Value is {_money(e['fair_value'])}"
            + (f", {relationship} the current price of {_money(e['price'])}." if e["price"] is not None else ".")
            + consensus,
            "This is Atlas's canonical valuation output and is kept separate from Wall Street targets.",
            "Atlas canonical valuation", as_of, "valuation",
        ))
    if e["analyst_mean"] is not None and e["fair_value"] is None:
        coverage = f" from {int(e['analyst_count'])} analysts" if e["analyst_count"] is not None else ""
        candidates.append(_fact(
            f"Wall Street's average target is {_money(e['analyst_mean'])}{coverage}.",
            "Consensus provides an external reference point without replacing Atlas Fair Value.",
            "Yahoo/Finnhub analyst consensus", as_of, "analyst",
        ))
    headline = str(e["news_headline"] or "")
    if (
        headline
        and e.get("news_classification") in {
            "Catalyst", "Earnings", "Analyst Action",
            "Regulatory / Political", "M&A / Capital Allocation",
        }
        and not any(marker in headline.lower() for marker in _GENERIC_NEWS)
    ):
        candidates.append(_fact(
            f"Verified company-specific headline: {headline}",
            "A current company event can change estimates, sentiment, or the timing of the thesis.",
            "Filtered company news", e["news_date"] or as_of, "news",
        ))
    if e["institutional_ownership"] is not None:
        candidates.append(_fact(
            f"Reported institutional ownership is {_pct(e['institutional_ownership'])}.",
            "Ownership is supporting context for sponsorship, not a standalone reason to buy.",
            "Yahoo/FMP ownership", as_of, "ownership",
        ))
    if e["price"] is not None and (e["sma50"] is not None or e["sma200"] is not None):
        signals = []
        if e["sma50"] is not None:
            signals.append(("above" if e["price"] >= e["sma50"] else "below") + " its 50-day average")
        if e["sma200"] is not None:
            signals.append(("above" if e["price"] >= e["sma200"] else "below") + " its 200-day average")
        candidates.append(_fact(
            f"Price is {' and '.join(signals)}.", "Trend evidence helps assess entry timing; it does not replace fundamentals.",
            "Yahoo price history", as_of, "technical",
        ))
    # Priority is encoded by construction. Keep domain diversity by selecting
    # at most one fact from a domain.
    selected, seen = [], set()
    for item in candidates:
        if item["domain"] in seen:
            continue
        selected.append(item)
        seen.add(item["domain"])
        if len(selected) == 3:
            break
    return selected


def _risks(e: Mapping[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if e["revenue_growth"] is not None and e["revenue_growth"] < 0:
        risks.append(_risk(
            f"Revenue is contracting at {_pct(e['revenue_growth'])}.",
            "Continued contraction would weaken the earnings and valuation case.",
            "Subsequent revenue growth and estimates", "growth",
        ))
    if e["earnings_growth"] is not None and e["earnings_growth"] < 0:
        risks.append(_risk(
            f"Earnings growth is negative at {_pct(e['earnings_growth'])}.",
            "Falling earnings reduce support for valuation and capital returns.",
            "Reported EPS and forward estimates", "earnings",
        ))
    if e["eps_surprise"] is not None and e["eps_surprise"] < 0:
        risks.append(_risk(
            f"Latest EPS missed estimates by {abs(e['eps_surprise']):.1f}%.",
            "A miss can signal execution or estimate risk if it persists.",
            "Next earnings result and estimate revisions", "earnings_surprise",
        ))
    if e["operating_margin"] is not None and e["operating_margin"] < 10:
        risks.append(_risk(
            f"Operating margin is {_pct(e['operating_margin'])}.",
            "Limited operating profitability reduces resilience if growth slows.",
            "Operating-margin progression", "margin",
        ))
    if e["fcf"] is not None and e["fcf"] < 0:
        risks.append(_risk(
            f"Free cash flow is negative at {_money(e['fcf'])}.",
            "Persistent cash burn can constrain reinvestment and increase financing risk.",
            "Free-cash-flow conversion", "cash_flow",
        ))
    if e["fair_value"] is not None and e["price"] is not None and e["fair_value"] < e["price"]:
        risks.append(_risk(
            f"Canonical Atlas Fair Value of {_money(e['fair_value'])} is below the current price.",
            "The current valuation offers no modeled margin of safety.",
            "Refreshed canonical valuation inputs", "valuation",
        ))
    if e["analyst_mean"] is not None and e["price"] is not None and e["analyst_mean"] < e["price"]:
        risks.append(_risk(
            f"Wall Street's average target of {_money(e['analyst_mean'])} is below the current price.",
            "Consensus currently provides limited external valuation support.",
            "Analyst revisions and target changes", "analyst",
        ))
    if (
        e["fair_value"] is not None
        and e["analyst_mean"] is not None
        and e["fair_value"] > e["analyst_mean"] * 1.2
    ):
        risks.append(_risk(
            f"Wall Street's average target of {_money(e['analyst_mean'])} is materially below Atlas Fair Value of {_money(e['fair_value'])}.",
            "The thesis relies more heavily on Atlas's canonical fundamental valuation than on consensus repricing.",
            "Earnings delivery and analyst estimate revisions", "valuation_divergence",
        ))
    if e["price"] is not None and e["sma50"] is not None and e["price"] < e["sma50"]:
        risks.append(_risk(
            "Price is below its 50-day average.", "Weak near-term trend can delay an otherwise sound thesis.",
            "Price recovery relative to the 50-day average", "technical",
        ))
    primary = str(e["primary_risk"] or "").strip()
    if primary and "score" not in primary.lower() and all(primary.lower() not in item["risk"].lower() for item in risks):
        risks.append(_risk(primary.rstrip("." ) + ".", "This is the specific risk identified in the current Atlas evidence.", "Next verified company update", "reported_risk"))
    return risks[:3]


def _unavailable(e: Mapping[str, Any]) -> list[str]:
    gaps = []
    if e["revenue_growth"] is None and e["earnings_growth"] is None:
        gaps.append("Revenue and earnings growth")
    if e["gross_margin"] is None and e["operating_margin"] is None:
        gaps.append("Gross and operating margins")
    if e["fcf"] is None and e["ocf"] is None:
        gaps.append("Free and operating cash flow")
    if e["eps_surprise"] is None and e["revenue_surprise"] is None:
        gaps.append("Latest earnings-surprise evidence")
    if e["fair_value"] is None:
        gaps.append("Canonical Atlas Fair Value")
    if e["analyst_mean"] is None:
        gaps.append("Wall Street consensus target")
    if e["next_earnings_date"] is None and not e["news_headline"]:
        gaps.append("A verified next catalyst")
    return gaps


def _action(e: Mapping[str, Any]) -> dict[str, Any]:
    verdict = str(e["verdict"])
    display = verdict.replace("_", " ").title()
    entry = e["entry_status"]
    trade_plan = e["trade_plan"]
    if not entry:
        entry = _text(trade_plan.get("entry_status"))
    entry_zone = e["entry_zone"] if e["entry_zone"] is not None else trade_plan.get("entry_zone")
    timing = entry or (f"Existing entry zone: {entry_zone}" if entry_zone not in (None, "", []) else "No verified entry/timing instruction is available.")
    return {
        "current_action": display,
        "entry_timing_context": timing,
        "position_size_guidance": e["position_size"] or _text(trade_plan.get("position_size_range")) or "Unavailable",
    }


def _catalyst(e: Mapping[str, Any]) -> dict[str, Any]:
    if e["next_earnings_date"]:
        return {
            "event": "Next scheduled earnings report",
            "date": e["next_earnings_date"],
            "verification_status": "Verified provider date",
            "what_atlas_will_watch": "Revenue and earnings growth, margins, cash conversion, surprises, and estimate revisions.",
        }
    headline = str(e["news_headline"] or "")
    if headline and not any(marker in headline.lower() for marker in _GENERIC_NEWS):
        return {
            "event": headline,
            "date": e["news_date"],
            "verification_status": "Verified company-specific news; event timing may be ongoing",
            "what_atlas_will_watch": "Whether the event changes fundamentals, estimates, or the investment thesis.",
        }
    return {
        "event": "No verified next catalyst is available",
        "date": None,
        "verification_status": "Unavailable",
        "what_atlas_will_watch": "The next verified earnings, company, regulatory, or analyst event.",
    }


def _conditions(e: Mapping[str, Any]) -> dict[str, list[str]]:
    strengthen, weaken, invalidate = [], [], []
    if e["revenue_growth"] is not None:
        strengthen.append(f"Revenue growth sustains above the current {_pct(e['revenue_growth'])} baseline.")
        weaken.append(f"Revenue growth falls materially below the current {_pct(e['revenue_growth'])} baseline.")
    if e["operating_margin"] is not None:
        strengthen.append(f"Operating margin improves from the current {_pct(e['operating_margin'])} level.")
        weaken.append(f"Operating margin compresses materially from {_pct(e['operating_margin'])}.")
    if e["fcf"] is not None:
        strengthen.append(f"Free-cash-flow conversion improves from the current {_money(e['fcf'])} level.")
        if e["fcf"] >= 0:
            invalidate.append("Free cash flow turns persistently negative while growth also weakens.")
    if e["analyst_mean"] is not None:
        strengthen.append("Analysts raise estimates or targets after new company evidence.")
        weaken.append("Analysts cut estimates or targets materially.")
    if e["fair_value"] is not None and e["price"] is not None:
        invalidate.append("Canonical Atlas Fair Value falls below market price alongside weakening fundamentals.")
    if not strengthen:
        strengthen.append("Verified fundamental or valuation evidence becomes available and supports the current verdict.")
    if not weaken:
        weaken.append("New verified evidence weakens the currently available technical or analyst support.")
    if not invalidate:
        invalidate.append("Verified fundamentals deteriorate enough that the existing thesis no longer has evidentiary support.")
    return {"strengthen": strengthen[:3], "weaken": weaken[:3], "invalidate": invalidate[:2]}


def guidance_summary_text(guidance: Mapping[str, Any]) -> str:
    view = _mapping(guidance.get("atlas_view"))
    action = _mapping(guidance.get("action_now"))
    facts = list(guidance.get("supporting_facts") or [])
    risks = list(guidance.get("key_risks") or [])
    catalyst = _mapping(guidance.get("next_catalyst"))
    parts = [str(view.get("interpretation") or "Atlas evidence is under review.")]
    parts.append(f"Action now: {action.get('current_action', 'Monitor')}. {action.get('entry_timing_context', '')}".strip())
    if facts:
        parts.append("Why: " + " ".join(str(item.get("fact")) for item in facts[:3]))
    if risks:
        parts.append("Main risks: " + " ".join(str(item.get("risk")) for item in risks[:2]))
    parts.append(f"Next: {catalyst.get('event', 'No verified catalyst is available')}"
                 + (f" on {catalyst.get('date')}." if catalyst.get("date") else "."))
    return " ".join(part for part in parts if part)


def build_guidance_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    e = _normalized_evidence(row)
    facts = _supporting_facts(e)
    risks = _risks(e)
    gaps = _unavailable(e)
    rich_domains = {item["domain"] for item in facts}
    evidence_limited = len(rich_domains.intersection({"earnings_growth", "earnings", "profitability_cash", "valuation"})) < 2
    verdict = str(e["verdict"])
    company = e["company"] or e["ticker"]
    if evidence_limited:
        interpretation = (
            f"Atlas's {verdict.replace('_', ' ').title()} view on {company} is evidence-limited and currently leans on "
            "the available analyst or technical context rather than a complete fundamental record."
        )
    else:
        interpretation = (
            f"Atlas's {verdict.replace('_', ' ').title()} view on {company} is supported by company-specific "
            "fundamental, earnings, cash-flow, or valuation evidence summarized below."
        )
    return {
        "atlas_view": {"verdict": verdict, "confidence": e["confidence"], "interpretation": interpretation},
        "action_now": _action(e),
        "supporting_facts": facts,
        "key_risks": risks,
        "next_catalyst": _catalyst(e),
        "thesis_change_conditions": _conditions(e),
        "unavailable_evidence": gaps,
        "evidence_limited": evidence_limited,
    }


__all__ = ["build_guidance_summary", "guidance_summary_text"]
