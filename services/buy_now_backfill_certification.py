"""Bind completed history-backfill evidence to the existing BUY NOW certifier.

This module owns no scoring or publication logic.  It verifies the two durable
raw namespaces, appends licensed completed-session bars to the immutable
retained histories, and emits the canonical inputs expected by the existing
memory-bounded incremental certification bridge.
"""
from __future__ import annotations

import base64
from datetime import datetime, time, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from services.buy_now_history_backfill_execution import BackfillExecutor, digest, file_sha256
from services.buy_now_history_continuity import validate_backfill_observation_set
from services.finnhub_full_universe_executor import DailyBar, deserialize_bars, serialize_bars
from services.finnhub_incremental_post_close import (
    CHANGE_PROBE_FAMILY, PRICE_FAMILY, IncrementalCeiling, accept_receipt,
    build_incremental_plan, new_checkpoint, publication_readiness,
)


def _envelope(*, ordinal: int, original: Path, recovery: Path) -> tuple[dict[str, Any], Path]:
    candidates = [root / f"{ordinal:05d}.json" for root in (original, recovery)]
    found = [path for path in candidates if path.is_file()]
    if len(found) != 1:
        raise ValueError(f"BACKFILL_COMBINED_ENVELOPE_CARDINALITY_INVALID:{ordinal}:{len(found)}")
    return json.loads(found[0].read_text(encoding="utf-8")), found[0]


def combine_backfill_observations(
    *, plan: Mapping[str, Any], original_raw_dir: Path, recovery_raw_dir: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Validate and normalize every original request slot exactly once."""
    grouped: dict[str, dict[str, tuple[Mapping[str, Any], Path]]] = {}
    envelope_manifest = []
    for request in plan.get("requests") or ():
        ordinal = int(request["ordinal"])
        envelope, path = _envelope(
            ordinal=ordinal, original=original_raw_dir, recovery=recovery_raw_dir,
        )
        if envelope.get("ordinal") != ordinal or envelope.get("request_sha256") != digest(request):
            raise ValueError(f"BACKFILL_COMBINED_REQUEST_IDENTITY_INVALID:{ordinal}")
        encoded = str(envelope.get("body_base64") or "")
        try:
            raw_body = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError(f"BACKFILL_COMBINED_BODY_ENCODING_INVALID:{ordinal}") from exc
        if hashlib.sha256(raw_body).hexdigest() != envelope.get("body_sha256"):
            raise ValueError(f"BACKFILL_COMBINED_BODY_DIGEST_INVALID:{ordinal}")
        BackfillExecutor._validate_response(request, envelope)
        ticker, capability = str(request["ticker"]), str(request["capability"])
        if capability in grouped.setdefault(ticker, {}):
            raise ValueError(f"BACKFILL_COMBINED_CAPABILITY_DUPLICATE:{ticker}:{capability}")
        grouped[ticker][capability] = (envelope, path)
        envelope_manifest.append([ordinal, file_sha256(path)])

    observations: dict[str, list[dict[str, Any]]] = {}
    unavailable: dict[str, dict[str, Any]] = {}
    wanted = list(plan.get("missing_sessions") or ())
    for ticker in sorted(grouped):
        capabilities = grouped[ticker]
        if set(capabilities) != {"historical_ohlcv", "splits", "dividends"}:
            raise ValueError(f"BACKFILL_COMBINED_CAPABILITY_SET_INVALID:{ticker}")
        candle, candle_path = capabilities["historical_ohlcv"]
        split, split_path = capabilities["splits"]
        dividend, dividend_path = capabilities["dividends"]
        candle_body = json.loads(base64.b64decode(candle["body_base64"]))
        split_body = json.loads(base64.b64decode(split["body_base64"]))
        dividend_body = json.loads(base64.b64decode(dividend["body_base64"]))
        if candle_body == {"s": "no_data"}:
            unavailable[ticker] = {
                "reason": "FINNHUB_NO_DATA", "requested_sessions": wanted,
                "raw_response_sha256": file_sha256(candle_path),
            }
            continue
        sessions = [datetime.fromtimestamp(int(value), timezone.utc).date().isoformat()
                    for value in candle_body["t"]]
        if sessions != wanted:
            raise ValueError(f"BACKFILL_COMBINED_SESSION_SET_INVALID:{ticker}")
        lineage = hashlib.sha256(
            (file_sha256(candle_path) + file_sha256(split_path) + file_sha256(dividend_path)).encode()
        ).hexdigest()
        action_status = "PRESENT" if split_body or dividend_body else "NONE"
        observations[ticker] = [{
            "session": session, "open": candle_body["o"][index],
            "high": candle_body["h"][index], "low": candle_body["l"][index],
            "close": candle_body["c"][index], "volume": candle_body["v"][index],
            "raw_response_sha256": lineage, "corporate_action_status": action_status,
        } for index, session in enumerate(sessions)]

    validation = validate_backfill_observation_set(
        plan=plan, observations=observations, unavailable=unavailable,
    )
    validation["combined_envelope_manifest_sha256"] = digest(envelope_manifest)
    validation["combined_request_count"] = len(envelope_manifest)
    return observations, unavailable, validation


def build_certification_inputs(
    *, backfill_plan: Mapping[str, Any], retained_rows: Sequence[Mapping[str, Any]],
    retained_histories: Mapping[str, Sequence[Mapping[str, Any]]],
    observations: Mapping[str, Sequence[Mapping[str, Any]]],
    unavailable: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Create canonical memory-bounded certifier inputs without transport."""
    symbols = sorted({str(request["ticker"]).upper() for request in backfill_plan["requests"]})
    membership = dict(backfill_plan.get("membership_identity") or {})
    membership["tickers"] = symbols
    plan = build_incremental_plan(
        session=str(backfill_plan["range_end"]), customer_symbols=symbols,
        governed_membership=membership,
        ceiling=IncrementalCeiling(customer_symbols=len(symbols), changed_fundamental_symbols=0),
    )
    checkpoint = new_checkpoint(plan=plan)
    lineage_by_symbol = {
        symbol: digest(list(observations.get(symbol) or ()) or unavailable.get(symbol) or {})
        for symbol in symbols
    }
    for key in plan["request_keys"]:
        session, symbol, family = key.split(":", 2)
        checkpoint = accept_receipt(plan=plan, checkpoint=checkpoint, receipt={
            "request_key": key, "session": session, "symbol": symbol,
            "family": family, "status": "AVAILABLE",
            "raw_path": f"combined-backfill/{symbol}/{family}.json",
            "raw_sha256": lineage_by_symbol[symbol],
        })
    readiness = publication_readiness(plan=plan, checkpoint=checkpoint)
    retained = {str(row.get("ticker") or "").upper(): dict(row) for row in retained_rows}
    if sorted(retained) != symbols or sorted(retained_histories) != symbols:
        raise ValueError("BACKFILL_CERTIFICATION_RETAINED_MEMBERSHIP_MISMATCH")
    records = []
    for symbol in symbols:
        bars = deserialize_bars(retained_histories[symbol])
        blockers: list[str] = []
        if symbol in unavailable:
            blockers.append("BACKFILL_TERMINAL_FINNHUB_NO_DATA")
        else:
            for item in observations[symbol]:
                timestamp = datetime.combine(
                    datetime.fromisoformat(str(item["session"])).date(), time(23, 59, 59),
                    tzinfo=timezone.utc,
                )
                bars.append(DailyBar(
                    symbol, timestamp, float(item["open"]), float(item["high"]),
                    float(item["low"]), float(item["close"]), float(item["volume"]), True,
                ))
            if any(left.timestamp >= right.timestamp for left, right in zip(bars, bars[1:])):
                raise ValueError(f"BACKFILL_CERTIFICATION_HISTORY_ORDER_INVALID:{symbol}")
        if len(bars) < 200:
            blockers.append("INCREMENTAL_TECHNICAL_HISTORY_INSUFFICIENT")
        row = retained[symbol]
        if symbol not in unavailable:
            row["current_price"] = row["price"] = bars[-1].close
            row["historical_ohlcv_evidence_id"] = lineage_by_symbol[symbol]
        keys = [key for key in plan["request_keys"] if f":{symbol}:" in key]
        records.append({
            "ticker": symbol, "row": row, "bars": serialize_bars(bars),
            "blockers": blockers, "credential_entitlement_failures": 0,
            "security_master": {}, "analytical_inputs": {},
            "shadow_evidence_leakage": False, "authority_violations": 0,
            "incremental_receipt_keys": sorted(keys),
            "incremental_receipt_set_sha256": readiness["receipt_set_sha256"],
            "normalization_method": "EXISTING_FINNHUB_CANONICAL_NORMALIZER",
        })
    return plan, checkpoint, records


__all__ = ["build_certification_inputs", "combine_backfill_observations"]
