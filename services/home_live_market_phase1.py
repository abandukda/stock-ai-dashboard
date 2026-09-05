"""Bounded post-shell Twelve Data enrichment for Home Guidance.

This module is the only customer-route acquisition seam for Phase 1. It never
uses /quote, never publishes volume authority, and is called only after Home's
PAGE_INTERACTIVE marker has been emitted.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import ssl
import time
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

import requests

from engines.research_context import build_production_decision
from services.live_market.twelve_data_phase1 import (
    Phase1Policy, build_adapter_if_enabled, build_phase1_bundle,
    load_twelve_data_setting, normalize_websocket_price, twelve_data_enabled,
)
from services.on_demand_evaluation_service import evaluate_on_demand


HOME_PHASE1_VERSION = "HOME_TWELVE_DATA_PHASE1_V1"
WS_BASE = "wss://ws.twelvedata.com/v1/quotes/price"
DEFAULT_MAX_SYMBOLS = 10
DEFAULT_WS_WAIT_SECONDS = 7.0


def _ticker(row: Mapping[str, Any]) -> str:
    return str(row.get("ticker") or row.get("Ticker") or row.get("symbol") or "").strip().upper()


def _rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("rows", "results", "data"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, Mapping)]
    return []


def _websocket_events(
    symbols: Sequence[str], api_key: str, *, wait_seconds: float,
    connector: Callable[..., Any] | None = None,
) -> tuple[dict[str, tuple[Mapping[str, Any], datetime]], dict[str, Any]]:
    """Collect at most one validated candidate event per exact symbol."""
    if not symbols:
        return {}, {"status": "DATA_UNAVAILABLE", "reason_codes": ("NO_SYMBOLS",)}
    if connector is None:
        import certifi
        from websockets.sync.client import connect
        connector = connect
        tls_context = ssl.create_default_context(cafile=certifi.where())
    else:
        tls_context = None
    found: dict[str, tuple[Mapping[str, Any], datetime]] = {}
    started = time.monotonic()
    try:
        with connector(
            f"{WS_BASE}?apikey={api_key}", open_timeout=min(wait_seconds, 5),
            close_timeout=2, ssl=tls_context,
        ) as socket:
            socket.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(symbols)}}))
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline and len(found) < len(symbols):
                try:
                    message = socket.recv(timeout=max(.1, deadline - time.monotonic()))
                    payload = json.loads(message)
                except TimeoutError:
                    break
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                events = payload if isinstance(payload, list) else [payload]
                for event in events:
                    if not isinstance(event, Mapping):
                        continue
                    symbol = str(event.get("symbol") or "").upper()
                    if symbol in symbols and event.get("price") is not None:
                        found[symbol] = (dict(event), datetime.now(timezone.utc))
        return found, {
            "status": "AVAILABLE" if found else "DATA_UNAVAILABLE",
            "symbols_requested": len(symbols), "symbols_received": len(found),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    except Exception as exc:
        return {}, {
            "status": "DATA_UNAVAILABLE", "symbols_requested": len(symbols),
            "symbols_received": 0, "elapsed_seconds": round(time.monotonic() - started, 3),
            "reason_codes": (f"WEBSOCKET_{type(exc).__name__.upper()}",),
        }


def acquire_home_phase1_evaluations(
    full_scan_payload: Any, *, max_symbols: int = DEFAULT_MAX_SYMBOLS,
    now: datetime | None = None, policy: Phase1Policy | None = None,
    get: Callable[..., Any] = requests.get, connector: Callable[..., Any] | None = None,
    secrets: Mapping[str, Any] | None = None, environ: Mapping[str, str] | None = None,
    daily_history_cache: Mapping[str, Mapping[str, Any]] | None = None,
    recovery_payload: Any = None,
    latest_completed_session_only: bool = False,
    trial_dossiers: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Acquire a small Home cohort; failures return evidence, never exceptions."""
    started = time.monotonic()
    if not twelve_data_enabled(secrets=secrets, environ=environ):
        return {"version": HOME_PHASE1_VERSION, "status": "DISABLED", "evaluations": {}, "provider_calls": 0}
    rows = _rows(full_scan_payload)[:max(0, int(max_symbols))]
    symbols = [_ticker(row) for row in rows if _ticker(row)]
    try:
        adapter = build_adapter_if_enabled(get=get, secrets=secrets, environ=environ)
        api_key = load_twelve_data_setting("TWELVE_DATA_API_KEY", secrets=secrets, environ=environ)
        if adapter is None:
            raise RuntimeError("TWELVE_DATA_ADAPTER_UNAVAILABLE")
    except Exception as exc:
        return {
            "version": HOME_PHASE1_VERSION, "status": "DATA_UNAVAILABLE", "evaluations": {},
            "provider_calls": 0, "reason_codes": (type(exc).__name__.upper(),),
        }
    events, websocket_meta = (
        ({}, {"status": "NOT_REQUIRED", "reason_codes": ("LATEST_COMPLETED_SESSION_MODE",)})
        if latest_completed_session_only
        else _websocket_events(symbols, api_key, wait_seconds=DEFAULT_WS_WAIT_SECONDS, connector=connector)
    )
    evaluations: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    history_cache = {str(key): dict(value) for key, value in (daily_history_cache or {}).items()}
    provider_calls = 0 if latest_completed_session_only else 1
    for row in rows:
        ticker_started = time.monotonic()
        symbol = _ticker(row)
        evaluation_row = row
        dossier = (trial_dossiers or {}).get(symbol)
        if dossier:
            from services.twelve_data_trial_intelligence import normalize_trial_dossier
            evaluation_row = normalize_trial_dossier(row, dossier)
        event, received = events.get(symbol, ({}, now or datetime.now(timezone.utc)))
        try:
            payload = {} if latest_completed_session_only else adapter.fetch_time_series(symbol)
            provider_calls += 0 if latest_completed_session_only else 1
            cache_day = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York")).date().isoformat()
            cache_key = f"{symbol}|TWELVE_DATA|1Y|1day|REGULAR|splits|BULL_RUN_RADAR_V1_PROVISIONAL|{cache_day}"
            daily_payload = history_cache.get(cache_key)
            if daily_payload is None:
                daily_payload = dict(adapter.fetch_time_series(symbol, interval="1day", outputsize=260, prepost=False))
                history_cache[cache_key] = daily_payload
                provider_calls += 1
            bundle = build_phase1_bundle(
                symbol, websocket_event=event, time_series_payload=payload,
                daily_time_series_payload=daily_payload,
                received_timestamp=received, now=now, policy=policy,
            )
            evaluation = evaluate_on_demand(
                evaluation_row, context={"production_decision": build_production_decision(row), "evidence_registry": {}},
                twelve_data_phase1=bundle, phase1_enabled=True,
            )
            # Presentation evidence only; excluded from canonical technical,
            # volume, valuation, Guidance, and Actionability calculations.
            evaluation["phase1_completed_bar"] = dict(bundle["completed_bars"].get("latest_completed_bar") or {})
            evaluation["phase1_bar_quality"] = {
                "status": bundle["completed_bars"].get("status"),
                "reason_codes": tuple(bundle["completed_bars"].get("reason_codes") or ()),
                "gap_metadata": tuple(bundle["completed_bars"].get("gap_metadata") or ()),
                "evidence_id": bundle["completed_bars"].get("evidence_id"),
            }
            daily_history = bundle.get("canonical_technical_history") or {}
            evaluation["phase1_home_chart"] = {
                "status": daily_history.get("status"),
                "ranges": ("1M", "3M", "1Y"),
                "interval": daily_history.get("interval"),
                "adjustment_mode": daily_history.get("adjustment_mode"),
                "extended_hours_included": daily_history.get("extended_hours_included"),
                "provider": daily_history.get("provider"),
                "newest_completed_bar_timestamp": daily_history.get("newest_completed_bar_timestamp"),
                "evidence_id": daily_history.get("evidence_id"),
                "bars": tuple(daily_history.get("bars") or ())[-260:],
            }
            if dossier:
                evaluation["trial_intelligence"] = dict(dossier)
                evaluation["trial_presentation_fields"] = {
                    key: evaluation_row.get(key) for key in (
                        "description", "sector", "industry", "revenue_growth", "earnings_growth",
                        "operating_profit_margin", "free_cash_flow", "current_ratio", "latest_revenue",
                        "latest_operating_income", "operating_cash_flow", "total_debt", "cash_and_equivalents",
                        "forward_eps", "forward_revenue",
                    ) if evaluation_row.get(key) is not None
                }
            evaluations[symbol] = evaluation
            diagnostics[symbol] = {
                "current_price_status": bundle["current_price"]["status"],
                "completed_bar_status": bundle["completed_bars"]["status"],
                "technical_history_status": bundle["canonical_technical_history"]["status"],
                "volume_status": bundle["completed_daily_volume"]["status"],
                "volume_relative": bundle["completed_daily_volume"].get("relative_volume"),
                "guidance": evaluation["guidance"]["state"],
                "actionability": evaluation["actionability"]["status"],
                "reason_codes": evaluation["guidance"]["reason_codes"],
                "elapsed_seconds": round(time.monotonic() - ticker_started, 3),
            }
        except Exception as exc:
            diagnostics[symbol] = {
                "status": "DATA_UNAVAILABLE", "reason_codes": (type(exc).__name__.upper(),),
                "elapsed_seconds": round(time.monotonic() - ticker_started, 3),
            }
    if evaluations:
        from engines.home_guidance_story_v1 import build_home_guidance_story
        from services.atlas_view_summary import build_summary_payload, generate_summaries
        summary_story = build_home_guidance_story(
            rows, recovery_payload or [], current_evaluations=evaluations,
        )
        summary_cards = summary_story.get("cards") or []
        summaries = generate_summaries([build_summary_payload(card) for card in summary_cards])
        for card, summary in zip(summary_cards, summaries):
            symbol = str(card.get("ticker") or "")
            if symbol in evaluations:
                evaluations[symbol]["atlas_ai_view"] = summary
    return {
        "version": HOME_PHASE1_VERSION,
        "status": "AVAILABLE" if evaluations else "DATA_UNAVAILABLE",
        "evaluations": evaluations, "diagnostics": diagnostics,
        "websocket": websocket_meta, "provider_calls": provider_calls,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "captured_at": (now or datetime.now(timezone.utc)).isoformat(),
        "daily_history_cache": history_cache,
    }


__all__ = ["HOME_PHASE1_VERSION", "acquire_home_phase1_evaluations"]
