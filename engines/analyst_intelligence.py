"""Deterministic Wall Street analyst semantics for Atlas research.

This module is presentation/research intelligence only.  Agreement labels,
trend labels, and Atlas/Street relationships never feed scoring, confidence,
ranking, recommendations, valuation, expected return, trades, or sizing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from collections.abc import Iterable, Mapping
from typing import Any

from engines.semantic_fields import (
    canonical_atlas_fair_value, is_missing_scalar, number, safe_mapping,
    safe_scalar_display, safe_sequence, semantic_identity,
)


HIGH_AGREEMENT_MAX = 31.1
MODERATE_AGREEMENT_MAX = 60.4
_BULLISH_RATINGS = {
    "buy", "strong buy", "outperform", "overweight", "positive",
    "market outperform", "sector outperform", "accumulate",
}
_BEARISH_RATINGS = {
    "sell", "strong sell", "underperform", "underweight", "negative",
    "market underperform", "sector underperform", "reduce",
}
_FIRM_NAMES = {
    "b of a securities": "BofA Securities",
    "bank of america securities": "BofA Securities",
    "jp morgan": "JPMorgan",
    "j.p. morgan": "JPMorgan",
    "keybanc": "KeyBanc",
}


def _sources(row: Mapping[str, Any] | Any) -> tuple[Mapping[str, Any], ...]:
    root = safe_mapping(row)
    if not root:
        return ()
    values = [root]
    for key in ("analyst_recommendation_counts", "raw", "Raw"):
        value = root.get(key)
        if isinstance(value, Mapping):
            values.append(value)
    return tuple(values)


def _first(row: Mapping[str, Any] | Any, *keys: str) -> Any:
    for source in _sources(row):
        for key in keys:
            if key not in source:
                continue
            value = source.get(key)
            # Containers are legitimate analyst evidence (notably the
            # canonical firm-action list).  Set membership is only safe for
            # scalar values; attempting it with a list raised the post-context
            # Research render TypeError seen by Runtime QA.
            if isinstance(value, (Mapping, list, tuple, set, frozenset)):
                if len(value) > 0:
                    return value
                continue
            if not is_missing_scalar(value):
                return value
    return None


def _count(row: Mapping[str, Any], *keys: str) -> int | None:
    value = number(_first(row, *keys))
    if value is None or value < 0:
        return None
    return int(value)


def _date(value: Any) -> datetime | None:
    # Provider schemas occasionally surface malformed container-shaped date
    # fields. They are unusable dates, but must fail closed without attempting
    # hash-based sentinel membership.
    if is_missing_scalar(value) or isinstance(value, (Mapping, list, tuple, set)):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    text = safe_scalar_display(value)
    return text or None


def _firm(value: Any) -> str | None:
    text = _text(value)
    return _FIRM_NAMES.get(text.lower(), text) if text else None


def _action_family(item: Mapping[str, Any]) -> str:
    rating_action = str(item.get("rating_action") or item.get("Action") or item.get("action") or "").strip().lower()
    target_action = str(item.get("target_action") or item.get("priceTargetAction") or "").strip().lower()
    current = str(item.get("current_rating") or item.get("ToGrade") or item.get("rating") or "").strip().lower()
    previous = str(item.get("previous_rating") or item.get("FromGrade") or "").strip().lower()
    if rating_action in {"up", "upgrade", "upgraded"}:
        return "UPGRADED"
    if rating_action in {"down", "downgrade", "downgraded"}:
        return "DOWNGRADED"
    if "raise" in target_action:
        return "TARGET RAISED"
    if "lower" in target_action or "cut" in target_action:
        return "TARGET LOWERED"
    if rating_action in {"init", "initiated", "initiation"}:
        return "INITIATED"
    if "maintain" in target_action:
        return "TARGET MAINTAINED"
    if rating_action in {"reit", "reiterate", "reiterated"} or (current and previous and current == previous):
        return "REITERATED"
    return "OTHER"


def normalize_analyst_actions(actions: Iterable[Mapping[str, Any]] | None, current_price: Any = None) -> list[dict[str, Any]]:
    """Normalize and deterministically deduplicate structured firm actions."""
    price = number(current_price)
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in actions or []:
        if not isinstance(source, Mapping):
            continue
        date_value = _date(source.get("date") or source.get("GradeDate") or source.get("publishedDate") or source.get("gradingDate"))
        firm = _firm(source.get("firm") or source.get("Firm") or source.get("brokerage") or source.get("company"))
        if date_value is None or not firm:
            continue
        current_target = number(source.get("current_target") if source.get("current_target") is not None else source.get("currentPriceTarget") if source.get("currentPriceTarget") is not None else source.get("priceTarget"))
        previous_target = number(source.get("previous_target") if source.get("previous_target") is not None else source.get("priorPriceTarget") if source.get("priorPriceTarget") is not None else source.get("previousPriceTarget"))
        # Provider zero represents an absent target in this action payload.
        current_target = current_target if current_target is not None and current_target > 0 else None
        previous_target = previous_target if previous_target is not None and previous_target > 0 else None
        current_rating = _text(source.get("current_rating") or source.get("ToGrade") or source.get("currentGrade") or source.get("rating") or source.get("newGrade"))
        previous_rating = _text(source.get("previous_rating") or source.get("FromGrade") or source.get("previousGrade"))
        rating_action = _text(source.get("rating_action") or source.get("Action") or source.get("action") or source.get("gradingAction"))
        target_action = _text(source.get("target_action") or source.get("priceTargetAction"))
        analyst_name = _text(source.get("analyst_name") or source.get("analyst"))
        key = semantic_identity((
            date_value.isoformat(), firm.lower(), current_rating, previous_rating,
            current_target, previous_target, rating_action, target_action,
        ))
        if key in seen:
            continue
        seen.add(key)
        original = dict(source)
        base = {
            "firm": firm,
            "analyst_name": analyst_name,
            "date": date_value.isoformat(),
            "current_rating": current_rating,
            "previous_rating": previous_rating,
            "current_target": current_target,
            "previous_target": previous_target,
            "rating_action": rating_action,
            "target_action": target_action,
        }
        family = _action_family({**original, **base})
        target_change = current_target - previous_target if current_target is not None and previous_target is not None else None
        target_change_pct = target_change / previous_target * 100 if target_change is not None and previous_target else None
        implied = (current_target / price - 1) * 100 if current_target is not None and price and price > 0 else None
        normalized.append({
            **base,
            "primary_action": family,
            "target_change": round(target_change, 2) if target_change is not None else None,
            "target_change_pct": round(target_change_pct, 1) if target_change_pct is not None else None,
            "current_price_implied_upside_pct": round(implied, 1) if implied is not None else None,
            "original_fields": original,
        })
    priority = {"UPGRADED": 0, "DOWNGRADED": 0, "TARGET RAISED": 1, "TARGET LOWERED": 1, "INITIATED": 2, "TARGET MAINTAINED": 3, "REITERATED": 4, "OTHER": 5}
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return sorted(normalized, key=lambda item: (-(_date(item["date"]) or epoch).timestamp(), priority[item["primary_action"]], item["firm"].lower()))


def recent_meaningful_actions(actions: Iterable[Mapping[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    values = [item for item in safe_sequence(actions) if isinstance(item, Mapping)]
    meaningful = [item for item in values if _text(item.get("primary_action")) not in {"TARGET MAINTAINED", "REITERATED", "OTHER"}]
    meaningful_ids = {semantic_identity(item) for item in meaningful}
    neutral = [item for item in values if semantic_identity(item) not in meaningful_ids]
    # Keep chronology inside each class while preventing a page of reiterations
    # from hiding recent directional evidence.
    selected = (meaningful + neutral)[: max(0, limit)]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return sorted(
        selected,
        key=lambda item: -(_date(item.get("date")) or epoch).timestamp(),
    )


def _trend(actions: Iterable[Mapping[str, Any]], days: int, now: datetime) -> dict[str, Any]:
    positive = negative = neutral = 0
    cutoff = now - timedelta(days=days)
    for item in actions:
        occurred = _date(item.get("date"))
        if occurred is None or occurred < cutoff or occurred > now:
            continue
        family = item.get("primary_action")
        rating = str(item.get("current_rating") or "").strip().lower()
        if family in {"TARGET RAISED", "UPGRADED"} or (family == "INITIATED" and rating in _BULLISH_RATINGS):
            positive += 1
        elif family in {"TARGET LOWERED", "DOWNGRADED"} or (family == "INITIATED" and rating in _BEARISH_RATINGS):
            negative += 1
        else:
            neutral += 1
    if positive == negative and positive > 0:
        classification = "MIXED"
    elif positive == 0 and negative == 0:
        classification = "STABLE"
    elif positive > 0 and negative == 0:
        classification = "IMPROVING"
    elif negative > 0 and positive == 0:
        classification = "DETERIORATING"
    elif positive >= 2 * negative:
        classification = "IMPROVING"
    elif negative >= 2 * positive:
        classification = "DETERIORATING"
    else:
        classification = "MIXED"
    return {"classification": classification, "positive": positive, "negative": negative, "neutral": neutral}


def _relationship(atlas_upside: float | None, street_upside: float | None, atlas: float | None, street: float | None) -> tuple[str, str]:
    if atlas is None and street is not None:
        return "ATLAS VALUE UNAVAILABLE", "Atlas has not published a canonical fair value; Wall Street consensus remains independent external evidence."
    if street is None and atlas is not None:
        return "WALL STREET CONSENSUS UNAVAILABLE", "Wall Street consensus is unavailable; Atlas Fair Value remains an independent internal valuation."
    if atlas is None and street is None:
        return "VALUATION COMPARISON UNAVAILABLE", "Neither canonical Atlas Fair Value nor Wall Street consensus is currently available."
    if atlas_upside is None or street_upside is None:
        return "VALUATION COMPARISON UNAVAILABLE", "The available values cannot be compared without a legitimate current price."
    if (atlas_upside < 0 < street_upside) or (street_upside < 0 < atlas_upside):
        return "MATERIAL DIVERGENCE", f"Atlas-FV implied upside is {atlas_upside:+.1f}% while Wall Street implied upside is {street_upside:+.1f}%."
    if abs(atlas_upside - street_upside) <= 10:
        return "BROADLY ALIGNED", f"Atlas-FV and Wall Street implied upside are within 10 percentage points ({atlas_upside:+.1f}% versus {street_upside:+.1f}%)."
    if atlas_upside > street_upside:
        return "ATLAS MORE CONSTRUCTIVE", f"Atlas-FV implied upside is {atlas_upside:+.1f}% versus Wall Street implied upside at {street_upside:+.1f}%."
    return "WALL STREET MORE CONSTRUCTIVE", f"Wall Street implied upside is {street_upside:+.1f}% versus Atlas-FV implied upside at {atlas_upside:+.1f}%."


def build_analyst_intelligence(row: Mapping[str, Any] | Any, *, actions: Iterable[Mapping[str, Any]] | None = None, now: datetime | None = None) -> dict[str, Any]:
    row = safe_mapping(row)
    current_price = number(_first(row, "current_price", "price", "Price", "Current Price"))
    mean = number(_first(row, "analyst_target_mean", "Analyst Target", "targetMeanPrice"))
    # Mean is deliberately never a median fallback.
    median = number(_first(row, "analyst_target_median", "Analyst Median", "targetMedianPrice"))
    high = number(_first(row, "analyst_target_high", "Analyst High", "targetHighPrice"))
    low = number(_first(row, "analyst_target_low", "Analyst Low", "targetLowPrice"))
    coverage = _count(row, "analyst_count", "Analyst Count", "numberOfAnalystOpinions")
    counts = {
        "strong_buy_count": _count(row, "strong_buy", "strong_buy_count", "strongBuy"),
        "buy_count": _count(row, "buy", "buy_count"),
        "hold_count": _count(row, "hold", "hold_count"),
        "sell_count": _count(row, "sell", "sell_count"),
        "strong_sell_count": _count(row, "strong_sell", "strong_sell_count", "strongSell"),
    }
    complete_mix = all(value is not None for value in counts.values())
    responses = sum(counts.values()) if complete_mix else None
    bullish = counts["strong_buy_count"] + counts["buy_count"] if complete_mix else None
    neutral = counts["hold_count"] if complete_mix else None
    bearish = counts["sell_count"] + counts["strong_sell_count"] if complete_mix else None
    pct = lambda value: round(value / responses * 100, 1) if value is not None and responses else None
    street_upside = (mean / current_price - 1) * 100 if mean is not None and current_price and current_price > 0 else None
    median_upside = (median / current_price - 1) * 100 if median is not None and current_price and current_price > 0 else None
    spread = high - low if high is not None and low is not None and high >= low else None
    dispersion = spread / mean * 100 if spread is not None and mean and mean > 0 else None
    agreement = None
    if dispersion is not None:
        agreement = "HIGH AGREEMENT" if dispersion <= HIGH_AGREEMENT_MAX else "MODERATE AGREEMENT" if dispersion <= MODERATE_AGREEMENT_MAX else "LOW AGREEMENT"
    source_actions = actions if actions is not None else _first(row, "analyst_actions", "upgrades_downgrades", "ratings_actions")
    normalized_actions = normalize_analyst_actions(source_actions if isinstance(source_actions, Iterable) and not isinstance(source_actions, (str, bytes, Mapping)) else [], current_price)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    atlas = canonical_atlas_fair_value(row)
    atlas_upside = number(_first(row, "atlas_fv_upside_pct", "Atlas FV Upside"))
    if atlas_upside is None and atlas is not None and current_price and current_price > 0:
        atlas_upside = (atlas / current_price - 1) * 100
    relationship, message = _relationship(atlas_upside, street_upside, atlas, mean)
    return {
        "current_price": current_price,
        "wall_street_mean_target": mean,
        "wall_street_median_target": median,
        "wall_street_high_target": high,
        "wall_street_low_target": low,
        "analyst_coverage": coverage,
        "wall_street_implied_upside_pct": round(street_upside, 1) if street_upside is not None else None,
        "wall_street_median_upside_pct": round(median_upside, 1) if median_upside is not None else None,
        **counts,
        "recommendation_response_count": responses,
        "bullish_count": bullish,
        "neutral_count": neutral,
        "bearish_count": bearish,
        "bullish_pct": pct(bullish),
        "neutral_pct": pct(neutral),
        "bearish_pct": pct(bearish),
        "target_spread": round(spread, 2) if spread is not None else None,
        "target_dispersion_pct": round(dispersion, 1) if dispersion is not None else None,
        "analyst_agreement": agreement,
        "recent_actions": recent_meaningful_actions(normalized_actions, 5),
        "all_actions": normalized_actions,
        "trend_30d": _trend(normalized_actions, 30, moment),
        "trend_90d": _trend(normalized_actions, 90, moment),
        "atlas_fair_value": atlas,
        "atlas_fv_upside_pct": round(atlas_upside, 1) if atlas_upside is not None else None,
        "atlas_street_relationship": relationship,
        "atlas_street_divergence_message": message,
    }


def grounded_analyst_context(intelligence: Mapping[str, Any]) -> dict[str, Any]:
    """Return only deterministic customer concepts safe for AI summarization."""
    keys = (
        "wall_street_mean_target", "wall_street_median_target", "wall_street_high_target",
        "wall_street_low_target", "analyst_coverage", "wall_street_implied_upside_pct",
        "wall_street_median_upside_pct", "strong_buy_count", "buy_count", "hold_count",
        "sell_count", "strong_sell_count", "recommendation_response_count", "bullish_count",
        "neutral_count", "bearish_count", "bullish_pct", "neutral_pct", "bearish_pct",
        "target_spread", "target_dispersion_pct", "analyst_agreement", "trend_30d",
        "trend_90d", "atlas_fair_value", "atlas_fv_upside_pct", "atlas_street_relationship",
        "atlas_street_divergence_message",
    )
    result = {key: intelligence.get(key) for key in keys}
    action_keys = (
        "firm", "date", "current_rating", "previous_rating", "current_target",
        "previous_target", "rating_action", "target_action", "primary_action",
        "target_change", "target_change_pct", "current_price_implied_upside_pct",
    )
    result["recent_actions"] = [
        {key: action.get(key) for key in action_keys}
        for action in intelligence.get("recent_actions") or []
    ]
    return result


__all__ = [
    "HIGH_AGREEMENT_MAX", "MODERATE_AGREEMENT_MAX", "build_analyst_intelligence",
    "normalize_analyst_actions", "recent_meaningful_actions", "grounded_analyst_context",
]
