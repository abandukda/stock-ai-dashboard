"""Provider-free, evidence-bound Home market intelligence projection."""
from __future__ import annotations

from typing import Any, Mapping


CONTRACT = "ATLAS_HOME_MARKET_INTELLIGENCE_V1"


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _seq(value: Any) -> tuple[Any, ...]:
    return tuple(value) if isinstance(value, (list, tuple)) else ()


def build_home_market_intelligence(story: Mapping[str, Any]) -> dict[str, Any]:
    """Admit only dated market context already accepted by the Home story."""
    context = _map(story.get("market_today"))
    instruments = tuple(
        dict(item) for item in _seq(context.get("instruments"))
        if isinstance(item, Mapping) and item.get("symbol") and item.get("price") is not None
    )
    macro = tuple(
        dict(item) for item in _seq(context.get("official_macro_evidence"))
        if isinstance(item, Mapping) and item.get("agency_label") and item.get("source_url")
        and item.get("observation_period")
    )
    news = tuple(
        dict(item) for item in _seq(context.get("major_market_news"))
        if isinstance(item, Mapping) and item.get("headline") and item.get("source") and item.get("published_at")
    )
    sectors = tuple(
        dict(item) for item in _seq(context.get("sector_performance"))
        if isinstance(item, Mapping) and item.get("sector") and item.get("change_pct") is not None
        and item.get("as_of")
    )
    events = tuple(
        dict(item) for item in _seq(context.get("upcoming_events"))
        if isinstance(item, Mapping) and item.get("label") and item.get("scheduled_at") and item.get("source")
    )
    analogues = []
    for raw in _seq(context.get("historical_analogues")):
        item = _map(raw)
        if not (
            item.get("criteria") and item.get("sample_size") and item.get("observation_window")
            and item.get("outcome_dispersion") and item.get("source_evidence_ids")
        ):
            continue
        analogues.append(dict(item))
    interpretation = str(context.get("interpretation") or "").strip()
    as_of = context.get("as_of") or story.get("scan_timestamp")
    status = "AVAILABLE" if as_of and (instruments or macro or news) else "LIMITED" if as_of else "UNAVAILABLE"
    return {
        "contract": CONTRACT, "status": status, "as_of": as_of,
        "market_session": context.get("market_session") or "UNAVAILABLE",
        "classification": "CONTEXTUAL_NON_SCORING", "external_model_active": False,
        "indices": instruments, "sectors": sectors, "macro": macro, "news": news, "events": events,
        "interpretation": interpretation or "ATLAS is not inferring a market backdrop without governed evidence.",
        "regime": context.get("market_regime") if context.get("market_regime_evidence_ids") else None,
        "regime_limitation": None if context.get("market_regime_evidence_ids") else
            "A source-bound market-regime observation is unavailable.",
        "historical_analogues": tuple(analogues),
        "analogue_limitation": None if analogues else
            "No reproducible historical analogue with criteria, sample size, window, dispersion, and source evidence is available.",
        "watchpoints": tuple(str(item).strip() for item in _seq(context.get("conditional_watchpoints")) if str(item).strip())[:4],
        "limitations": tuple(item for item in (
            None if instruments else "Verified index context is unavailable.",
            None if sectors else "Verified sector performance is unavailable.",
            None if events else "Verified upcoming market events are unavailable.",
        ) if item),
    }


__all__ = ["CONTRACT", "build_home_market_intelligence"]
