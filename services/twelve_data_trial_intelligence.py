"""Explicit INTERNAL_TRIAL Twelve intelligence acquisition.

This context is non-scoring.  Canonical ATLAS values always win and raw
provider payloads are retained behind evidence envelopes for later mapping.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import time
from typing import Any, Callable, Mapping, Sequence

import requests

from services.data_mode_policy import internal_trial_mode
from services.live_market.twelve_data_phase1 import REST_BASE, load_twelve_data_setting, normalize_ticker


VERSION = "TWELVE_DATA_INTERNAL_TRIAL_INTELLIGENCE_V1"
ENDPOINTS = (
    "profile", "statistics", "income_statement", "balance_sheet", "cash_flow",
    "earnings", "earnings_estimate", "revenue_estimate", "price_target",
    "insider_transactions", "institutional_holders", "press_releases",
)


def _evidence_id(symbol: str, family: str, observed: str) -> str:
    digest = hashlib.sha256(f"{symbol}|{family}|{observed}".encode()).hexdigest()[:20]
    return f"TDTRIAL-{digest}"


def acquire_twelve_trial_dossiers(
    symbols: Sequence[str], *, get: Callable[..., Any] = requests.get,
    secrets: Mapping[str, Any] | None = None, environ: Mapping[str, str] | None = None,
    max_workers: int = 6, timeout: float = 12,
) -> dict[str, Any]:
    if not internal_trial_mode(environ=environ, secrets=secrets):
        return {"version": VERSION, "status": "DISABLED", "dossiers": {}, "provider_calls": 0}
    key = load_twelve_data_setting("TWELVE_DATA_API_KEY", secrets=secrets, environ=environ)
    if not key:
        return {"version": VERSION, "status": "DATA_UNAVAILABLE", "dossiers": {}, "provider_calls": 0, "reason_codes": ("TWELVE_DATA_API_KEY_UNAVAILABLE",)}
    observed = datetime.now(timezone.utc).isoformat()
    clean = tuple(dict.fromkeys(normalize_ticker(symbol) for symbol in symbols))
    dossiers = {symbol: {"ticker": symbol, "families": {}} for symbol in clean}
    telemetry = []

    def fetch(symbol: str, family: str) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        started = time.monotonic()
        try:
            response = get(f"{REST_BASE}/{family}", params={"symbol": symbol}, headers={"Authorization": f"apikey {key}"}, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            error = isinstance(payload, Mapping) and str(payload.get("status") or "").lower() == "error"
            envelope = {
                "status": "DATA_UNAVAILABLE" if error else "AVAILABLE", "provider": "TWELVE_DATA",
                "endpoint": family, "observed_at": observed,
                "evidence_id": _evidence_id(symbol, family, observed),
                "payload": payload if not error else None,
                "reason_codes": ("PROVIDER_ERROR",) if error else (),
            }
            meta = {"ticker": symbol, "endpoint": family, "success": not error, "latency_seconds": round(time.monotonic()-started, 3)}
            return symbol, family, envelope, meta
        except Exception as exc:
            return symbol, family, {"status": "DATA_UNAVAILABLE", "provider": "TWELVE_DATA", "endpoint": family, "observed_at": observed, "evidence_id": _evidence_id(symbol, family, observed), "payload": None, "reason_codes": (type(exc).__name__.upper(),)}, {"ticker": symbol, "endpoint": family, "success": False, "latency_seconds": round(time.monotonic()-started, 3)}

    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as pool:
        futures = [pool.submit(fetch, symbol, family) for symbol in clean for family in ENDPOINTS]
        for future in as_completed(futures):
            symbol, family, envelope, meta = future.result()
            dossiers[symbol]["families"][family] = envelope
            telemetry.append(meta)
    successes = sum(item["success"] for item in telemetry)
    for dossier in dossiers.values():
        dossier["evidence_ids"] = tuple(item["evidence_id"] for item in dossier["families"].values() if item["status"] == "AVAILABLE")
    return {
        "version": VERSION, "status": "AVAILABLE" if successes else "DATA_UNAVAILABLE",
        "dossiers": dossiers, "provider_calls": len(telemetry), "successful_calls": successes,
        "success_rate": successes / len(telemetry) if telemetry else 0,
        "latency_seconds": {"total": round(sum(item["latency_seconds"] for item in telemetry), 3), "max": max((item["latency_seconds"] for item in telemetry), default=0)},
        "endpoint_success": {family: sum(item["success"] for item in telemetry if item["endpoint"] == family) for family in ENDPOINTS},
        "observed_at": observed,
    }


__all__ = ["ENDPOINTS", "VERSION", "acquire_twelve_trial_dossiers"]
