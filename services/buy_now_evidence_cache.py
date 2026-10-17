"""Immutable evidence cache and minimal daily request planning for BUY NOW."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from services.buy_now_history_backfill_execution import atomic_json, canonical, file_sha256


SYSTEMIC = {"RATE_LIMITED", "ENTITLEMENT_FAILURE", "SHARED_INTEGRITY_FAILURE"}
TICKER_TERMINAL = {"TERMINAL_NO_DATA", "MALFORMED_PAYLOAD",
                   "CORPORATE_ACTION_INCONSISTENCY", "UNKNOWN_INTEGRITY_FAILURE"}


def classify_provider_outcome(*, endpoint: str, status_code: int,
                              payload: Any | None, transport_certain: bool = True) -> str:
    if not transport_certain:
        return "INDETERMINATE_TRANSPORT"
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code in (401, 403):
        return "ENTITLEMENT_FAILURE"
    if status_code >= 500:
        return "TEMPORARY_PROVIDER_FAILURE"
    if status_code != 200:
        return "UNKNOWN_INTEGRITY_FAILURE"
    if endpoint == "/stock/candle":
        if payload == {"s": "no_data"}:
            return "TERMINAL_NO_DATA"
        fields = ("c", "h", "l", "o", "t", "v")
        if not isinstance(payload, Mapping) or payload.get("s") != "ok":
            return "MALFORMED_PAYLOAD"
        if any(not isinstance(payload.get(key), list) for key in fields):
            return "MALFORMED_PAYLOAD"
        lengths = {len(payload[key]) for key in fields}
        if len(lengths) != 1 or not next(iter(lengths), 0) or any(v is None for v in payload["v"]):
            return "MALFORMED_PAYLOAD"
        return "VALID_MARKET_DATA"
    if endpoint in ("/stock/split", "/stock/dividend"):
        return "VALID_MARKET_DATA" if isinstance(payload, list) else "CORPORATE_ACTION_INCONSISTENCY"
    return "UNKNOWN_INTEGRITY_FAILURE"


def acquisition_disposition(outcomes: Mapping[str, str]) -> dict[str, Any]:
    """Stop on systemic faults; otherwise isolate explicit ticker failures."""
    systemic = sorted(ticker for ticker, status in outcomes.items() if status in SYSTEMIC)
    indeterminate = sorted(ticker for ticker, status in outcomes.items()
                           if status == "INDETERMINATE_TRANSPORT")
    if systemic or indeterminate:
        return {"status": "STOP_CLOSED", "systemic_tickers": systemic,
                "indeterminate_tickers": indeterminate, "withheld_tickers": []}
    withheld = sorted(ticker for ticker, status in outcomes.items() if status in TICKER_TERMINAL)
    accepted = sorted(ticker for ticker, status in outcomes.items() if status == "VALID_MARKET_DATA")
    return {"status": "CONTINUE_WITH_EXPLICIT_WITHHOLDING",
            "systemic_tickers": [], "indeterminate_tickers": [],
            "withheld_tickers": withheld, "accepted_tickers": accepted}


class ImmutableEvidenceCache:
    """Content-addressed cache; existing evidence can only be verified, never replaced."""

    def __init__(self, root: Path):
        self.root = root

    def persist(self, *, request_identity: Mapping[str, Any], envelope: Mapping[str, Any],
                ticker: str, family: str, acquired_at: str,
                finalized_sessions: Sequence[str], quality_status: str) -> dict[str, Any]:
        request_sha = hashlib.sha256(canonical(request_identity)).hexdigest()
        envelope_sha = hashlib.sha256(canonical(envelope)).hexdigest()
        path = self.root / "objects" / request_sha[:2] / f"{request_sha}.json"
        record = {
            "schema": "ATLAS_IMMUTABLE_MARKET_EVIDENCE_V1",
            "request_identity": dict(request_identity), "request_sha256": request_sha,
            "envelope": dict(envelope), "envelope_sha256": envelope_sha,
            "ticker": ticker, "family": family, "acquired_at": acquired_at,
            "finalized_sessions": list(finalized_sessions), "quality_status": quality_status,
        }
        record["record_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
        if path.exists():
            existing = json.loads(path.read_text())
            if existing != record:
                raise RuntimeError("BUY_NOW_CACHE_IMMUTABLE_COLLISION")
            if file_sha256(path) != hashlib.sha256(canonical(record)).hexdigest():
                raise RuntimeError("BUY_NOW_CACHE_FILE_DIGEST_INVALID")
            return {"status": "CACHE_HIT", "path": str(path), "record_sha256": record["record_sha256"]}
        atomic_json(path, record)
        return {"status": "PERSISTED", "path": str(path), "record_sha256": record["record_sha256"]}

    def load(self, request_identity: Mapping[str, Any]) -> dict[str, Any] | None:
        request_sha = hashlib.sha256(canonical(request_identity)).hexdigest()
        path = self.root / "objects" / request_sha[:2] / f"{request_sha}.json"
        if not path.exists():
            return None
        record = json.loads(path.read_text())
        supplied = record.pop("record_sha256", None)
        if supplied != hashlib.sha256(canonical(record)).hexdigest():
            raise RuntimeError("BUY_NOW_CACHE_RECORD_CORRUPT")
        record["record_sha256"] = supplied
        return record


def plan_minimal_daily_requests(*, symbols: Sequence[str], finalized_session: str,
                                contiguous_session_by_ticker: Mapping[str, str],
                                corporate_actions_fresh: Mapping[str, bool]) -> dict[str, Any]:
    governed = sorted(set(symbols))
    requests: list[dict[str, Any]] = []
    withheld: list[dict[str, str]] = []
    for ticker in governed:
        boundary = contiguous_session_by_ticker.get(ticker)
        if boundary == finalized_session:
            continue
        if not boundary:
            withheld.append({"ticker": ticker, "reason": "CONTIGUOUS_HISTORY_UNAVAILABLE"})
            continue
        requests.append({"ticker": ticker, "endpoint": "/stock/candle",
                         "from_session_exclusive": boundary, "to_session": finalized_session})
        if not corporate_actions_fresh.get(ticker, False):
            requests.extend([
                {"ticker": ticker, "endpoint": "/stock/split", "from_session_exclusive": boundary,
                 "to_session": finalized_session},
                {"ticker": ticker, "endpoint": "/stock/dividend", "from_session_exclusive": boundary,
                 "to_session": finalized_session},
            ])
    return {
        "schema": "ATLAS_MINIMAL_DAILY_REQUEST_PLAN_V1",
        "finalized_session": finalized_session, "governed_count": len(governed),
        "requests": requests, "request_count": len(requests),
        "withheld": withheld, "withheld_count": len(withheld),
        "automatic_retries": 0,
    }


__all__ = ["ImmutableEvidenceCache", "SYSTEMIC", "TICKER_TERMINAL",
           "acquisition_disposition", "classify_provider_outcome",
           "plan_minimal_daily_requests"]
