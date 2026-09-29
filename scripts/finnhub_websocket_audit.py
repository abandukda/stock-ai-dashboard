#!/usr/bin/env python3
"""Bounded, non-production Finnhub WebSocket contract audit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any


VERSION = "FINNHUB_WEBSOCKET_BOUNDED_AUDIT_V1"
URL = "wss://ws.finnhub.io"


def classify_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for message in messages for row in (message.get("data") or []) if isinstance(row, dict)]
    return {
        "message_count": len(messages), "event_count": len(rows),
        "event_types": sorted({str(row.get("type")) for row in rows if row.get("type") is not None}),
        "symbols": sorted({str(row.get("s")) for row in rows if row.get("s")}),
        "timestamps_present": bool(rows) and all(row.get("t") is not None for row in rows),
        "venues_present": bool(rows) and all(row.get("venue") is not None for row in rows),
        "duplicate_event_count": len(rows) - len({json.dumps(row, sort_keys=True) for row in rows}),
        "suitability": "LIVE_DISPLAY" if rows else "NOT_CERTIFIED",
        "scoring_allowed": False,
    }


def run(symbols: list[str], seconds: float) -> dict[str, Any]:
    token = os.getenv("FINNHUB_API_KEY", "").strip()
    if not token:
        raise RuntimeError("FINNHUB_API_KEY is required")
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is required") from exc
    messages: list[dict[str, Any]] = []
    socket = websocket.create_connection(f"{URL}?token={token}", timeout=10)
    try:
        for symbol in symbols:
            socket.send(json.dumps({"type": "subscribe", "symbol": symbol}))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                item = json.loads(socket.recv())
            except Exception:
                continue
            if isinstance(item, dict): messages.append(item)
    finally:
        for symbol in symbols:
            try: socket.send(json.dumps({"type": "unsubscribe", "symbol": symbol}))
            except Exception: pass
        socket.close()
    result = {"version": VERSION, "captured_at": datetime.now(timezone.utc).isoformat(),
              "connection_limit_contract": 2, "subscriptions": symbols,
              "reconnect_tested": False, "heartbeat_observed": any(m.get("type") == "ping" for m in messages),
              **classify_messages(messages)}
    result["evidence_id"] = "FINNHUB:WEBSOCKET:" + hashlib.sha256(
        json.dumps(result, sort_keys=True).encode()).hexdigest()[:20]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="AAPL,MSFT,NVDA")
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--output", type=Path, default=Path("audit_results/finnhub_contract_gap/websocket.json"))
    args = parser.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(run(args.symbols.split(","), args.seconds), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__": raise SystemExit(main())
