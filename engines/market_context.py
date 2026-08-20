"""Provider-independent Phase 9C market context and Home snapshot objects."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _trend(row: Mapping[str, Any]) -> dict[str, Any]:
    price = _number(row.get("price") if row.get("price") is not None else row.get("current_price"))
    sma50, sma200 = _number(row.get("sma50")), _number(row.get("sma200"))
    if price is None or sma50 is None or sma200 is None:
        return {"status": DATA_UNAVAILABLE, "price": price, "sma50": sma50, "sma200": sma200, "trend": "UNAVAILABLE"}
    if price > sma50 > sma200:
        trend = "UPTREND"
    elif price < sma50 < sma200:
        trend = "DOWNTREND"
    else:
        trend = "MIXED"
    return {"status": AVAILABLE, "price": price, "sma50": sma50, "sma200": sma200, "trend": trend}


def build_market_context(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    evidence = evidence if isinstance(evidence, Mapping) else {}
    spy = _trend(evidence.get("SPY") or {})
    qqq = _trend(evidence.get("QQQ") or {})
    if spy["status"] != AVAILABLE:
        regime = "UNAVAILABLE"
    elif spy["trend"] == "UPTREND" and qqq.get("trend") in {"UPTREND", "MIXED", "UNAVAILABLE"}:
        regime = "RISK_ON"
    elif spy["trend"] == "DOWNTREND" or qqq.get("trend") == "DOWNTREND":
        regime = "RISK_OFF"
    else:
        regime = "NEUTRAL"
    volatility = _number(evidence.get("volatility_pct") or evidence.get("vix"))
    volatility_state = (
        "UNAVAILABLE" if volatility is None else "ELEVATED" if volatility >= 25 else "CALM" if volatility < 15 else "NORMAL"
    )
    sectors = []
    for item in evidence.get("sector_etfs") or []:
        if not isinstance(item, Mapping):
            continue
        strength = _number(item.get("relative_strength_pct") if item.get("relative_strength_pct") is not None else item.get("return_pct"))
        if strength is not None:
            sectors.append({"symbol": item.get("symbol"), "sector": item.get("sector"), "relative_strength_pct": strength})
    sectors.sort(key=lambda item: item["relative_strength_pct"], reverse=True)
    return {
        "version": "MARKET_CONTEXT_V1",
        "semantic_status": AVAILABLE if regime != "UNAVAILABLE" else DATA_UNAVAILABLE,
        "as_of": evidence.get("as_of"),
        "source_label": evidence.get("source_label") or "Latest Atlas production scan",
        "is_real_time": False,
        "spy": spy,
        "qqq": qqq,
        "market_regime": regime,
        "volatility_value": volatility,
        "volatility_state": volatility_state,
        "sector_relative_strength": sectors,
    }


def build_atlas_now(
    rows: Sequence[Mapping[str, Any]],
    *,
    market_context: Mapping[str, Any] | None = None,
    watchlist_tickers: Sequence[str] = (),
    as_of: str | None = None,
) -> dict[str, Any]:
    watch = {str(item).upper() for item in watchlist_tickers}
    buy_now = [row for row in rows if str(row.get("committee_verdict") or "").upper() == "BUY_NOW"]
    developing = [row for row in rows if str(row.get("committee_verdict") or "").upper() == "ACCUMULATE"]
    promoted = {str(row.get("ticker") or "").upper() for row in buy_now + developing} | watch
    earnings = []
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        date = row.get("next_earnings_date")
        if ticker in promoted and date:
            earnings.append({"ticker": ticker, "date": str(date), "recommendation": row.get("committee_verdict")})
    earnings.sort(key=lambda item: item["date"])
    changes = [row.get("research_change") for row in rows if row.get("research_change")]
    context = market_context or build_market_context({})
    return {
        "version": "ATLAS_NOW_V1",
        "semantic_status": AVAILABLE,
        "as_of": as_of or datetime.now(timezone.utc).isoformat(),
        "freshness_label": "Latest production scan — not real-time",
        "buy_now_count": len(buy_now),
        "developing_opportunity_count": len(developing),
        "upcoming_earnings": earnings,
        "market_regime": context.get("market_regime") or "UNAVAILABLE",
        "major_research_changes": changes[:5],
    }


__all__ = ["build_atlas_now", "build_market_context"]
