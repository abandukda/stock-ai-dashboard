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
    events, websocket_meta = _websocket_events(symbols, api_key, wait_seconds=DEFAULT_WS_WAIT_SECONDS, connector=connector)
    evaluations: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    provider_calls = 1
    for row in rows:
        ticker_started = time.monotonic()
        symbol = _ticker(row)
        event, received = events.get(symbol, ({}, now or datetime.now(timezone.utc)))
        try:
            payload = adapter.fetch_time_series(symbol)
            provider_calls += 1
            bundle = build_phase1_bundle(
                symbol, websocket_event=event, time_series_payload=payload,
                received_timestamp=received, now=now, policy=policy,
            )
            evaluation = evaluate_on_demand(
                row, context={"production_decision": build_production_decision(row), "evidence_registry": {}},
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
            evaluations[symbol] = evaluation
            diagnostics[symbol] = {
                "current_price_status": bundle["current_price"]["status"],
                "completed_bar_status": bundle["completed_bars"]["status"],
                "volume_status": bundle["intraday_volume"]["status"],
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
    return {
        "version": HOME_PHASE1_VERSION,
        "status": "AVAILABLE" if evaluations else "DATA_UNAVAILABLE",
        "evaluations": evaluations, "diagnostics": diagnostics,
        "websocket": websocket_meta, "provider_calls": provider_calls,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "captured_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


__all__ = ["HOME_PHASE1_VERSION", "acquire_home_phase1_evaluations"]
