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


FAMILIAR_MEGA_CAPS = {"AAPL", "AMZN", "AVGO", "CRM", "GOOGL", "META", "MSFT", "NVDA", "TSLA"}
_MISSING = {None, "", "Unavailable", "Under review", "Unknown", "—"}


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
    for source in (row, raw, legacy):
        for key in keys:
            value = source.get(key)
            if value not in _MISSING:
                return value
    return None


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


def _evidence_eligibility(row: Mapping[str, Any], guidance: Mapping[str, Any]) -> tuple[bool, str]:
    """Headline presentation guard; missing canonical FV alone never fails it."""
    coverage = _num(row.get("component_coverage_pct")) or 0.0
    expected = _num(row.get("expected_return_pct"))
    domains = {item.get("domain") for item in guidance.get("supporting_facts") or [] if item.get("domain")}
    entry_available = _first(row, "entry_range", "entry_low", "Entry Range", "Entry Low") is not None
    base = coverage >= 70 and expected is not None and entry_available and len(domains) >= 2
    # Evidence-limited rows remain visible in the BUY_NOW universe but do not
    # displace substantiated alternatives in the headline three.
    substantiated = base and not bool(guidance.get("evidence_limited"))
    if substantiated:
        return True, f"Substantiated: {coverage:.0f}% coverage and {len(domains)} evidence domains"
    gaps = []
    if coverage < 70:
        gaps.append("coverage below 70%")
    if expected is None:
        gaps.append("expected return unavailable")
    if not entry_available:
        gaps.append("preferred entry unavailable")
    if len(domains) < 2:
        gaps.append("fewer than two supporting evidence domains")
    if guidance.get("evidence_limited"):
        gaps.append("GuidanceSummary marks evidence limited")
    return False, "; ".join(gaps) or "Evidence guard not met"


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
        evidence_ok, evidence_reason = _evidence_eligibility(row, row["guidance_summary"])
        row["discovery_evidence_eligible"] = evidence_ok
        row["discovery_evidence_reason"] = evidence_reason
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
    sparse = [row for row in eligible if not row["discovery_evidence_eligible"]]
    selected = (substantiated + sparse)[: max(0, int(limit))]
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
    buy_now = [row for row in normalized if row.get("committee_verdict") == "BUY_NOW"]
    buy_pct = counts["BUY_NOW"] / len(normalized) * 100 if normalized else 0.0
    near_entry = 0
    fv_available = 0
    strong_evidence = 0
    for row in buy_now:
        price = _num(_first(row, "current_price", "price"))
        low = _num(_first(row, "entry_low", "Entry Low"))
        high = _num(_first(row, "entry_high", "Entry High"))
        if price is not None and low is not None and high is not None and low <= price <= high:
            near_entry += 1
        if _num(_first(row, "atlas_fair_value", "Atlas Fair Value")) is not None:
            fv_available += 1
        if (_num(row.get("component_coverage_pct")) or 0) >= 80:
            strong_evidence += 1
    theme_text = f" Actionable evidence is concentrated in {' and '.join(themes)}." if themes else ""
    morning_view = (
        f"ATLAS is {posture} this morning: {counts['BUY_NOW']} of {len(normalized)} fully researched stocks "
        f"({buy_pct:.1f}%) qualify as BUY NOW, while {counts['ACCUMULATE']} are ACCUMULATE. "
        f"{near_entry} of {len(buy_now)} BUY NOW names trade inside their persisted preferred entry ranges; "
        f"canonical Atlas Fair Value is available for {fv_available}, and {strong_evidence} have at least 80% evidence coverage."
        f"{theme_text}"
    )
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
        "portfolio_actions": portfolio_actions,
        "watchlist_actions": watchlist_actions,
        "catalysts": catalysts,
    }


__all__ = ["build_home_intelligence", "select_home_discoveries"]
