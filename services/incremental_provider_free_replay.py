"""Provider-free transport double for the protected incremental entrypoint.

This module is deliberately fixture-only.  It accepts the endpoint parameters
produced by the real acquisition entrypoint, proves the corrected Finnhub
candle timestamp contract, and emits clearly labelled simulated records.  It
never reads credentials or opens a network connection.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from collections import Counter
import hashlib
import json
import ijson
from pathlib import Path
from typing import Any, Mapping, Sequence


REPLAY_CONTRACT = "ATLAS_INCREMENTAL_PROVIDER_FREE_REPLAY_V1"


def _plan_symbols(plan: Mapping[str, Any]) -> list[str]:
    return sorted({
        str(key).split(":", 2)[1].upper()
        for key in plan.get("request_keys") or () if str(key).count(":") == 2
    })


def validate_replay_retained_scope(
    *, retained_rows: Any, plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(retained_rows, list):
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_SCHEMA_INVALID")
    expected = _plan_symbols(plan)
    observed = [str(row.get("ticker") or "").upper() for row in retained_rows if isinstance(row, Mapping)]
    if len(observed) != len(retained_rows):
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_ROW_INVALID")
    if len(observed) != len(set(observed)):
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_DUPLICATE_SYMBOL")
    if sorted(observed) != expected:
        raise ValueError(
            f"INCREMENTAL_PROVIDER_FREE_RETAINED_MEMBERSHIP_MISMATCH:{len(observed)}:{len(expected)}"
        )
    return [dict(row) for row in retained_rows]


def resolve_replay_retained_records(
    *, artifact_root: Path, plan: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select the exact membership file by the plan-bound raw file digest.

    The retained artifact contains more than one publication tree.  Filesystem
    traversal order is not an identity contract, so selecting the first
    ``full_evaluation_pool.json`` can bind the replay to the wrong projection.
    """
    expected_sha = str((plan.get("governed_membership") or {}).get("source_file_sha256") or "")
    if len(expected_sha) != 64:
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_SOURCE_DIGEST_MISSING")
    candidates = []
    matches: list[Path] = []
    # Publication pools exceed 1 GB. Never retain raw bytes or decode entire
    # alternative trees just to select the checksum-bound source.
    for path in sorted(artifact_root.rglob("full_evaluation_pool.json")):
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
        file_digest = hasher.hexdigest()
        schema, count = "INVALID_JSON", None
        try:
            with path.open("rb") as stream:
                events = ijson.parse(stream, use_float=True)
                prefix, event, value = next(events)
                schema = ("LIST" if event == "start_array" else
                          "DICT" if event == "start_map" else type(value).__name__.upper())
                count = 0 if schema == "LIST" else None
                for prefix, event, value in events:
                    if count is not None and prefix == "item" and event in (
                        "start_map", "start_array", "string", "number", "boolean", "null"
                    ):
                        count += 1
        except (ijson.JSONError, UnicodeDecodeError, StopIteration):
            schema, count = "INVALID_JSON", None
        candidates.append({"relative_path": str(path.relative_to(artifact_root)),
                           "sha256": file_digest, "schema": schema, "row_count": count})
        if file_digest == expected_sha:
            if schema != "LIST":
                raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_SCHEMA_INVALID")
            matches.append(path)
    if not matches:
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_SOURCE_NOT_FOUND")
    selected = matches[0]
    expected = _plan_symbols(plan)
    expected_set = set(expected)
    by_ticker: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    duplicate_tickers: set[str] = set()
    excluded_reasons: Counter[str] = Counter()
    source_count = excluded_count = 0
    with selected.open("rb") as stream:
        for row in ijson.items(stream, "item", use_float=True):
            source_count += 1
            if not isinstance(row, Mapping):
                raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_ROW_INVALID")
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_TICKER_INVALID")
            if ticker in seen:
                duplicate_tickers.add(ticker)
            seen.add(ticker)
            if ticker in expected_set:
                by_ticker[ticker] = dict(row)
                continue
            excluded_count += 1
            certification = row.get("publication_certification")
            certification = certification if isinstance(certification, Mapping) else {}
            reasons = list(certification.get("blockers") or certification.get("reason_codes") or ())
            state = str(certification.get("certification_state") or "").strip()
            if reasons:
                excluded_reasons.update(str(reason) for reason in reasons if str(reason).strip())
            elif state:
                excluded_reasons[state] += 1
            else:
                excluded_reasons["NOT_IN_APPROVED_CUSTOMER_MEMBERSHIP"] += 1
    # Recheck after parsing so a source replacement cannot inherit old authority.
    hasher = hashlib.sha256()
    with selected.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    if hasher.hexdigest() != expected_sha:
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_SOURCE_CHANGED")
    if duplicate_tickers:
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_DUPLICATE_SYMBOL:"
                         + ",".join(sorted(duplicate_tickers)))
    missing = sorted(expected_set - set(by_ticker))
    if missing:
        raise ValueError("INCREMENTAL_PROVIDER_FREE_RETAINED_PLAN_TICKER_MISSING:"
                         + ",".join(missing))
    rows = validate_replay_retained_scope(
        retained_rows=[by_ticker[ticker] for ticker in expected], plan=plan,
    )
    report = {
        "contract": "ATLAS_INCREMENTAL_RETAINED_RECORD_RESOLUTION_V1",
        "expected_source_file_sha256": expected_sha,
        "selected_relative_path": str(selected.relative_to(artifact_root)),
        "source_row_count": source_count,
        "selected_row_count": len(rows), "candidate_count": len(candidates),
        "matching_source_count": len(matches),
        "excluded_row_count": excluded_count,
        "excluded_reason_counts": dict(sorted(excluded_reasons.items())),
        "missing_plan_ticker_count": 0,
        "duplicate_source_ticker_count": 0,
        "candidates": candidates,
    }
    report["resolution_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return rows, report


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


__all__ = [
    "ProviderFreeReplayAdapter", "REPLAY_CONTRACT",
    "resolve_replay_retained_records", "validate_replay_retained_scope",
]
