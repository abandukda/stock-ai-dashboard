"""Provider-free transport double for the protected incremental entrypoint.

This module is deliberately fixture-only.  It accepts the endpoint parameters
produced by the real acquisition entrypoint, proves the corrected Finnhub
candle timestamp contract, and emits clearly labelled simulated records.  It
never reads credentials or opens a network connection.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


REPLAY_CONTRACT = "ATLAS_INCREMENTAL_PROVIDER_FREE_REPLAY_V1"


class ProviderFreeReplayAdapter:
    def __init__(self, *, retained_rows: Sequence[Mapping[str, Any]], session: str) -> None:
        self.rows = {str(row.get("ticker") or "").upper(): dict(row) for row in retained_rows}
        self.session = date.fromisoformat(session)
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _provenance(capability: str, symbol: str) -> dict[str, Any]:
        return {
            "provider": "PROVIDER_FREE_REPLAY_FIXTURE",
            "capability": capability,
            "certification_status": "CERTIFIED",
            "derived_use_permission": "CERTIFIED_CALCULATION",
            "raw_evidence_id": f"replay:{symbol}:{capability}",
            "fixture_classification": "SIMULATED_NOT_PROVIDER_EVIDENCE",
        }

    def fetch(self, capability: str, symbol: str, **parameters: Any) -> dict[str, Any]:
        symbol = symbol.upper()
        if symbol not in self.rows:
            raise ValueError(f"INCREMENTAL_REPLAY_SYMBOL_OUTSIDE_RETAINED_SCOPE:{symbol}")
        self.calls.append({"capability": capability, "symbol": symbol, "parameters": dict(parameters)})
        if capability == "historical_ohlcv":
            start = parameters.get("from")
            end = parameters.get("to")
            if not isinstance(start, int) or not isinstance(end, int) or start >= end:
                raise ValueError("INCREMENTAL_REPLAY_CANDLE_TIMESTAMP_CONTRACT_INVALID")
            expected_start = int(datetime.combine(self.session, datetime.min.time(), tzinfo=timezone.utc).timestamp())
            expected_end = int(datetime.combine(self.session + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp()) - 1
            if (start, end, parameters.get("resolution")) != (expected_start, expected_end, "D"):
                raise ValueError("INCREMENTAL_REPLAY_CANDLE_SCOPE_INVALID")
            price = float(self.rows[symbol].get("current_price") or self.rows[symbol].get("price") or 1.0)
            # One completed bar is sufficient to exercise acquisition and raw-first
            # persistence. Certification receives the unchanged retained analytical
            # row and cannot treat this fixture as real provider evidence.
            payload = {
                "timestamps": [expected_end], "open": [price], "high": [price],
                "low": [price], "close": [price], "volume": [1.0],
                "completed_session_flags": [True],
            }
        elif capability == "sec_filings":
            if parameters.get("from") != self.session.isoformat() or parameters.get("to") != self.session.isoformat():
                raise ValueError("INCREMENTAL_REPLAY_FILING_SCOPE_INVALID")
            payload = {"filings": []}
        else:
            raise ValueError(f"INCREMENTAL_REPLAY_CAPABILITY_NOT_ALLOWED:{capability}")
        return {"payload": payload, "provenance": self._provenance(capability, symbol),
                "limitations": ["PROVIDER_FREE_SIMULATION", "NOT_CUSTOMER_PUBLISHABLE"]}


__all__ = ["ProviderFreeReplayAdapter", "REPLAY_CONTRACT"]
