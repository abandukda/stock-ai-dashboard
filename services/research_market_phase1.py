"""Post-shell Twelve Data market/chart enrichment for explicit Research."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import requests

from services.canonical_market_snapshot import build_market_snapshot
from services.home_live_market_phase1 import _websocket_events
from services.live_market.twelve_data_phase1 import (
    Phase1Policy, build_adapter_if_enabled, build_phase1_bundle,
    load_twelve_data_setting, twelve_data_enabled,
)
from services.on_demand_evaluation_service import evaluate_on_demand


RESEARCH_MARKET_PHASE1_VERSION = "RESEARCH_TWELVE_DATA_PHASE1_V1"


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _newest_existing(row: Mapping[str, Any]) -> datetime | None:
    history = next((row.get(key) for key in (
        "price_history", "historical_prices", "chart_data", "historical_data",
    ) if isinstance(row.get(key), list) and row.get(key)), [])
    stamps = [
        _timestamp(item.get("timestamp") or item.get("datetime") or item.get("date"))
        for item in history if isinstance(item, Mapping)
    ]
    return max((stamp for stamp in stamps if stamp), default=None)


def apply_research_phase1(row: Mapping[str, Any], bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Attach canonical evidence without changing persisted overlay authorities."""
    output = dict(row)
    current = bundle.get("current_price") if isinstance(bundle.get("current_price"), Mapping) else {}
    last_known = bundle.get("last_known_market") if isinstance(bundle.get("last_known_market"), Mapping) else {}
    source = current if current.get("status") == "AVAILABLE" else last_known
    market = build_market_snapshot(str(output.get("ticker") or output.get("Ticker") or ""), source)
    output["canonical_market_snapshot"] = market
    if current.get("status") == "AVAILABLE":
        output.update({
            "current_price": current.get("price"),
            "price_as_of": current.get("provider_timestamp"),
            "quote_timestamp": current.get("provider_timestamp"),
            "quote_source": "Twelve Data WebSocket",
            "market_status": current.get("market_session"),
        })

    completed = bundle.get("completed_bars") if isinstance(bundle.get("completed_bars"), Mapping) else {}
    bars = [dict(bar) for bar in completed.get("bars") or () if isinstance(bar, Mapping) and bar.get("completed")]
    newest = _timestamp((completed.get("latest_completed_bar") or {}).get("timestamp"))
    existing_newest = _newest_existing(output)
    use_twelve = bool(bars and newest and (existing_newest is None or newest > existing_newest))
    chart_contract = {
        "ticker": completed.get("ticker"), "provider": completed.get("provider"),
        "range": "LATEST_1MIN_WINDOW", "interval": "1min", "adjustment_mode": "splits",
        "extended_hours_included": True, "bars": bars,
        "newest_bar_timestamp": (completed.get("bars") or [{}])[-1].get("timestamp") if completed.get("bars") else None,
        "newest_completed_bar_timestamp": newest.isoformat() if newest else None,
        "session": (completed.get("latest_completed_bar") or {}).get("session"),
        "quality_status": completed.get("status"), "gap_status": "GAPS_PRESENT" if completed.get("gap_metadata") else "NO_GAPS_DETECTED",
        "gap_metadata": completed.get("gap_metadata") or (), "evidence_id": completed.get("evidence_id"),
    }
    output["canonical_chart_contract"] = chart_contract
    daily = bundle.get("canonical_technical_history") if isinstance(bundle.get("canonical_technical_history"), Mapping) else {}
    daily_bars = [dict(bar) for bar in daily.get("bars") or () if isinstance(bar, Mapping)]
    output["canonical_chart_ranges"] = {
        "1D": {**chart_contract, "range": "1D", "bars": bars[-960:]},
        "5D": {**chart_contract, "range": "5D", "bars": bars[-5000:]},
        "1M": {**dict(daily), "range": "1M", "bars": daily_bars[-23:]},
        "3M": {**dict(daily), "range": "3M", "bars": daily_bars[-66:]},
        "6M": {**dict(daily), "range": "6M", "bars": daily_bars[-132:]},
        "1Y": {**dict(daily), "range": "1Y", "bars": daily_bars[-260:]},
    }
    if use_twelve:
        output["price_history"] = bars
        output["history_provenance"] = {
            "status": completed.get("status"), "provider_called": True,
            "provider_success": True, "records_found": len(bars), "mapping_success": True,
            "source": "Twelve Data /time_series", "provider": completed.get("provider"),
            "range": chart_contract["range"], "interval": "1min", "adjustment_mode": "splits",
            "extended_hours_included": True, "as_of": chart_contract["newest_completed_bar_timestamp"],
            "newest_bar_timestamp": chart_contract["newest_bar_timestamp"],
            "newest_completed_bar_timestamp": chart_contract["newest_completed_bar_timestamp"],
            "session": chart_contract["session"], "gap_status": chart_contract["gap_status"],
            "quality_status": chart_contract["quality_status"], "evidence_id": chart_contract["evidence_id"],
            "retrieval_status": "fresh_approved_twelve_evidence", "cache_status": "none", "error": "",
        }
    context = dict(output.get("research_context") or {})
    evaluation = evaluate_on_demand(output, context=context, twelve_data_phase1=bundle, phase1_enabled=True)
    context["current_evaluation"] = evaluation
    output["research_context"] = context
    output["canonical_technical"] = dict(evaluation.get("technical_confirmation") or {})
    output["canonical_guidance"] = dict(evaluation.get("guidance") or {})
    output["canonical_actionability"] = dict(evaluation.get("actionability") or {})
    from engines.home_guidance_story_v1 import build_home_guidance_candidate
    from services.atlas_view_summary import build_summary_payload, generate_summaries
    card = build_home_guidance_candidate(
        output, production_rank=int(output.get("production_rank") or output.get("rank") or 0),
        recovery_row=output.get("canonical_recovery_row") if isinstance(output.get("canonical_recovery_row"), Mapping) else None,
        current_evaluation=evaluation,
    )
    summary = generate_summaries([build_summary_payload(card)])[0]
    evaluation["atlas_ai_view"] = summary
    context["current_evaluation"] = evaluation
    output["atlas_ai_view"] = summary
    return output


def acquire_research_phase1(
    ticker: str, *, now: datetime | None = None, policy: Phase1Policy | None = None,
    get: Callable[..., Any] = requests.get, connector: Callable[..., Any] | None = None,
    secrets: Mapping[str, Any] | None = None, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Make one bounded single-symbol WebSocket cohort and one REST request."""
    symbol = str(ticker or "").strip().upper()
    if not symbol or not twelve_data_enabled(secrets=secrets, environ=environ):
        return {"version": RESEARCH_MARKET_PHASE1_VERSION, "status": "DISABLED", "bundle": {}}
    try:
        adapter = build_adapter_if_enabled(get=get, secrets=secrets, environ=environ)
        key = load_twelve_data_setting("TWELVE_DATA_API_KEY", secrets=secrets, environ=environ)
        if adapter is None:
            raise RuntimeError("TWELVE_DATA_ADAPTER_UNAVAILABLE")
        events, websocket = _websocket_events([symbol], key, wait_seconds=7.0, connector=connector)
        event, received = events.get(symbol, ({}, now or datetime.now(timezone.utc)))
        minute_payload = adapter.fetch_time_series(symbol, outputsize=5000)
        daily_payload = adapter.fetch_time_series(symbol, interval="1day", outputsize=260, prepost=False)
        bundle = build_phase1_bundle(
            symbol, websocket_event=event, time_series_payload=minute_payload,
            daily_time_series_payload=daily_payload,
            received_timestamp=received, now=now, policy=policy,
        )
        return {"version": RESEARCH_MARKET_PHASE1_VERSION, "status": "AVAILABLE", "bundle": bundle, "websocket": websocket}
    except Exception as exc:
        return {"version": RESEARCH_MARKET_PHASE1_VERSION, "status": "DATA_UNAVAILABLE", "bundle": {}, "reason_codes": (type(exc).__name__.upper(),)}


__all__ = ["RESEARCH_MARKET_PHASE1_VERSION", "acquire_research_phase1", "apply_research_phase1"]
