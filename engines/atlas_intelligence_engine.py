"""Grounded, stock-specific Atlas intelligence.

The narrative produced here is deterministic and derived only from the
normalized Atlas report. It deliberately includes the ticker/company name,
stock-specific metrics, catalyst evidence, valuation, technical context, and
risk evidence so different companies cannot silently collapse into one shared
template.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import math
import re


_MISSING = {
    "", "none", "null", "nan", "n/a", "na", "unknown",
    "unavailable", "under review", "not available",
}


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
        number = float(text)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text.lower() not in _MISSING else default


def _first_sentence(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    for separator in (". ", "\n", "; "):
        if separator in text:
            return text.split(separator, 1)[0].strip().rstrip(".") + "."
    return text.rstrip(".") + "."


def _section(report: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = (report.get("sections") or {}).get(name) or {}
    return value if isinstance(value, Mapping) else {}


def _data(report: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = _section(report, name).get("data") or {}
    return value if isinstance(value, Mapping) else {}


def _ticker(report: Mapping[str, Any]) -> str:
    return _text(report.get("ticker"), "UNKNOWN").upper()


def _company(report: Mapping[str, Any]) -> str:
    return _text(report.get("company"), _ticker(report))


def _sector(report: Mapping[str, Any]) -> str:
    return _text(report.get("sector"))


def _first_num(mapping: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _num(mapping.get(key))
        if value is not None:
            return value
    return None


def _first_text(mapping: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(mapping.get(key))
        if value:
            return value
    return ""


def _news_items(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = _section(report, "news").get("data") or []
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _today_change(report: Mapping[str, Any]) -> float | None:
    quote = report.get("quote") or {}
    if isinstance(quote, Mapping):
        value = _first_num(
            quote,
            "change_pct", "percent_change", "day_change_pct",
            "regular_market_change_percent", "regularMarketChangePercent",
        )
        if value is not None:
            return value
    return _first_num(
        _data(report, "technical"),
        "day_change_pct", "change_pct", "one_day_pct",
    )


def _relative_volume(report: Mapping[str, Any]) -> float | None:
    return _first_num(
        _data(report, "technical"),
        "volume_ratio", "relative_volume", "relative_volume_ratio", "rvol",
    )


def _dedupe(items: Sequence[str], limit: int = 6) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = re.sub(r"\s+", " ", _text(item)).strip()
        key = clean.lower().rstrip(".")
        if clean and key not in seen:
            seen.add(key)
            output.append(clean.rstrip(".") + ".")
        if len(output) >= limit:
            break
    return output


def _financial_evidence(report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    data = _data(report, "financials")
    supports: list[str] = []
    concerns: list[str] = []

    revenue = _first_num(data, "revenue_growth_pct", "revenue_growth", "revenueGrowth")
    eps = _first_num(data, "eps_growth_pct", "eps_growth", "epsGrowth")
    gross = _first_num(data, "gross_margin_pct", "gross_margin", "grossMargin")
    operating = _first_num(data, "operating_margin_pct", "operating_margin")
    roic = _first_num(data, "roic_pct", "roic", "return_on_invested_capital")
    fcf = _first_num(data, "free_cash_flow", "freeCashFlow", "fcf")
    debt = _first_num(data, "debt", "total_debt", "totalDebt")
    cash = _first_num(data, "cash", "cash_and_equivalents", "cashAndCashEquivalents")
    forward_pe = _first_num(data, "forward_pe", "forwardPE", "pe_forward")
    peg = _first_num(data, "peg_ratio", "peg", "pegRatio")

    if revenue is not None:
        target = supports if revenue >= 5 else concerns
        target.append(f"Revenue growth is {revenue:.1f}%")
    if eps is not None:
        target = supports if eps >= 5 else concerns
        target.append(f"EPS growth is {eps:.1f}%")
    if gross is not None:
        target = supports if gross >= 40 else concerns
        target.append(f"Gross margin is {gross:.1f}%")
    if operating is not None:
        target = supports if operating >= 15 else concerns
        target.append(f"Operating margin is {operating:.1f}%")
    if roic is not None:
        target = supports if roic >= 12 else concerns
        target.append(f"ROIC is {roic:.1f}%")
    if fcf is not None:
        target = supports if fcf > 0 else concerns
        target.append(f"Free cash flow is ${fcf:,.0f}")
    if cash is not None and debt is not None:
        if cash >= debt:
            supports.append(f"Cash of ${cash:,.0f} covers debt of ${debt:,.0f}")
        else:
            concerns.append(f"Debt of ${debt:,.0f} exceeds cash of ${cash:,.0f}")
    if forward_pe is not None:
        target = concerns if forward_pe >= 35 else supports
        target.append(f"Forward P/E is {forward_pe:.1f}×")
    if peg is not None:
        target = concerns if peg > 2 else supports
        target.append(f"PEG is {peg:.2f}")

    return supports, concerns


def _technical_evidence(report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    data = _data(report, "technical")
    supports: list[str] = []
    concerns: list[str] = []

    rsi = _first_num(data, "rsi", "rsi14")
    rvol = _relative_volume(report)
    price = _first_num(data, "price", "current_price") or _num(report.get("current_price"))
    sma50 = _first_num(data, "sma50", "sma_50")
    sma200 = _first_num(data, "sma200", "sma_200")
    technical_score = _first_num(
        report.get("score_attribution") or {},
        "technical_score", "technical_confirmation_score",
    )

    if rsi is not None:
        if 40 <= rsi <= 70:
            supports.append(f"RSI is {rsi:.1f}, indicating balanced momentum")
        elif rsi > 75:
            concerns.append(f"RSI is elevated at {rsi:.1f}")
        elif rsi < 35:
            concerns.append(f"RSI is weak at {rsi:.1f}")
    if rvol is not None:
        target = supports if rvol >= 1.0 else concerns
        target.append(f"Relative volume is {rvol:.2f}× normal")
    if price is not None and sma50 is not None:
        target = supports if price >= sma50 else concerns
        target.append(
            f"Price ${price:.2f} is {'above' if price >= sma50 else 'below'} the 50-day average ${sma50:.2f}"
        )
    if price is not None and sma200 is not None:
        target = supports if price >= sma200 else concerns
        target.append(
            f"Price is {'above' if price >= sma200 else 'below'} the 200-day average ${sma200:.2f}"
        )
    if technical_score is not None:
        target = supports if technical_score >= 60 else concerns
        target.append(f"Technical confirmation score is {technical_score:.1f}/100")

    return supports, concerns


def _earnings_evidence(report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    data = _data(report, "earnings")
    supports: list[str] = []
    concerns: list[str] = []

    eps_surprise = _first_num(data, "eps_surprise_pct", "epsSurprisePct")
    revenue_surprise = _first_num(data, "revenue_surprise_pct", "revenueSurprisePct")
    guidance = _first_text(data, "guidance", "guidance_summary")
    tone = _first_text(data, "management_tone", "tone")

    if eps_surprise is not None:
        target = supports if eps_surprise >= 0 else concerns
        target.append(
            f"Latest EPS {'beat' if eps_surprise >= 0 else 'miss'} was {abs(eps_surprise):.1f}%"
        )
    if revenue_surprise is not None:
        target = supports if revenue_surprise >= 0 else concerns
        target.append(
            f"Latest revenue {'beat' if revenue_surprise >= 0 else 'miss'} was {abs(revenue_surprise):.1f}%"
        )
    if guidance:
        text = guidance[:180]
        target = concerns if re.search(r"cut|lower|weak|cautious|below", text, re.I) else supports
        target.append(f"Management guidance: {text}")
    if tone:
        target = concerns if re.search(r"cautious|negative|weak", tone, re.I) else supports
        target.append(f"Management tone is described as {tone}")

    return supports, concerns


def _analyst_evidence(report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    data = _data(report, "analysts")
    supports: list[str] = []
    concerns: list[str] = []
    average = _first_num(data, "average_target", "price_target_average", "target_mean")
    current = _num(report.get("current_price"))
    buy_count = _first_num(data, "buy_count", "buy")
    hold_count = _first_num(data, "hold_count", "hold")
    sell_count = _first_num(data, "sell_count", "sell")

    if average is not None and current is not None and current > 0:
        upside = (average / current - 1) * 100
        target = supports if upside >= 8 else concerns
        target.append(f"Wall Street's average target implies {upside:+.1f}% versus the current price")
    if buy_count is not None or hold_count is not None or sell_count is not None:
        supports.append(
            "Analyst mix is "
            f"{int(buy_count or 0)} Buy, {int(hold_count or 0)} Hold, and {int(sell_count or 0)} Sell"
        )
    return supports, concerns


def _news_evidence(report: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    supports: list[str] = []
    concerns: list[str] = []
    for item in _news_items(report)[:5]:
        headline = _text(item.get("headline") or item.get("title"))
        sentiment = _text(item.get("sentiment")).lower()
        if not headline:
            continue
        target = concerns if ("negative" in sentiment or "bear" in sentiment) else supports
        target.append(f"Recent catalyst: {headline[:180]}")
    return supports, concerns


def _risk_evidence(report: Mapping[str, Any]) -> list[str]:
    risks: list[str] = []
    section = _section(report, "risk")
    data = section.get("data") or []
    if isinstance(data, list):
        for item in data[:5]:
            if not isinstance(item, Mapping):
                continue
            factor = _text(item.get("factor") or item.get("risk") or item.get("category"))
            detail = _text(item.get("atlas_interpretation") or item.get("detail"))
            level = _text(item.get("level") or item.get("rating"))
            if factor:
                risks.append(
                    f"{factor}{f' ({level})' if level else ''}: {detail or 'requires monitoring'}"
                )
    return risks


def _stock_specific_context(report: Mapping[str, Any]) -> dict[str, Any]:
    ticker = _ticker(report)
    company = _company(report)
    sector = _sector(report)
    verdict = _text(report.get("committee_verdict"), "MONITOR").replace("_", " ").title()
    opportunity = _num(report.get("opportunity_score"))
    confidence = _num(report.get("confidence_pct"))
    expected_return = _num(report.get("expected_return_pct"))
    current_price = _num(report.get("current_price"))
    fair_value = _num(report.get("validated_fair_value"))

    supports: list[str] = []
    concerns: list[str] = []

    for extractor in (
        _financial_evidence,
        _earnings_evidence,
        _analyst_evidence,
        _technical_evidence,
        _news_evidence,
    ):
        positive, negative = extractor(report)
        supports.extend(positive)
        concerns.extend(negative)

    supports.extend(_text(item) for item in (report.get("bull_case") or []))
    concerns.extend(_text(item) for item in (report.get("bear_case") or []))
    concerns.extend(_risk_evidence(report))

    if expected_return is not None:
        target = supports if expected_return >= 8 else concerns
        target.append(f"Atlas validated expected return is {expected_return:+.1f}%")
    if current_price is not None and fair_value is not None and current_price > 0:
        upside = (fair_value / current_price - 1) * 100
        target = supports if upside >= 8 else concerns
        target.append(
            f"Validated fair value ${fair_value:.2f} implies {upside:+.1f}% from ${current_price:.2f}"
        )

    supports = _dedupe(supports, 8)
    concerns = _dedupe(concerns, 8)

    if not supports:
        supports.append(
            f"{ticker}'s current Atlas opportunity score is "
            f"{opportunity:.1f}/100." if opportunity is not None
            else f"{ticker} remains in the active Atlas research universe."
        )
    if not concerns:
        concerns.append(
            f"{ticker} requires continued monitoring because not every research component "
            "is currently strong enough to support an unrestricted position."
        )

    return {
        "ticker": ticker,
        "company": company,
        "sector": sector,
        "verdict": verdict,
        "opportunity": opportunity,
        "confidence": confidence,
        "expected_return": expected_return,
        "supports": supports,
        "concerns": concerns,
    }


def build_today_move(report: Mapping[str, Any]) -> dict[str, Any]:
    ticker = _ticker(report)
    change = _today_change(report)
    relative_volume = _relative_volume(report)
    news = _news_items(report)

    verified: list[str] = []
    inferences: list[str] = []
    limitations: list[str] = []

    if change is not None:
        direction = "higher" if change > 0 else "lower" if change < 0 else "flat"
        verified.append(f"{ticker} is trading {direction} by {abs(change):.1f}% in the loaded market data.")
    else:
        limitations.append(f"A verified intraday percentage move was not included for {ticker}.")

    if relative_volume is not None:
        verified.append(f"{ticker}'s relative volume is {relative_volume:.2f}× normal.")
        if relative_volume >= 2:
            inferences.append(f"{ticker} is attracting unusually elevated trading participation.")
        elif relative_volume >= 1.25:
            inferences.append(f"{ticker}'s volume confirms above-average investor attention.")
        elif relative_volume < 0.75:
            inferences.append(f"{ticker}'s move is occurring on relatively light participation.")
    else:
        limitations.append(f"Relative-volume data were not populated for {ticker}.")

    headlines = [
        _text(item.get("headline") or item.get("title"))
        for item in news[:8]
    ]
    material_headlines = [headline for headline in headlines if headline]
    if material_headlines:
        verified.append(f"Atlas reviewed {len(material_headlines)} recent verified {ticker} news items.")
        inferences.append(f"The leading loaded catalyst is: {material_headlines[0][:180]}.")
    else:
        limitations.append(f"No recent verified {ticker} news items were loaded for cause attribution.")

    if not inferences:
        inferences.append(
            f"Atlas does not yet have enough verified evidence to assign one dominant cause "
            f"to {ticker}'s current move."
        )

    confidence = 35 + (20 if change is not None else 0) + (15 if relative_volume is not None else 0)
    confidence += 25 if material_headlines else 0

    return {
        "headline": f"{ticker} today's move: {change:+.1f}%" if change is not None else f"{ticker} today's move is under review",
        "verified_facts": _dedupe(verified, 6),
        "atlas_inferences": _dedupe(inferences, 5),
        "data_limitations": _dedupe(limitations, 5),
        "explanation_confidence_pct": min(95, confidence),
        "top_headlines": material_headlines[:5],
    }


def build_executive_intelligence(report: Mapping[str, Any]) -> dict[str, Any]:
    context = _stock_specific_context(report)
    ticker = context["ticker"]
    company = context["company"]
    sector = context["sector"]
    verdict = context["verdict"]
    opportunity = context["opportunity"]
    confidence = context["confidence"]
    expected_return = context["expected_return"]
    supports = context["supports"]
    concerns = context["concerns"]

    identity = f"{company} ({ticker})" if company.upper() != ticker else ticker
    summary_parts = [f"Atlas rates {identity} {verdict}."]
    if sector:
        summary_parts.append(f"The company operates in the {sector} sector.")
    if opportunity is not None and confidence is not None:
        summary_parts.append(
            f"Its opportunity score is {opportunity:.1f}/100 with {confidence:.1f}% confidence."
        )
    if expected_return is not None:
        summary_parts.append(f"Validated expected return is {expected_return:+.1f}%.")
    summary_parts.append("Primary support: " + " ".join(supports[:2]))
    summary_parts.append("Primary risk: " + concerns[0])
    executive_summary = " ".join(summary_parts)

    upgrade_triggers = _dedupe(
        [_text(item) for item in (report.get("upgrade_triggers") or [])]
        + [
            f"{ticker}'s earnings or guidance improve without a valuation deterioration.",
            f"{ticker}'s technical trend confirms with stronger price and volume evidence.",
        ],
        5,
    )
    downgrade_triggers = _dedupe(
        [_text(item) for item in (report.get("downgrade_triggers") or [])]
        + [
            f"{ticker}'s earnings estimates or management guidance deteriorate materially.",
            f"{ticker}'s validated fair value falls below the market price.",
            f"{ticker} breaks key support on sustained heavy selling volume.",
        ],
        5,
    )

    return {
        "executive_summary": executive_summary,
        "why_atlas_supports_it": supports[:6],
        "key_risks": concerns[:6],
        "upgrade_triggers": upgrade_triggers,
        "downgrade_triggers": downgrade_triggers,
        "today_move": build_today_move(report),
        "evidence_note": (
            f"{ticker}'s narrative is grounded in the current normalized Atlas report. "
            "Unavailable evidence is explicitly treated as a limitation."
        ),
        "narrative_quality": {
            "ticker": ticker,
            "company": company,
            "numeric_fact_count": len(re.findall(r"[-+]?\$?\d+(?:\.\d+)?%?", executive_summary)),
            "support_count": len(supports),
            "risk_count": len(concerns),
            "stock_specific": ticker in executive_summary,
        },
    }


__all__ = ["build_executive_intelligence", "build_today_move"]
