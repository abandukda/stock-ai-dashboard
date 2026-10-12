"""Bounded Finnhub acquisition for prospective Report Card observations.

The module is inert until called with an explicit authorization token. It reads
the protected ledger, never writes it, and emits only the internal evidence
schema consumed by :mod:`services.report_card_observation_producer`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Mapping, Protocol, Sequence

from services.finnhub_enterprise_display_contract import display_authority
from services.finnhub_rate_governance import FinnhubRateContract, FinnhubRateGovernor
from services.prospective_report_card import ProspectiveLedger, _utc
from services.report_card import HORIZONS
from services.report_card_observation_activation import FINALIZED_SESSION_STATUS
from services.report_card_observation_producer import EVIDENCE_SCHEMA


ACQUISITION_VERSION = "ATLAS_REPORT_CARD_MARKET_EVIDENCE_ACQUISITION_V1"
AUTHORIZATION_TOKEN = "REPORT_CARD_ACQUIRE_ONCE"
LICENSE_CLASS = "FINNHUB_PAID_CORE_CERTIFICATION"
REQUIRED_CAPABILITIES = ("historical_ohlcv", "splits", "dividends")


class Provider(Protocol):
    def fetch(self, capability: str, symbol: str, **parameters: Any) -> Any: ...


@dataclass(frozen=True)
class AcquisitionScope:
    ledger_tip: str
    activation_timestamp: str
    signal_ids: tuple[str, ...]
    tickers: tuple[str, ...]
    horizons: tuple[int, ...]
    target_sessions: Mapping[int, str]

    @property
    def scope_digest(self) -> str:
        return _digest({
            "ledger_tip": self.ledger_tip,
            "activation_timestamp": self.activation_timestamp,
            "signal_ids": self.signal_ids,
            "tickers": self.tickers,
            "horizons": self.horizons,
            "target_sessions": dict(self.target_sessions),
        })


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _record_dict(record: Any) -> Mapping[str, Any]:
    value = record.as_dict() if hasattr(record, "as_dict") else record
    if not isinstance(value, Mapping):
        raise ValueError("PROVIDER_RECORD_INVALID")
    return value


def derive_acquisition_scope(
    *, ledger: ProspectiveLedger, trading_sessions: Sequence[str], finalized_session: str,
) -> AcquisitionScope:
    """Derive due horizons solely from verified immutable ledger state."""
    tip = ledger.verify()
    signals = ledger.rows("SIGNAL")
    if not signals:
        raise ValueError("REPORT_CARD_SIGNALS_REQUIRED")
    sessions = tuple(str(item) for item in trading_sessions)
    if sessions != tuple(sorted(set(sessions))) or finalized_session not in sessions:
        raise ValueError("TRADING_CALENDAR_INVALID")
    final_index = sessions.index(finalized_session)
    usable = sessions[: final_index + 1]
    observations = ledger.rows("OBSERVATION")
    observed = {(row["parent_id"], int(row["payload"].get("horizon_trading_days", 0))) for row in observations}
    signal_targets: dict[int, set[str]] = {horizon: set() for horizon in HORIZONS}
    for row in signals:
        signal_id = str(row["record_id"])
        payload = row["payload"]
        reference = _utc(
            payload.get("executable_reference_timestamp") or payload.get("first_seen_at"),
            "SIGNAL_EXECUTABLE_REFERENCE",
        )
        eligible = [session for session in usable if datetime.fromisoformat(session).date() > reference.date()]
        for horizon in HORIZONS:
            if len(eligible) >= horizon and (signal_id, horizon) not in observed:
                signal_targets[horizon].add(eligible[horizon - 1])
    targets: dict[int, str] = {}
    signal_count = len(signals)
    for horizon, values in signal_targets.items():
        if not values:
            continue
        if len(values) != 1:
            raise ValueError(f"MIXED_SIGNAL_MATURITY:{horizon}")
        eligible_count = sum(
            (str(row["record_id"]), horizon) not in observed
            and len([
                session for session in usable
                if datetime.fromisoformat(session).date() > _utc(
                    row["payload"].get("executable_reference_timestamp") or row["payload"].get("first_seen_at"),
                    "SIGNAL_EXECUTABLE_REFERENCE",
                ).date()
            ]) >= horizon
            for row in signals
        )
        if eligible_count != signal_count:
            raise ValueError(f"PARTIAL_HORIZON_STATE:{horizon}")
        targets[horizon] = next(iter(values))
    tickers = tuple(sorted({str(row["payload"].get("ticker") or "").upper() for row in signals}))
    if not all(tickers):
        raise ValueError("SIGNAL_TICKER_REQUIRED")
    return AcquisitionScope(
        ledger_tip=tip,
        activation_timestamp=ledger.activation_timestamp().isoformat(),
        signal_ids=tuple(str(row["record_id"]) for row in signals),
        tickers=tickers,
        horizons=tuple(sorted(targets)),
        target_sessions=targets,
    )


def estimated_provider_calls(scope: AcquisitionScope) -> int:
    """One OHLCV call per instrument plus split/dividend calls per signal ticker."""
    return 0 if not scope.horizons else 3 * len(scope.tickers) + 1


def acquire_market_evidence(
    *, ledger: ProspectiveLedger, provider: Provider, calendar: Mapping[str, Any],
    now: datetime, authorization: str, source_sha: str,
    retry_attempts: int = 2, rate_governor: FinnhubRateGovernor | None = None,
    retryable: Callable[[Mapping[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Acquire one bounded, replayable internal market-evidence snapshot."""
    if authorization != AUTHORIZATION_TOKEN:
        raise PermissionError("REPORT_CARD_ACQUISITION_NOT_AUTHORIZED")
    if len(source_sha) != 40:
        raise ValueError("SOURCE_SHA_REQUIRED")
    captured = now.astimezone(timezone.utc)
    sessions = tuple(str(item) for item in calendar.get("trading_sessions") or ())
    finalized = str(calendar.get("finalized_session") or "")
    if calendar.get("session_status") != FINALIZED_SESSION_STATUS:
        raise ValueError("MARKET_SESSION_NOT_FINALIZED")
    opened = _utc(calendar.get("session_open_at"), "SESSION_OPEN")
    closed = _utc(calendar.get("session_close_at"), "SESSION_CLOSE")
    if captured < closed or closed <= opened or closed.date().isoformat() != finalized:
        raise ValueError("FINALIZED_SESSION_TIMING_INVALID")
    scope = derive_acquisition_scope(ledger=ledger, trading_sessions=sessions, finalized_session=finalized)
    call_budget = estimated_provider_calls(scope)
    if not scope.horizons:
        return {
            "schema_version": EVIDENCE_SCHEMA,
            "acquisition_version": ACQUISITION_VERSION,
            "status": "NO_DUE_OBSERVATIONS",
            "source_sha": source_sha,
            "scope_digest": scope.scope_digest,
            "ledger_tip": scope.ledger_tip,
            "provider_calls": 0,
            "instruments": {},
        }
    governor = rate_governor or FinnhubRateGovernor(FinnhubRateContract(500, 1, 0))
    retryable = retryable or (lambda record: str((record.get("payload") or {}).get("reason") or "").startswith("HTTP_5"))
    telemetry: list[dict[str, Any]] = []

    def fetch(capability: str, ticker: str) -> Mapping[str, Any]:
        authority = display_authority(capability)
        if authority is None:
            raise PermissionError(f"UNCONTRACTED_CAPABILITY:{capability}")
        parameters: dict[str, Any] = {}
        if capability == "historical_ohlcv":
            parameters = {"resolution": "D", "from": sessions[0], "to": finalized}
        elif capability in {"splits", "dividends"}:
            parameters = {"from": sessions[0], "to": finalized}
        for attempt in range(retry_attempts + 1):
            governor.before_request()
            record = _record_dict(provider.fetch(capability, ticker, **parameters))
            provenance = record.get("provenance") or {}
            telemetry.append({
                "capability": capability,
                "ticker": ticker,
                "attempt": attempt + 1,
                "status": provenance.get("certification_status"),
                "content_hash": provenance.get("content_hash"),
            })
            if not retryable(record) or attempt == retry_attempts:
                return record
            governor.retry_delay(2 ** attempt)
        raise AssertionError("unreachable")

    records: dict[tuple[str, str], Mapping[str, Any]] = {}
    for ticker in (*scope.tickers, "SPY"):
        records[(ticker, "historical_ohlcv")] = fetch("historical_ohlcv", ticker)
    for ticker in scope.tickers:
        records[(ticker, "splits")] = fetch("splits", ticker)
        records[(ticker, "dividends")] = fetch("dividends", ticker)
    if len(telemetry) > call_budget * (retry_attempts + 1):
        raise ValueError("PROVIDER_CALL_BUDGET_EXCEEDED")

    instruments: dict[str, Any] = {}
    for ticker in (*scope.tickers, "SPY"):
        price_record = records[(ticker, "historical_ohlcv")]
        price_payload = price_record.get("payload") or {}
        provenance = price_record.get("provenance") or {}
        timestamps = list(price_payload.get("timestamps") or ())
        closes = list(price_payload.get("close") or ())
        flags = list(price_payload.get("completed_session_flags") or ())
        if not (len(timestamps) == len(closes) == len(flags)):
            raise ValueError(f"PARTIAL_PRICE_ACQUISITION:{ticker}")
        close_map: dict[str, float] = {}
        for stamp, close, completed in zip(timestamps, closes, flags):
            if not completed:
                continue
            session = datetime.fromtimestamp(float(stamp), timezone.utc).date().isoformat()
            if session in sessions and close not in (None, ""):
                close_map[session] = float(close)
        missing_targets = [session for session in scope.target_sessions.values() if session not in close_map]
        latest_available_session = max(close_map) if close_map else None
        if not missing_targets:
            status = "AVAILABLE"
        elif latest_available_session:
            status = "STALE_PRICE"
        else:
            status = "MISSING_PRICE"
        instrument: dict[str, Any] = {
            "data_status": status,
            "closes": close_map,
            "corporate_action_status": "NONE",
            "price_source": "GOVERNED_ADJUSTED_DAILY_CLOSE",
            "price_provenance": {
                "provider": "FINNHUB",
                "instrument": ticker,
                "as_of": closed.isoformat(),
                "retrieved_at": captured.isoformat(),
                "currency": "USD",
                "session_status": FINALIZED_SESSION_STATUS,
                "raw_evidence_id": provenance.get("raw_evidence_id"),
                "content_hash": provenance.get("content_hash"),
            },
        }
        if missing_targets:
            instrument["unavailable_reason"] = (
                "FINALIZED_DAILY_CLOSE_STALE" if latest_available_session else "FINALIZED_DAILY_CLOSE_MISSING"
            )
            instrument["latest_available_session"] = latest_available_session
        if ticker != "SPY":
            for capability in ("splits", "dividends"):
                action_record = records[(ticker, capability)]
                action_provenance = action_record.get("provenance") or {}
                if str(action_provenance.get("certification_status")) not in {"CERTIFIED", "UNVERIFIED_SHADOW"}:
                    raise ValueError(f"CORPORATE_ACTION_EVIDENCE_UNAVAILABLE:{ticker}:{capability}")
            split_actions = (records[(ticker, "splits")].get("payload") or {}).get("corporate_actions") or []
            dividend_actions = (records[(ticker, "dividends")].get("payload") or {}).get("corporate_actions") or []
            if split_actions:
                instrument["corporate_action_status"] = "SPLIT_ADJUSTED"
            instrument["corporate_action_evidence"] = {
                "splits": split_actions,
                "dividends": dividend_actions,
            }
        instruments[ticker] = instrument

    spy_closes = instruments["SPY"]["closes"]
    benchmark_references: dict[str, dict[str, Any]] = {}
    for row in ledger.rows("SIGNAL"):
        payload = row["payload"]
        reference_timestamp = (
            payload.get("executable_reference_timestamp")
            or payload.get("first_seen_at")
            or row.get("created_at")
        )
        if not reference_timestamp:
            raise ValueError(f"SIGNAL_REFERENCE_TIMESTAMP_REQUIRED:{row['record_id']}")
        reference_date = datetime.fromisoformat(str(reference_timestamp).replace("Z", "+00:00")).date().isoformat()
        eligible_sessions = [session for session in spy_closes if session <= reference_date]
        if not eligible_sessions:
            raise ValueError(f"BENCHMARK_REFERENCE_EVIDENCE_REQUIRED:{row['record_id']}")
        benchmark_session = max(eligible_sessions)
        benchmark_references[row["record_id"]] = {
            "price": spy_closes[benchmark_session],
            "as_of": benchmark_session,
            "source": "GOVERNED_SPY_ADJUSTED_DAILY_CLOSE",
            "raw_evidence_id": instruments["SPY"]["price_provenance"]["raw_evidence_id"],
            "content_hash": instruments["SPY"]["price_provenance"]["content_hash"],
        }
    artifact = {
        "schema_version": EVIDENCE_SCHEMA,
        "acquisition_version": ACQUISITION_VERSION,
        "status": "ACQUIRED",
        "source_sha": source_sha,
        "captured_at": captured.isoformat(),
        "session_open_at": opened.isoformat(),
        "session_close_at": closed.isoformat(),
        "session_status": FINALIZED_SESSION_STATUS,
        "trading_calendar_source": str(calendar.get("source") or ""),
        "trading_calendar_version": str(calendar.get("version") or ""),
        "trading_sessions": list(sessions),
        "ledger_tip": scope.ledger_tip,
        "activation_timestamp": scope.activation_timestamp,
        "scope_digest": scope.scope_digest,
        "signal_ids": list(scope.signal_ids),
        "due_horizons": list(scope.horizons),
        "target_sessions": {str(key): value for key, value in scope.target_sessions.items()},
        "provider_call_budget": call_budget,
        "provider_calls": len(telemetry),
        "provider_telemetry": telemetry,
        "benchmark_references": benchmark_references,
        "instruments": instruments,
        "customer_visible": False,
        "raw_machine_readable_redistribution": False,
    }
    if not artifact["trading_calendar_source"] or not artifact["trading_calendar_version"]:
        raise ValueError("TRADING_CALENDAR_IDENTITY_REQUIRED")
    artifact["artifact_sha256"] = _digest(artifact)
    return artifact


__all__ = [
    "ACQUISITION_VERSION", "AUTHORIZATION_TOKEN", "AcquisitionScope",
    "acquire_market_evidence", "derive_acquisition_scope", "estimated_provider_calls",
]
