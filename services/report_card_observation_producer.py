"""Deterministic producer for governed Report Card observation bundles.

This module never calls a provider.  It converts a separately acquired,
source-bound market-evidence snapshot into the exact bundle consumed by
``report_card_observation_activation``.  Keeping acquisition outside this
module makes offline replay identical to an authorized production run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from services.prospective_report_card import ProspectiveLedger, _utc, _finite_observation_number
from services.report_card import HORIZONS
from services.report_card_observation_activation import (
    ALLOWED_CORPORATE_ACTION_STATUS,
    ALLOWED_PRICE_SOURCES,
    BUNDLE_SCHEMA,
    FINALIZED_SESSION_STATUS,
)

EVIDENCE_SCHEMA = "ATLAS_REPORT_CARD_MARKET_EVIDENCE_V1"
PRODUCER_VERSION = "ATLAS_REPORT_CARD_OBSERVATION_PRODUCER_V1"
UNAVAILABLE_STATES = frozenset({
    "MISSING_PRICE", "STALE_PRICE", "DELISTED", "MERGER_PENDING_GOVERNED_TREATMENT",
})


def _sessions_after(sessions: Sequence[str], timestamp: datetime) -> list[str]:
    return [str(value) for value in sessions if datetime.fromisoformat(str(value)).date() > timestamp.date()]


def _close(instrument: Mapping[str, Any], session: str) -> float | None:
    value = (instrument.get("closes") or {}).get(session)
    return _finite_observation_number(value, positive=True)


def build_observation_bundle(
    *, ledger: ProspectiveLedger, evidence: Mapping[str, Any], horizon: int,
    certified_at: datetime,
) -> dict[str, Any]:
    """Build one all-signal, one-horizon bundle or fail closed.

    A requested horizon is emitted only when every immutable signal has that
    many finalized trading sessions. Missing/delisted securities remain in the
    cohort with an explicit unavailable state; immature sessions never do.
    """
    if horizon not in HORIZONS:
        raise ValueError("UNREGISTERED_REPORT_CARD_HORIZON")
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError("MARKET_EVIDENCE_SCHEMA_INVALID")
    if evidence.get("session_status") != FINALIZED_SESSION_STATUS:
        raise ValueError("MARKET_SESSION_NOT_FINALIZED")
    if not evidence.get("trading_calendar_source") or not evidence.get("trading_calendar_version"):
        raise ValueError("TRADING_CALENDAR_IDENTITY_REQUIRED")
    opened = _utc(evidence.get("session_open_at"), "SESSION_OPEN")
    closed = _utc(evidence.get("session_close_at"), "SESSION_CLOSE")
    captured = _utc(evidence.get("captured_at"), "EVIDENCE_CAPTURE")
    current = certified_at.astimezone(timezone.utc)
    if closed <= opened or captured < closed or current < captured:
        raise ValueError("FINALIZED_SESSION_TIMING_INVALID")
    sessions = [str(value) for value in evidence.get("trading_sessions") or ()]
    if sessions != sorted(set(sessions)) or not sessions or sessions[-1] != closed.date().isoformat():
        raise ValueError("TRADING_SESSION_SEQUENCE_INVALID")
    instruments = evidence.get("instruments")
    references = evidence.get("benchmark_references")
    if not isinstance(instruments, Mapping) or not isinstance(references, Mapping):
        raise ValueError("MARKET_EVIDENCE_PAYLOAD_INVALID")
    benchmark = instruments.get("SPY")
    if not isinstance(benchmark, Mapping):
        raise ValueError("SPY_BENCHMARK_REQUIRED")

    records: list[dict[str, Any]] = []
    for row in ledger.rows("SIGNAL"):
        signal_id = str(row["record_id"])
        signal = row["payload"]
        ticker = str(signal.get("ticker") or "").upper()
        executable = _utc(
            signal.get("executable_reference_timestamp") or signal.get("first_seen_at"),
            "SIGNAL_EXECUTABLE_REFERENCE",
        )
        eligible = _sessions_after(sessions, executable)
        if len(eligible) < horizon:
            raise ValueError(f"OBSERVATION_HORIZON_IMMATURE:{signal_id}")
        window = eligible[:horizon]
        if window[-1] != closed.date().isoformat():
            raise ValueError(f"OBSERVATION_NOT_DUE_FOR_SESSION:{signal_id}")
        instrument = instruments.get(ticker)
        if not isinstance(instrument, Mapping):
            instrument = {
                "data_status": "MISSING_PRICE", "unavailable_reason": "INSTRUMENT_EVIDENCE_MISSING",
            }
        data_status = str(instrument.get("data_status") or "AVAILABLE")
        if data_status not in {"AVAILABLE", *UNAVAILABLE_STATES}:
            raise ValueError(f"OBSERVATION_DATA_STATUS_INVALID:{ticker}")
        corporate_action = str(instrument.get("corporate_action_status") or "NONE")
        if corporate_action not in ALLOWED_CORPORATE_ACTION_STATUS:
            raise ValueError(f"CORPORATE_ACTION_STATUS_INVALID:{ticker}")
        price_source = str(instrument.get("price_source") or "")
        if price_source not in ALLOWED_PRICE_SOURCES:
            raise ValueError(f"PRICE_SOURCE_INVALID:{ticker}")
        provenance = dict(instrument.get("price_provenance") or {})
        if provenance.get("session_status") != FINALIZED_SESSION_STATUS:
            raise ValueError(f"PRICE_NOT_FINALIZED:{ticker}")
        required_provenance = ("provider", "instrument", "as_of", "retrieved_at", "currency")
        if not all(provenance.get(key) for key in required_provenance):
            raise ValueError(f"PRICE_PROVENANCE_INCOMPLETE:{ticker}")
        if str(provenance.get("instrument") or "").upper() != ticker:
            raise ValueError(f"PRICE_TICKER_OWNERSHIP_MISMATCH:{ticker}")

        observation: dict[str, Any] = {
            "trading_sessions": window,
            "corporate_action_status": corporate_action,
            "price_source": price_source,
            "price_provenance": provenance,
            "data_status": data_status,
            "observed_price": None,
            "observed_at": closed.isoformat(),
            "benchmark_ticker": "SPY",
            "benchmark_return": None,
            "benchmark_observed_at": closed.isoformat(),
        }
        if data_status == "AVAILABLE":
            observed = _close(instrument, window[-1])
            benchmark_observed = _close(benchmark, window[-1])
            reference = references.get(signal_id)
            benchmark_reference = _finite_observation_number((reference or {}).get("price"), positive=True) or 0.0
            if not observed or not benchmark_observed or benchmark_reference <= 0:
                raise ValueError(f"OBSERVATION_PRICE_MISSING:{ticker}")
            try:
                reference_session = datetime.fromisoformat(str((reference or {}).get("as_of"))).date()
            except (TypeError, ValueError) as exc:
                raise ValueError(f"BENCHMARK_REFERENCE_INVALID:{ticker}") from exc
            if reference_session > executable.date():
                raise ValueError(f"BENCHMARK_REFERENCE_LOOKAHEAD:{ticker}")
            observation.update(
                observed_price=observed,
                benchmark_reference_price=benchmark_reference,
                benchmark_observed_price=benchmark_observed,
            )
        else:
            reason = str(instrument.get("unavailable_reason") or "")
            if not reason:
                raise ValueError(f"OBSERVATION_UNAVAILABLE_REASON_REQUIRED:{ticker}")
            observation["unavailable_reason"] = reason
        records.append({"signal_id": signal_id, "observation": observation})

    if not records:
        raise ValueError("REPORT_CARD_SIGNALS_REQUIRED")
    return {
        "schema_version": BUNDLE_SCHEMA,
        "producer_version": PRODUCER_VERSION,
        "activation_timestamp": ledger.activation_timestamp().isoformat(),
        "ledger_tip_before": ledger.verify(),
        "customer_visible": False,
        "public_performance_claims_allowed": False,
        "provider_calls": 0,
        "reacquisition": "none",
        "session_open_at": opened.isoformat(),
        "session_close_at": closed.isoformat(),
        "bundle_certified_at": current.isoformat(),
        "session_status": FINALIZED_SESSION_STATUS,
        "trading_calendar_source": evidence["trading_calendar_source"],
        "trading_calendar_version": evidence["trading_calendar_version"],
        "horizon_trading_days": horizon,
        "records": records,
    }


__all__ = ["EVIDENCE_SCHEMA", "PRODUCER_VERSION", "UNAVAILABLE_STATES", "build_observation_bundle"]
