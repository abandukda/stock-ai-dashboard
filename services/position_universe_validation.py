"""Internal-only universe state ledger for prospective methodology validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from services.position_management_ledgers import AppendOnlyStateLedger, _digest


UNIVERSE_SCHEMA_VERSION = "ATLAS_POSITION_UNIVERSE_VALIDATION_LEDGER_V1"
UNIVERSE_REQUIRED = {
    "ticker", "scan_timestamp", "sector", "industry", "beta", "market_cap_bucket", "current_action",
    "valuation_state", "technical_state", "risk_state", "candidate_digest", "publication_digest",
    "evaluation_snapshot", "source_sha", "methodology_version", "customer_visible", "delisted",
}


class UniverseValidationLedger(AppendOnlyStateLedger):
    def __init__(self, path: Path, *, activation_timestamp: str):
        super().__init__(path, schema_version=UNIVERSE_SCHEMA_VERSION, activation_timestamp=activation_timestamp)

    def append_state(self, payload: Mapping[str, Any]) -> bool:
        missing = sorted(UNIVERSE_REQUIRED - set(payload))
        if missing:
            raise ValueError("UNIVERSE_STATE_INCOMPLETE:" + ",".join(missing))
        identity = {key: payload[key] for key in ("ticker", "scan_timestamp", "methodology_version",
                                                   "evaluation_snapshot")}
        return self.append(record_id="universe:" + _digest(identity), record_type="UNIVERSE_STATE",
                           created_at=str(payload["scan_timestamp"]), payload=payload)

    def append_forward_return(self, *, state_record_id: str, ticker: str, horizon_sessions: int,
                              observed_at: str, stock_return: float | None, spy_return: float | None,
                              sector_return: float | None, data_status: str,
                              corporate_action_status: str) -> bool:
        if horizon_sessions not in {1, 5, 21, 63, 126, 252}:
            raise ValueError("UNREGISTERED_FORWARD_RETURN_HORIZON")
        payload = {"state_record_id": state_record_id, "ticker": ticker,
                   "horizon_sessions": horizon_sessions, "observed_at": observed_at,
                   "stock_return": stock_return, "spy_return": spy_return,
                   "sector_return": sector_return, "data_status": data_status,
                   "corporate_action_status": corporate_action_status, "customer_visible": False}
        identity = {"state_record_id": state_record_id, "horizon_sessions": horizon_sessions}
        return self.append(record_id="forward:" + _digest(identity), record_type="FORWARD_RETURN",
                           created_at=observed_at, payload=payload)


__all__ = ["UNIVERSE_SCHEMA_VERSION", "UniverseValidationLedger"]
