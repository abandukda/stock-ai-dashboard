"""Read-only projection of the internal shadow position ledger."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from services.position_management_ledgers import _digest


def build_shadow_position_dashboard(path: Path, *, authorized: bool) -> dict[str, Any]:
    if not authorized:
        raise PermissionError("INTERNAL_POSITION_MONITOR_ACCESS_REQUIRED")
    ledger_path = Path(path).resolve()
    if not ledger_path.is_file():
        raise FileNotFoundError("POSITION_SHADOW_LEDGER_UNAVAILABLE")
    with sqlite3.connect(f"file:{ledger_path.as_posix()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        metadata = {row["key"]: row["value"] for row in db.execute("SELECT key,value FROM metadata")}
        rows = list(db.execute("SELECT * FROM state_records WHERE record_type='POSITION_STATE' ORDER BY sequence"))
    if metadata.get("customer_visible") != "false":
        raise PermissionError("CUSTOMER_POSITION_MANAGEMENT_MUST_REMAIN_OFF")
    previous = "GENESIS"
    decoded = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        expected = _digest({"record_id": row["record_id"], "record_type": row["record_type"],
                            "created_at": row["created_at"], "payload": payload,
                            "previous_digest": previous})
        if row["previous_digest"] != previous or row["record_digest"] != expected:
            raise ValueError("SHADOW_LEDGER_INTEGRITY_FAILURE")
        previous = expected
        decoded.append(payload)
    latest: dict[str, dict[str, Any]] = {}
    for payload in decoded:
        latest[str(payload["signal_id"])] = payload
    return {"classification": "INTERNAL_SHADOW_POSITION_MONITOR", "customer_visible": False,
            "integrity": "PASS", "activation_timestamp": metadata.get("activation_timestamp"),
            "methodology_version": next(iter(latest.values()), {}).get("methodology_version"),
            "ledger_tip": previous, "history_count": len(decoded), "positions": list(latest.values()),
            "latest_by_signal_id": latest}


__all__ = ["build_shadow_position_dashboard"]
