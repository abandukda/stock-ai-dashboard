"""Reporting-only models for the guidance-first Atlas Home page.

This module selects presentation priorities *after* the V104 committee has
finished.  It never calculates or changes an investment score, verdict,
valuation, expected return, trade plan, or provider field.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
import math
from typing import Any, Iterable, Mapping

from engines.guidance_summary import build_guidance_summary
from engines.semantic_fields import analyst_consensus, canonical_atlas_fair_value


FAMILIAR_MEGA_CAPS = {"AAPL", "AMZN", "AVGO", "CRM", "GOOGL", "META", "MSFT", "NVDA", "TSLA"}
_MISSING = {None, "", "Unavailable", "Under review", "Unknown", "—"}
STRONG_HEADLINE_SUPPORT = "STRONG / COMPREHENSIVE"
GAPPED_HEADLINE_SUPPORT = "SUPPORTED WITH EVIDENCE GAPS"
CLIENT_STRONG_SUPPORT = "STRONG SUPPORT"
CLIENT_SUPPORTED = "SUPPORTED"


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    legacy = row.get("Raw") if isinstance(row.get("Raw"), Mapping) else {}
    nested_raw = raw.get("raw") if isinstance(raw.get("raw"), Mapping) else {}
    nested_legacy = raw.get("Raw") if isinstance(raw.get("Raw"), Mapping) else {}
    for source in (row, raw, legacy, nested_raw, nested_legacy):
        for key in keys:
            value = source.get(key)
            if isinstance(value, float) and not math.isfinite(value):
                continue
            if value not in _MISSING:
                return value
    return None


def classify_entry_status(price: Any, preferred_low: Any, preferred_high: Any) -> dict[str, Any]:
    """Describe price versus the persisted entry range without changing a decision."""
    price_value, low, high = _num(price), _num(preferred_low), _num(preferred_high)
    if price_value is None or price_value <= 0 or low is None or high is None or low <= 0 or high < low:
        return {"code": "UNAVAILABLE", "label": "Entry context unavailable", "action": None}
    if price_value < low:
        return {"code": "BELOW", "label": "Below preferred entry", "action": "Review before entering"}
    if price_value <= high:
        return {"code": "INSIDE", "label": "Inside Atlas preferred entry", "action": "Within the preferred range"}
    return {"code": "ABOVE", "label": "Above preferred entry", "action": "Wait for a better entry"}


def build_client_evidence_view(
    row: Mapping[str, Any],
    *,
    presentation_price: Any = None,
    presentation_price_as_of: Any = None,
    presentation_price_source_type: str | None = None,
) -> dict[str, Any]:
    """Resolve paid-client presentation from existing evidence only.

    A supplied presentation quote is isolated from every persisted investment
    field. When absent or invalid, the legitimate scanner signal price is used.
    """
    signal_price = _num(_first(row, "current_price", "price", "Current Price"))
    fresh_price = _num(presentation_price)
    if fresh_price is not None and fresh_price > 0:
        shown_price = fresh_price
        price_source_type = presentation_price_source_type or "Presentation market quote"
        price_as_of = presentation_price_as_of
        is_fresher = True
    else:
        shown_price = signal_price
        price_source_type = "Persisted scanner signal price" if signal_price is not None else "Unavailable"
        price_as_of = _first(row, "scan_time", "generated_at", "signal_as_of")
        is_fresher = False
    low = _num(_first(row, "preferred_entry_low", "entry_low", "Entry Low"))
    high = _num(_first(row, "preferred_entry_high", "entry_high", "Entry High"))
    atlas_value = canonical_atlas_fair_value(row)
    street = analyst_consensus(row).get("mean")
    valuation_items = []
    if atlas_value is not None:
        valuation_items.append({"label": "Atlas Fair Value", "value": atlas_value})
    if street is not None:
        valuation_items.append({"label": "Wall Street Consensus", "value": street})
    if atlas_value is None and street is None:
        valuation_limitation = "Valuation confirmation is limited."
    elif atlas_value is None:
        valuation_limitation = "Atlas valuation is not currently published."
    elif street is None:
        valuation_limitation = "Wall Street consensus is not currently available."
    else:
        valuation_limitation = None
    support = str(row.get("headline_support_quality") or GAPPED_HEADLINE_SUPPORT)
    guidance = row.get("guidance_summary") if isinstance(row.get("guidance_summary"), Mapping) else build_guidance_summary(row)
    facts = guidance.get("supporting_facts") or []
    return {
        "ticker": _text(row.get("ticker"), "UNKNOWN"),
        "company": _text(_first(row, "company", "company_name", "Company"), _text(row.get("ticker"), "UNKNOWN")),
        "recommendation": _text(row.get("committee_verdict"), "MONITOR"),
        "signal_price": signal_price,
        "presentation_price": shown_price,
        "presentation_price_source_type": price_source_type,
        "presentation_price_as_of": price_as_of,
        "uses_fresher_presentation_price": is_fresher,
        "preferred_entry_low": low,
        "preferred_entry_high": high,
        "entry_status": classify_entry_status(shown_price, low, high),
        "atlas_fair_value": atlas_value,
        "analyst_consensus": street,
        "valuation_items": valuation_items,
        "valuation_limitation": valuation_limitation,
        "headline_eligible": bool(row.get("headline_eligible")),
        "support_quality_internal": support,
        "support_quality_client": CLIENT_STRONG_SUPPORT if support == STRONG_HEADLINE_SUPPORT else CLIENT_SUPPORTED,
        "primary_thesis": _text((facts[0] or {}).get("fact") if facts else None, "Open full research for the current Atlas thesis."),
        "guidance_summary": guidance,
    }


def _ticker_set(values: Iterable[Any] | None) -> set[str]:
    return {_text(value).upper() for value in (values or []) if _text(value)}


def _history_for(history: Mapping[str, Any] | None, ticker: str) -> Mapping[str, Any]:
    value = (history or {}).get(ticker, {})
    return value if isinstance(value, Mapping) else {}


def _discovery_key(
    row: Mapping[str, Any],
    *,
    held: bool,
    watched: bool,
    history: Mapping[str, Any],
) -> tuple[float, ...]:
    """Presentation priority among BUY_NOW rows; not an investment score."""
    ticker = _text(row.get("ticker")).upper()
    opportunity = _num(row.get("opportunity_score")) or 0.0
    confidence = _num(row.get("confidence_pct")) or 0.0
    expected = _num(row.get("expected_return_pct")) or 0.0
    coverage = _num(row.get("component_coverage_pct")) or 0.0
    repeats = int(_num(history.get("consecutive_top3")) or 0)
    changed = bool(history.get("meaningful_evidence_changed"))
    entered_zone = bool(history.get("newly_in_entry_zone"))
    improved = _text(history.get("prior_recommendation")).upper() not in {"", "BUY_NOW"}

    evidence = row.get("guidance_summary") or {}
    domains = {item.get("domain") for item in evidence.get("supporting_facts") or [] if item.get("domain")}
    substantiated = bool(row.get("discovery_evidence_eligible"))
    # Discovery context is deliberately the final tiebreaker. It cannot
    # outrank investment/actionability or evidence quality.
    context = 0.0
    context += 1.0 if ticker not in FAMILIAR_MEGA_CAPS else 0.0
    context -= 1.0 if held else 0.0
    context -= 0.5 if watched else 0.0
    context -= min(repeats, 3) * 0.5
    context += 1.0 if (changed or entered_zone or improved) else 0.0
    return (
        1.0 if substantiated else 0.0,
        opportunity,
        confidence,
        expected,
        coverage,
        len(domains),
        context,
        -len(ticker),
    )


def evaluate_headline_eligibility(row: Mapping[str, Any], guidance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate reporting eligibility without changing the investment decision."""
    guidance = guidance or build_guidance_summary(row)
    coverage = _num(row.get("component_coverage_pct")) or 0.0
    price = _num(_first(row, "current_price", "price", "Current Price"))
    preferred_low = _num(_first(row, "preferred_entry_low", "entry_low", "Entry Low"))
    preferred_high = _num(_first(row, "preferred_entry_high", "entry_high", "Entry High"))
    domains: set[str] = set()
    growth = any(_num(_first(row, key)) is not None for key in ("revenue_growth", "earnings_growth"))
    profitability = any(_num(_first(row, key)) is not None for key in (
        "gross_profit_margin", "operating_profit_margin", "free_cash_flow",
        "operating_cash_flow", "roic", "roe",
    ))
    earnings_result = any(_num(_first(row, key)) is not None for key in (
        "reported_eps", "eps_surprise_pct", "revenue_surprise_pct",
    ))
    atlas_value = _num(_first(row, "atlas_fair_value", "Atlas Fair Value"))
    analyst_mean = _num(_first(row, "analyst_target_mean", "Analyst Target"))
    analyst_count = _num(_first(row, "analyst_count", "Analyst Count"))
    technical = any(_num(_first(row, key)) is not None for key in ("rsi", "sma20", "sma50", "volume_ratio"))
    ownership = any(_num(_first(row, key)) is not None for key in (
        "institutional_ownership_pct", "insider_ownership_pct",
    ))
    headline = _text(_first(row, "latest_news_headline", "Top News"))
    publisher = _text(_first(row, "latest_news_source", "Latest News Source"))
    verified_news = bool(headline and publisher and "no recent high-confidence" not in headline.lower())
    catalyst = guidance.get("next_catalyst") or {}
    verified_catalyst = bool(catalyst.get("date") and str(catalyst.get("verification_status", "")).lower().startswith("verified"))
    for available, name in (
        (growth, "earnings_growth"), (profitability, "profitability_cash"),
        (earnings_result, "earnings_result"), (atlas_value is not None, "canonical_valuation"),
        (analyst_mean is not None and analyst_count is not None and analyst_count > 0, "analyst"),
        (technical, "technical_timing"), (ownership, "ownership"),
        (verified_news, "verified_news"), (verified_catalyst, "verified_catalyst"),
    ):
        if available:
            domains.add(name)

    risks = [str(item.get("risk") or "").strip() for item in guidance.get("key_risks") or [] if isinstance(item, Mapping)]
    generic_risk = ("normal pullback", "normal market", "execution risk")
    material_gaps = [str(item).lower() for item in guidance.get("unavailable_evidence") or []]
    concrete_limitation = any(
        marker in gap for gap in material_gaps
        for marker in ("canonical atlas fair value", "earnings-surprise", "cash flow", "margin", "verified next catalyst")
    )
    concrete_risk = any(risk and not any(marker in risk.lower() for marker in generic_risk) for risk in risks) or concrete_limitation
    primary = bool({"earnings_growth", "profitability_cash", "earnings_result", "canonical_valuation"} & domains)
    confirmation = bool(domains - {"earnings_growth", "profitability_cash", "earnings_result", "canonical_valuation", "technical_timing"})
    reasons = []
    if row.get("committee_verdict") != "BUY_NOW":
        reasons.append("not_buy_now")
    if price is None or price <= 0:
        reasons.append("invalid_current_price")
    if preferred_low is None or preferred_high is None or preferred_low <= 0 or preferred_high < preferred_low:
        reasons.append("preferred_entry_unavailable")
    if coverage < 70:
        reasons.append("evidence_coverage_below_70")
    if len(domains) < 3:
        reasons.append("fewer_than_three_independent_evidence_domains")
    if not primary:
        reasons.append("no_strong_primary_thesis_domain")
    if not confirmation:
        reasons.append("no_independent_confirmation_domain")
    if not concrete_risk:
        reasons.append("no_concrete_explainable_risk")
    if guidance.get("evidence_limited"):
        reasons.append("evidence_limited_thesis")
    if atlas_value is None and analyst_mean is None and not ({"profitability_cash", "earnings_result", "verified_news", "verified_catalyst"} & domains):
        reasons.append("no_valuation_or_independent_deep_confirmation")
    comprehensive_domains = {
        "earnings_growth", "earnings_result", "profitability_cash", "analyst",
        "ownership", "technical_timing",
    }
    missing_material_domains = sorted(comprehensive_domains - domains)
    if not ({"verified_news", "verified_catalyst"} & domains):
        missing_material_domains.append("verified_news_or_catalyst")
    # Canonical valuation is reported as a gap when absent, but it is not a
    # requirement for comprehensive support and never changes eligibility.
    if "canonical_valuation" not in domains:
        missing_material_domains.append("canonical_valuation")
    support_quality = (
        STRONG_HEADLINE_SUPPORT
        if comprehensive_domains.issubset(domains) and {"verified_news", "verified_catalyst"} & domains
        else GAPPED_HEADLINE_SUPPORT
    )
    return {
        "eligible": not reasons,
        "evidence_domains": sorted(domains),
        "support_quality": support_quality,
        "missing_material_domains": missing_material_domains,
        "missing_critical_domains": [
            name for present, name in ((primary, "primary_thesis"), (confirmation, "independent_confirmation"), (concrete_risk, "concrete_risk"))
            if not present
        ],
        "reason_codes": reasons,
        "coverage_pct": coverage,
        "evidence_limited": bool(guidance.get("evidence_limited")),
    }


def audit_headline_evidence_quality(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """QA finding for headline rows that contradict the presentation guard."""
    findings = []
    for row in rows or []:
        result = evaluate_headline_eligibility(row, row.get("guidance_summary"))
        if row.get("committee_verdict") == "BUY_NOW" and not result["eligible"]:
            findings.append({
                "ticker": _text(row.get("ticker"), "UNKNOWN"),
                "rule": "HEADLINE BUY NOW EVIDENCE QUALITY",
                "severity": "HIGH",
                "reason_codes": result["reason_codes"],
            })
    return findings


def select_home_discoveries(
    rows: Iterable[Mapping[str, Any]],
    *,
    limit: int = 3,
    portfolio_tickers: Iterable[Any] | None = None,
    watchlist_tickers: Iterable[Any] | None = None,
    history: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select headline discoveries exclusively from existing BUY_NOW rows."""
    held_set, watched_set = _ticker_set(portfolio_tickers), _ticker_set(watchlist_tickers)
    eligible = []
    for source in rows or []:
        if not isinstance(source, Mapping) or source.get("committee_verdict") != "BUY_NOW":
            continue
        row = dict(source)
        ticker = _text(row.get("ticker")).upper()
        held, watched = ticker in held_set, ticker in watched_set
        prior = _history_for(history, ticker)
        row["guidance_summary"] = build_guidance_summary(row)
        headline = evaluate_headline_eligibility(row, row["guidance_summary"])
        evidence_ok = headline["eligible"]
        evidence_reason = "; ".join(headline["reason_codes"]) or "Headline evidence guard satisfied"
        row["discovery_evidence_eligible"] = evidence_ok
        row["discovery_evidence_reason"] = evidence_reason
        row["headline_eligible"] = evidence_ok
        row["headline_exclusion_reasons"] = headline["reason_codes"]
        row["headline_evidence_domains"] = headline["evidence_domains"]
        row["headline_support_quality"] = headline["support_quality"]
        row["headline_missing_material_domains"] = headline["missing_material_domains"]
        row["portfolio_status"] = "Held" if held else "Not held"
        row["watchlist_status"] = "Watched" if watched else "Not watched"
        row["discovery_label"] = _freshness_label(prior)
        row["_discovery_key"] = _discovery_key(
            row, held=held, watched=watched, history=prior
        )
        row["discovery_selection_inputs"] = {
            "opportunity_score": _num(row.get("opportunity_score")),
            "confidence_pct": _num(row.get("confidence_pct")),
            "expected_return_pct": _num(row.get("expected_return_pct")),
            "component_coverage_pct": _num(row.get("component_coverage_pct")),
            "supporting_domains": [
                item.get("domain")
                for item in row["guidance_summary"].get("supporting_facts") or []
                if item.get("domain")
            ],
            "evidence_eligible": evidence_ok,
            "portfolio_status": row["portfolio_status"],
            "watchlist_status": row["watchlist_status"],
            "consecutive_top3": int(_num(prior.get("consecutive_top3")) or 0),
            "meaningful_evidence_changed": bool(prior.get("meaningful_evidence_changed")),
            "newly_in_entry_zone": bool(prior.get("newly_in_entry_zone")),
        }
        eligible.append(row)

    eligible.sort(key=lambda item: (item["_discovery_key"], _text(item.get("ticker"))), reverse=True)
    substantiated = [row for row in eligible if row["discovery_evidence_eligible"]]
    selected = substantiated[: max(0, int(limit))]
    for row in eligible:
        row.pop("_discovery_key", None)
    return {"selected": selected, "eligible": eligible, "count": len(eligible)}


def _freshness_label(prior: Mapping[str, Any]) -> str | None:
    if not prior:
        return None
    prior_rec = _text(prior.get("prior_recommendation")).upper()
    repeats = int(_num(prior.get("consecutive_top3")) or 0)
    if prior_rec and prior_rec != "BUY_NOW":
        return "NEW BUY NOW"
    if repeats > 0:
        return "STILL BUY NOW"
    if prior.get("previously_appeared"):
        return "RETURNING OPPORTUNITY"
    return None


def build_home_intelligence(
    rows: Iterable[Mapping[str, Any]],
    *,
    portfolio_tickers: Iterable[Any] | None = None,
    watchlist_tickers: Iterable[Any] | None = None,
    history: Mapping[str, Any] | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    normalized = [dict(row) for row in (rows or []) if isinstance(row, Mapping)]
    held, watched = _ticker_set(portfolio_tickers), _ticker_set(watchlist_tickers)
    discovery = select_home_discoveries(
        normalized, portfolio_tickers=held, watchlist_tickers=watched, history=history
    )
    counts = Counter(_text(row.get("committee_verdict"), "MONITOR") for row in normalized)
    actionable = [row for row in normalized if row.get("committee_verdict") in {"BUY_NOW", "ACCUMULATE"}]
    sectors = Counter(_text(row.get("sector"), "Unknown") for row in actionable)
    themes = [name for name, _ in sectors.most_common(2) if name != "Unknown"]
    posture = "selective"
    if counts["BUY_NOW"] >= 10:
        posture = "constructive"
    elif not counts["BUY_NOW"]:
        posture = "cautious"
    buy_now = discovery["eligible"]
    all_buy_now = []
    entry_counts = Counter()
    for row in buy_now:
        client_view = build_client_evidence_view(row)
        row["client_evidence_view"] = client_view
        all_buy_now.append(row)
        entry_counts[client_view["entry_status"]["code"]] += 1
    theme_text = f" The current opportunities are concentrated in {' and '.join(themes)}." if themes else ""
    if buy_now:
        stock_word = "stock" if len(buy_now) == 1 else "stocks"
        actionable_text = f"{entry_counts['INSIDE']} are inside their preferred entry ranges"
        if entry_counts["ABOVE"]:
            actionable_text += f", while {entry_counts['ABOVE']} are better approached on a pullback"
        if entry_counts["BELOW"]:
            actionable_text += f"; {entry_counts['BELOW']} currently trade below their preferred ranges and merit a fresh review"
        morning_view = (
            f"Atlas is {posture} today, with {len(buy_now)} {stock_word} meeting BUY NOW criteria. "
            f"{actionable_text}.{theme_text}"
        )
    else:
        morning_view = "Atlas is cautious today: no stocks currently meet BUY NOW criteria. Patience is warranted until stronger setups emerge."
    portfolio_actions = [row for row in normalized if _text(row.get("ticker")).upper() in held]
    watchlist_actions = [row for row in normalized if _text(row.get("ticker")).upper() in watched]
    catalysts = []
    priority = {_text(row.get("ticker")).upper(): 2 for row in discovery["selected"]}
    priority.update({ticker: 4 for ticker in held})
    priority.update({ticker: 3 for ticker in watched})
    today = as_of or date.today()
    for row in normalized:
        guidance = build_guidance_summary(row)
        catalyst = guidance.get("next_catalyst") or {}
        catalyst_date = catalyst.get("date")
        if not catalyst_date:
            continue
        try:
            event_date = datetime.fromisoformat(str(catalyst_date)[:10]).date()
        except ValueError:
            continue
        event_name = _text(catalyst.get("event"))
        is_earnings = "earnings" in event_name.lower()
        verification = _text(catalyst.get("verification_status"))
        news_source = _text(_first(row, "latest_news_source", "Latest News Source"))
        if not verification.lower().startswith("verified"):
            continue
        if not is_earnings and not news_source:
            continue
        in_window = today <= event_date <= today + timedelta(days=45) if is_earnings else today - timedelta(days=1) <= event_date <= today
        if not in_window:
            continue
        item = dict(row)
        item["guidance_summary"] = guidance
        item["catalyst_priority"] = priority.get(_text(row.get("ticker")).upper(), 1)
        item["catalyst_type"] = "Scheduled earnings" if is_earnings else "Company-specific news"
        item["catalyst_source"] = "Persisted provider earnings date" if is_earnings else f"Filtered company news · {news_source}"
        catalysts.append(item)
    catalysts.sort(key=lambda row: (-row["catalyst_priority"], (row["guidance_summary"].get("next_catalyst") or {}).get("date"), _text(row.get("ticker"))))
    catalyst_counts = Counter(row["catalyst_type"] for row in catalysts)
    return {
        "morning_view": morning_view,
        "counts": {
            "buy_now": counts["BUY_NOW"],
            "accumulate": counts["ACCUMULATE"],
            "monitor": counts["MONITOR"],
            "portfolio_actions": len(portfolio_actions),
            "watchlist_actions": len(watchlist_actions),
            "verified_catalysts": len(catalysts),
            "scheduled_earnings": catalyst_counts["Scheduled earnings"],
            "company_news_events": catalyst_counts["Company-specific news"],
        },
        "discoveries": discovery,
        "all_buy_now": all_buy_now,
        "buy_now_accessible_count": len(all_buy_now),
        "portfolio_actions": portfolio_actions,
        "watchlist_actions": watchlist_actions,
        "catalysts": catalysts,
    }


__all__ = [
    "CLIENT_STRONG_SUPPORT", "CLIENT_SUPPORTED", "GAPPED_HEADLINE_SUPPORT", "STRONG_HEADLINE_SUPPORT",
    "audit_headline_evidence_quality", "build_client_evidence_view", "build_home_intelligence",
    "classify_entry_status", "evaluate_headline_eligibility", "select_home_discoveries",
]
