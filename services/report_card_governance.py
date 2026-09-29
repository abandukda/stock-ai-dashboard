"""Versioned, inactive governance contract for prospective ATLAS reporting.

This module defines records and deterministic transition rules.  It does not
activate recording, backfill history, publish performance, or change any ATLAS
investment methodology.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


GOVERNANCE_VERSION = "ATLAS_REPORT_CARD_GOVERNANCE_V1"
BUY_RANGE_RULE_VERSION = "ATLAS_LONG_TERM_BUY_RANGE_V1"
LONG_TERM_EXECUTION_RULE_VERSION = "ATLAS_LONG_TERM_FIRST_QUALIFYING_RTH_TRADE_V1"
LONG_TERM_EXPIRATION_RULE_VERSION = "ATLAS_LONG_TERM_FIVE_TRADING_SESSIONS_V1"
SWING_EXECUTION_RULE_VERSION = "ATLAS_SWING_EXECUTION_V1"
CORPORATE_ACTION_RULE_VERSION = "ATLAS_CORPORATE_ACTION_LIFECYCLE_V1"
PORTFOLIO_CAPACITY_RULE_VERSION = "ATLAS_PORTFOLIO_CAPACITY_NO_QUEUE_V1"
REPORT_CARD_PROSPECTIVE_ACTIVE = False
REPORT_CARD_ACTIVATION_READY = False
MODEL_PORTFOLIO_FILL_ASSUMPTION = "MODEL_PORTFOLIO_FULL_FILL_ASSUMPTION"
AMBIGUOUS_BAR_RULE = "AMBIGUOUS_DAILY_BAR_CONSERVATIVE_STOP_FIRST"

LONG_TERM_HORIZONS = (1, 5, 21, 63, 126, 252)
SWING_HORIZONS = (0, 1, 3, 5, 10, 21)
SWING_EXPIRATION_RULES = {
    "BREAKOUT": (1, "ATLAS_SWING_BREAKOUT_ONE_SESSION_V1"),
    "PULLBACK": (3, "ATLAS_SWING_PULLBACK_THREE_SESSIONS_V1"),
    "MOMENTUM_CONTINUATION": (2, "ATLAS_SWING_MOMENTUM_TWO_SESSIONS_V1"),
}


class PipelineState(str, Enum):
    COMPLETE_WITH_SIGNALS = "COMPLETE_WITH_SIGNALS"
    NO_QUALIFYING_SIGNALS = "NO_QUALIFYING_SIGNALS"
    EVALUATION_NOT_PERFORMED = "EVALUATION_NOT_PERFORMED"
    EVALUATION_INCOMPLETE = "EVALUATION_INCOMPLETE"
    PROVIDER_DATA_FAILURE = "PROVIDER_DATA_FAILURE"
    PUBLICATION_FAILURE = "PUBLICATION_FAILURE"


class LongTermTerminalState(str, Enum):
    EXECUTED = "EXECUTED"
    PRICE_NEVER_ENTERED_CERTIFIED_BUY_RANGE = "PRICE_NEVER_ENTERED_CERTIFIED_BUY_RANGE"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    REVALIDATED_NEW_SIGNAL = "REVALIDATED_NEW_SIGNAL"


class SwingTerminalState(str, Enum):
    EXECUTED = "EXECUTED"
    ENTRY_RANGE_NEVER_REACHED = "ENTRY_RANGE_NEVER_REACHED"
    BREAKOUT_NEVER_CONFIRMED = "BREAKOUT_NEVER_CONFIRMED"
    SETUP_EXPIRED = "SETUP_EXPIRED"
    SETUP_INVALIDATED_BEFORE_ENTRY = "SETUP_INVALIDATED_BEFORE_ENTRY"


class SignalOutcome(str, Enum):
    SIGNAL_EXECUTED = "SIGNAL_EXECUTED"
    SIGNAL_NOT_FUNDED_PORTFOLIO_FULL = "SIGNAL_NOT_FUNDED_PORTFOLIO_FULL"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    SIGNAL_NEVER_ENTERED_RANGE = "SIGNAL_NEVER_ENTERED_RANGE"


class PositionExitType(str, Enum):
    TARGET = "TARGET"
    STOP = "STOP"
    THESIS_INVALIDATION = "THESIS_INVALIDATION"
    TIME_EXIT = "TIME_EXIT"
    OTHER_PREDECLARED_EXIT = "OTHER_PREDECLARED_EXIT"
    PORTFOLIO_REBALANCING = "PORTFOLIO_REBALANCING"


class ExchangeCalendar(Protocol):
    """Canonical exchange-session dependency; calendar-day arithmetic is forbidden."""

    def session_at_or_after(self, timestamp: datetime) -> str: ...
    def next_sessions(self, session: str, count: int) -> Sequence[str]: ...
    def session_close(self, session: str) -> datetime: ...
    def is_regular_hours(self, timestamp: datetime) -> bool: ...


def _aware(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name}_TIMEZONE_REQUIRED")
    return parsed


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class GovernedCeiling:
    ceiling_type: str
    value: float
    applicable: bool
    certified: bool
    evidence_ids: tuple[str, ...]

    def eligible_value(self) -> float | None:
        if not self.applicable:
            return None
        if not self.certified or not self.evidence_ids:
            raise ValueError(f"APPLICABLE_CEILING_NOT_CERTIFIED:{self.ceiling_type}")
        if self.value <= 0:
            raise ValueError(f"CEILING_NOT_POSITIVE:{self.ceiling_type}")
        return float(self.value)


@dataclass(frozen=True)
class LongTermBuyRange:
    buy_range_lower: float
    preferred_entry: float
    buy_range_upper: float
    max_buy_price: float
    valuation_ceiling: GovernedCeiling | None
    technical_ceiling: GovernedCeiling | None
    risk_reward_ceiling: GovernedCeiling | None
    other_ceilings: tuple[GovernedCeiling, ...]
    binding_ceiling_type: str
    binding_ceiling_value: float
    buy_range_rule_version: str = BUY_RANGE_RULE_VERSION


def build_long_term_buy_range(*, buy_range_lower: float, preferred_entry: float,
                              buy_range_upper: float, valuation_ceiling: GovernedCeiling | None,
                              technical_ceiling: GovernedCeiling | None,
                              risk_reward_ceiling: GovernedCeiling | None,
                              other_ceilings: Sequence[GovernedCeiling] = ()) -> LongTermBuyRange:
    ceilings = tuple(item for item in (valuation_ceiling, technical_ceiling, risk_reward_ceiling, *other_ceilings)
                     if item is not None)
    eligible = [(item.ceiling_type, value) for item in ceilings if (value := item.eligible_value()) is not None]
    if not eligible:
        raise ValueError("NO_APPLICABLE_CERTIFIED_HARD_CEILING")
    binding_type, maximum = min(eligible, key=lambda item: (item[1], item[0]))
    lower, preferred, upper = map(float, (buy_range_lower, preferred_entry, buy_range_upper))
    if not 0 < lower <= preferred <= upper <= maximum:
        raise ValueError("BUY_RANGE_EXCEEDS_CERTIFIED_BUY_NOW_CEILING")
    return LongTermBuyRange(
        lower, preferred, upper, maximum, valuation_ceiling, technical_ceiling,
        risk_reward_ceiling, tuple(other_ceilings), binding_type, maximum,
    )


@dataclass(frozen=True)
class LongTermSignal:
    ticker: str
    stable_security_id: str
    signal_id: str
    signal_timestamp: str
    snapshot_timestamp: str
    observable_price_at_signal: float
    buy_range: LongTermBuyRange
    fair_value: float
    upside_at_signal_price: float
    upside_at_max_buy_price: float
    stop_or_invalidation_level: float | None
    action: str
    opportunity: float
    confidence: float
    six_pillars: Mapping[str, Any]
    valuation_methods: tuple[str, ...]
    valuation_outputs: Mapping[str, Any]
    valuation_reconciliation: Mapping[str, Any]
    scenario_evidence: Mapping[str, Any]
    technical_state: Mapping[str, Any]
    volume_state: Mapping[str, Any]
    risk_state: Mapping[str, Any]
    market_regime: str
    sector_context: Mapping[str, Any]
    provider_authority_version: str
    methodology_version: str
    execution_rule_version: str
    normalization_version: str
    candidate_digest: str
    evidence_ids: tuple[str, ...]
    raw_hashes: tuple[str, ...]
    publication_state: str
    signal_expiration_timestamp: str
    expiration_rule_version: str = LONG_TERM_EXPIRATION_RULE_VERSION
    signal_kind: str = "LONG_TERM"


def build_long_term_signal(payload: Mapping[str, Any], *, calendar: ExchangeCalendar) -> LongTermSignal:
    required = (
        "ticker", "stable_security_id", "signal_timestamp", "snapshot_timestamp", "observable_price_at_signal",
        "buy_range", "fair_value", "action", "opportunity", "confidence", "six_pillars", "valuation_methods",
        "provider_authority_version", "methodology_version", "normalization_version", "candidate_digest",
        "evidence_ids", "raw_hashes", "publication_state",
    )
    missing = [name for name in required if payload.get(name) in (None, "", (), [])]
    if missing:
        raise ValueError("MISSING_LONG_TERM_SIGNAL_FIELDS:" + ",".join(missing))
    if payload["action"] != "BUY_NOW" or payload["publication_state"] != "CUSTOMER_PUBLISHABLE_CERTIFIED":
        raise ValueError("LONG_TERM_SIGNAL_REQUIRES_PUBLISHABLE_CERTIFIED_BUY_NOW")
    timestamp = _aware(str(payload["signal_timestamp"]), "SIGNAL_TIMESTAMP")
    snapshot = _aware(str(payload["snapshot_timestamp"]), "SNAPSHOT_TIMESTAMP")
    if snapshot > timestamp:
        raise ValueError("SNAPSHOT_AFTER_SIGNAL")
    buy_range = payload["buy_range"]
    if not isinstance(buy_range, LongTermBuyRange):
        raise TypeError("BUY_RANGE_GOVERNANCE_REQUIRED")
    first_session = calendar.session_at_or_after(timestamp)
    sessions = list(calendar.next_sessions(first_session, 5))
    if len(sessions) != 5:
        raise ValueError("CANONICAL_CALENDAR_CANNOT_RESOLVE_EXPIRATION")
    expiration = calendar.session_close(sessions[-1])
    identity = {
        "ticker": str(payload["ticker"]).upper(), "stable_security_id": str(payload["stable_security_id"]),
        "signal_timestamp": timestamp.isoformat(), "candidate_digest": str(payload["candidate_digest"]),
        "methodology_version": str(payload["methodology_version"]),
    }
    signal_id = str(payload.get("signal_id") or _digest(identity))
    price, fair_value = float(payload["observable_price_at_signal"]), float(payload["fair_value"])
    return LongTermSignal(
        identity["ticker"], identity["stable_security_id"], signal_id, timestamp.isoformat(), snapshot.isoformat(),
        price, buy_range, fair_value, fair_value / price - 1, fair_value / buy_range.max_buy_price - 1,
        payload.get("stop_or_invalidation_level"), "BUY_NOW", float(payload["opportunity"]),
        float(payload["confidence"]), dict(payload["six_pillars"]), tuple(payload["valuation_methods"]),
        dict(payload.get("valuation_outputs") or {}), dict(payload.get("valuation_reconciliation") or {}),
        dict(payload.get("scenario_evidence") or {}), dict(payload.get("technical_state") or {}),
        dict(payload.get("volume_state") or {}), dict(payload.get("risk_state") or {}),
        str(payload.get("market_regime") or "UNAVAILABLE"), dict(payload.get("sector_context") or {}),
        str(payload["provider_authority_version"]), identity["methodology_version"],
        LONG_TERM_EXECUTION_RULE_VERSION, str(payload["normalization_version"]), identity["candidate_digest"],
        tuple(payload["evidence_ids"]), tuple(payload["raw_hashes"]), str(payload["publication_state"]),
        expiration.isoformat(),
    )


@dataclass(frozen=True)
class LongTermExecution:
    execution_id: str
    signal_id: str
    execution_timestamp: str
    execution_price: float
    market_session: str
    price_source: str
    execution_rule_version: str = LONG_TERM_EXECUTION_RULE_VERSION
    fill_assumption: str = MODEL_PORTFOLIO_FILL_ASSUMPTION


@dataclass(frozen=True)
class SignalLifecycleEvent:
    event_id: str
    signal_id: str
    signal_kind: str
    event_timestamp: str
    outcome: str
    executable_price: float | None
    capital_available: bool | None
    position_slot_available: bool | None
    terminal_for_execution: bool
    capacity_rule_version: str = PORTFOLIO_CAPACITY_RULE_VERSION


def evaluate_portfolio_capacity(*, signal_id: str, signal_kind: str, event_timestamp: str,
                                executable_price: float, capital_available: bool,
                                position_slot_available: bool) -> SignalLifecycleEvent:
    """Evaluate capacity only after a valid signal becomes price-executable."""
    timestamp = _aware(event_timestamp, "CAPACITY_EVENT_TIMESTAMP")
    funded = bool(capital_available and position_slot_available)
    outcome = "EXECUTION_CAPACITY_AVAILABLE" if funded else SignalOutcome.SIGNAL_NOT_FUNDED_PORTFOLIO_FULL.value
    identity = {"signal_id": signal_id, "timestamp": timestamp.isoformat(), "outcome": outcome}
    return SignalLifecycleEvent(
        _digest(identity), signal_id, signal_kind, timestamp.isoformat(), outcome,
        float(executable_price), bool(capital_available), bool(position_slot_available), not funded,
    )


def assert_signal_may_execute(signal_id: str, lifecycle_events: Sequence[SignalLifecycleEvent]) -> None:
    terminal = {
        SignalOutcome.SIGNAL_NOT_FUNDED_PORTFOLIO_FULL.value,
        SignalOutcome.SIGNAL_EXPIRED.value,
        SignalOutcome.SIGNAL_NEVER_ENTERED_RANGE.value,
    }
    if any(event.signal_id == signal_id and event.outcome in terminal for event in lifecycle_events):
        raise PermissionError("SIGNAL_TERMINAL_NO_QUEUE_NEW_CERTIFIED_SIGNAL_REQUIRED")


def build_position_exit(*, position_id: str, signal_id: str, event_timestamp: str,
                        exit_type: PositionExitType, exit_price: float,
                        rule_version: str, methodology_allows_rebalancing: bool = False) -> Mapping[str, Any]:
    timestamp = _aware(event_timestamp, "POSITION_EXIT_TIMESTAMP")
    if not rule_version:
        raise ValueError("POSITION_EXIT_RULE_VERSION_REQUIRED")
    if exit_type is PositionExitType.PORTFOLIO_REBALANCING and not methodology_allows_rebalancing:
        raise PermissionError("PORTFOLIO_REBALANCING_EXIT_NOT_GOVERNED_IN_V1")
    return {
        "event_id": _digest({"position_id": position_id, "timestamp": timestamp.isoformat(),
                             "exit_type": exit_type.value}),
        "position_id": position_id, "signal_id": signal_id, "event_timestamp": timestamp.isoformat(),
        "exit_type": exit_type.value, "exit_price": float(exit_price), "rule_version": rule_version,
        "thesis_invalidated": exit_type is PositionExitType.THESIS_INVALIDATION,
    }


def summarize_signal_outcomes(*, signal_ids: Sequence[str],
                              lifecycle_events: Sequence[SignalLifecycleEvent]) -> Mapping[str, int]:
    latest = {event.signal_id: event for event in lifecycle_events}
    counts = {
        "SIGNALS_ISSUED": len(set(signal_ids)), "SIGNALS_EXECUTED": 0,
        "SIGNALS_NOT_FUNDED_PORTFOLIO_FULL": 0, "SIGNALS_EXPIRED": 0,
        "SIGNALS_NEVER_ENTERED_RANGE": 0,
    }
    mapping = {
        SignalOutcome.SIGNAL_EXECUTED.value: "SIGNALS_EXECUTED",
        SignalOutcome.SIGNAL_NOT_FUNDED_PORTFOLIO_FULL.value: "SIGNALS_NOT_FUNDED_PORTFOLIO_FULL",
        SignalOutcome.SIGNAL_EXPIRED.value: "SIGNALS_EXPIRED",
        SignalOutcome.SIGNAL_NEVER_ENTERED_RANGE.value: "SIGNALS_NEVER_ENTERED_RANGE",
    }
    for signal_id in set(signal_ids):
        event = latest.get(signal_id)
        if event and event.outcome in mapping:
            counts[mapping[event.outcome]] += 1
    return counts


def signal_quality_population(signals: Sequence[LongTermSignal | SwingSignal]) -> tuple[str, ...]:
    """All issued signals participate, regardless of portfolio funding."""
    return tuple(signal.signal_id if isinstance(signal, LongTermSignal) else signal.swing_signal_id
                 for signal in signals)


def portfolio_performance_population(executions: Sequence[LongTermExecution | SwingExecution]) -> tuple[str, ...]:
    """Only actually executed positions participate in portfolio performance."""
    return tuple(execution.execution_id for execution in executions)


def first_qualifying_long_term_execution(signal: LongTermSignal, trades: Sequence[Mapping[str, Any]],
                                         *, calendar: ExchangeCalendar) -> LongTermExecution | None:
    issued = _aware(signal.signal_timestamp, "SIGNAL_TIMESTAMP")
    expiry = _aware(signal.signal_expiration_timestamp, "SIGNAL_EXPIRATION_TIMESTAMP")
    for trade in sorted(trades, key=lambda item: str(item.get("timestamp", ""))):
        timestamp = _aware(str(trade.get("timestamp")), "TRADE_TIMESTAMP")
        if timestamp < issued or timestamp > expiry or not calendar.is_regular_hours(timestamp):
            continue
        price = float(trade["price"])
        if signal.buy_range.buy_range_lower <= price <= signal.buy_range.max_buy_price:
            identity = {"signal_id": signal.signal_id, "timestamp": timestamp.isoformat(), "price": price}
            return LongTermExecution(_digest(identity), signal.signal_id, timestamp.isoformat(), price,
                                     "REGULAR_HOURS", str(trade.get("price_source") or "UNSPECIFIED_CERTIFIED_TRADE"))
    return None


def classify_long_term_gap(signal: LongTermSignal, price: float) -> str:
    if price > signal.buy_range.max_buy_price:
        return "NO_EXECUTION_PENDING_CERTIFIED_RANGE_OR_EXPIRATION"
    if price < signal.buy_range.buy_range_lower:
        return "EXACT_SNAPSHOT_REVALIDATION_REQUIRED_NO_OLD_SIGNAL_FILL"
    return "IN_CERTIFIED_BUY_RANGE"


@dataclass(frozen=True)
class SwingSignal:
    ticker: str
    stable_security_id: str
    swing_signal_id: str
    signal_timestamp: str
    setup_type: str
    setup_state: str
    entry_range_lower: float
    entry_range_upper: float
    preferred_entry: float
    max_entry: float
    stop: float
    target_1: float
    target_2: float | None
    atr: float
    risk_per_share: float
    reward_risk: float
    trend_state: str
    rsi: float
    moving_average_state: str
    volume_confirmation: str
    relative_strength: float
    market_regime: str
    sector_state: str
    catalyst_context: Mapping[str, Any]
    signal_confidence: float
    long_term_action_at_signal_time: str
    long_term_signal_id: str | None
    long_term_reason_category: str | None
    long_term_swing_conflict: bool
    methodology_version: str
    execution_rule_version: str
    snapshot_digest: str
    evidence_ids: tuple[str, ...]
    expiration_sessions: int
    expiration_rule_version: str
    signal_kind: str = "SWING"


@dataclass(frozen=True)
class SwingExecution:
    execution_id: str
    swing_signal_id: str
    execution_timestamp: str
    execution_price: float
    stop_price: float
    position_size: int
    portfolio_equity: float
    risk_per_trade_percentage: float
    sizing_rule_version: str
    market_session: str = "REGULAR_HOURS"


def build_swing_signal(payload: Mapping[str, Any]) -> SwingSignal:
    setup_type = str(payload.get("setup_type") or "")
    if setup_type not in SWING_EXPIRATION_RULES:
        raise ValueError("SWING_SETUP_EXPIRATION_RULE_UNREGISTERED")
    required = (
        "ticker", "stable_security_id", "signal_timestamp", "setup_state", "entry_range_lower",
        "entry_range_upper", "preferred_entry", "max_entry", "stop", "target_1", "atr",
        "risk_per_share", "reward_risk", "trend_state", "rsi", "moving_average_state",
        "volume_confirmation", "relative_strength", "market_regime", "sector_state",
        "signal_confidence", "long_term_action_at_signal_time", "methodology_version",
        "snapshot_digest", "evidence_ids",
    )
    missing = [name for name in required if payload.get(name) in (None, "", (), [])]
    if missing:
        raise ValueError("MISSING_SWING_SIGNAL_FIELDS:" + ",".join(missing))
    timestamp = _aware(str(payload["signal_timestamp"]), "SWING_SIGNAL_TIMESTAMP")
    lower, preferred, upper, maximum = map(float, (
        payload["entry_range_lower"], payload["preferred_entry"],
        payload["entry_range_upper"], payload["max_entry"],
    ))
    if not 0 < lower <= preferred <= upper <= maximum:
        raise ValueError("INVALID_SWING_ENTRY_RANGE")
    sessions, expiration_version = SWING_EXPIRATION_RULES[setup_type]
    long_term_action = str(payload["long_term_action_at_signal_time"])
    swing_direction = str(payload["setup_state"])
    conflict = long_term_action == "AVOID" and swing_direction not in {"SHORT", "BEARISH"}
    identity = {
        "ticker": str(payload["ticker"]).upper(), "stable_security_id": payload["stable_security_id"],
        "timestamp": timestamp.isoformat(), "setup_type": setup_type,
        "snapshot_digest": payload["snapshot_digest"], "methodology_version": payload["methodology_version"],
    }
    return SwingSignal(
        identity["ticker"], str(identity["stable_security_id"]),
        str(payload.get("swing_signal_id") or _digest(identity)), timestamp.isoformat(), setup_type,
        swing_direction, lower, upper, preferred, maximum, float(payload["stop"]),
        float(payload["target_1"]), None if payload.get("target_2") is None else float(payload["target_2"]),
        float(payload["atr"]), float(payload["risk_per_share"]), float(payload["reward_risk"]),
        str(payload["trend_state"]), float(payload["rsi"]), str(payload["moving_average_state"]),
        str(payload["volume_confirmation"]), float(payload["relative_strength"]),
        str(payload["market_regime"]), str(payload["sector_state"]),
        dict(payload.get("catalyst_context") or {}), float(payload["signal_confidence"]),
        long_term_action, payload.get("long_term_signal_id"), payload.get("long_term_reason_category"),
        conflict, str(payload["methodology_version"]), SWING_EXECUTION_RULE_VERSION,
        str(payload["snapshot_digest"]), tuple(payload["evidence_ids"]), sessions, expiration_version,
    )


def swing_position_size(*, portfolio_equity: float, risk_per_trade_percentage: float,
                        entry_price: float, stop_price: float) -> int:
    if portfolio_equity <= 0 or not 0 < risk_per_trade_percentage <= 1:
        raise ValueError("INVALID_SWING_RISK_BUDGET")
    risk_per_share = abs(float(entry_price) - float(stop_price))
    if risk_per_share <= 0:
        raise ValueError("INVALID_SWING_RISK_PER_SHARE")
    return int((portfolio_equity * risk_per_trade_percentage) // risk_per_share)


def resolve_daily_bar_target_stop(*, low: float, high: float, stop: float,
                                  target: float) -> str:
    stop_hit, target_hit = low <= stop, high >= target
    if stop_hit and target_hit:
        return AMBIGUOUS_BAR_RULE
    if stop_hit:
        return "STOP_HIT"
    if target_hit:
        return "TARGET_HIT"
    return "NEITHER_HIT"


@dataclass(frozen=True)
class CorporateActionEvent:
    stable_security_id: str
    event_id: str
    event_type: str
    effective_timestamp: str
    old_ticker: str | None
    new_ticker: str | None
    terms: Mapping[str, Any]
    evidence_ids: tuple[str, ...]
    raw_hashes: tuple[str, ...]
    rule_version: str = CORPORATE_ACTION_RULE_VERSION


def build_corporate_action(payload: Mapping[str, Any]) -> CorporateActionEvent:
    supported = {"SPLIT", "DIVIDEND", "TICKER_CHANGE", "MERGER", "CASH_ACQUISITION",
                 "STOCK_ACQUISITION", "BANKRUPTCY", "DELISTING"}
    event_type = str(payload.get("event_type") or "")
    if event_type not in supported:
        raise ValueError("UNSUPPORTED_CORPORATE_ACTION")
    required = ("stable_security_id", "effective_timestamp", "evidence_ids", "raw_hashes")
    missing = [key for key in required if payload.get(key) in (None, "", (), [])]
    if missing:
        raise ValueError("INCOMPLETE_CORPORATE_ACTION:" + ",".join(missing))
    timestamp = _aware(str(payload["effective_timestamp"]), "CORPORATE_ACTION_TIMESTAMP")
    identity = {"stable_security_id": payload["stable_security_id"], "event_type": event_type,
                "effective_timestamp": timestamp.isoformat(), "terms": payload.get("terms") or {}}
    return CorporateActionEvent(
        str(payload["stable_security_id"]), str(payload.get("event_id") or _digest(identity)), event_type,
        timestamp.isoformat(), payload.get("old_ticker"), payload.get("new_ticker"),
        dict(payload.get("terms") or {}), tuple(payload["evidence_ids"]), tuple(payload["raw_hashes"]),
    )


def append_immutable(path: Path, record: Any, *, identity_field: str) -> bool:
    """Append any governed record once; outcomes can never rewrite history."""
    payload = asdict(record)
    identity = str(payload[identity_field])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            existing = json.loads(line)
            if str(existing.get(identity_field)) != identity:
                continue
            if json.dumps(existing, sort_keys=True) != json.dumps(payload, sort_keys=True):
                raise ValueError("IMMUTABLE_RECORD_CONFLICT")
            return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return True


def record_prospective_signal(path: Path, signal: LongTermSignal | SwingSignal) -> bool:
    if not REPORT_CARD_PROSPECTIVE_ACTIVE:
        raise PermissionError("REPORT_CARD_PROSPECTIVE_INACTIVE")
    identity = "signal_id" if isinstance(signal, LongTermSignal) else "swing_signal_id"
    return append_immutable(path, signal, identity_field=identity)


def record_prospective_execution(path: Path, execution: LongTermExecution | SwingExecution) -> bool:
    if not REPORT_CARD_PROSPECTIVE_ACTIVE:
        raise PermissionError("REPORT_CARD_PROSPECTIVE_INACTIVE")
    return append_immutable(path, execution, identity_field="execution_id")


def open_model_portfolio_position(*_args: Any, **_kwargs: Any) -> None:
    if not REPORT_CARD_PROSPECTIVE_ACTIVE:
        raise PermissionError("REPORT_CARD_PROSPECTIVE_INACTIVE")
    raise NotImplementedError("MODEL_PORTFOLIO_ACTIVATION_REQUIRES_SEPARATE_GOVERNANCE")


def public_report_allowed() -> bool:
    return False


def pipeline_public_message(state: PipelineState) -> str:
    if state is PipelineState.NO_QUALIFYING_SIGNALS:
        return "ATLAS completed evaluation; no qualifying signals were certified."
    if state is PipelineState.COMPLETE_WITH_SIGNALS:
        return "ATLAS completed evaluation with certified signals."
    return "ATLAS evaluation is unavailable or incomplete."


__all__ = [
    "AMBIGUOUS_BAR_RULE", "BUY_RANGE_RULE_VERSION", "CORPORATE_ACTION_RULE_VERSION",
    "CorporateActionEvent", "ExchangeCalendar", "GOVERNANCE_VERSION", "GovernedCeiling",
    "LONG_TERM_EXECUTION_RULE_VERSION", "LONG_TERM_EXPIRATION_RULE_VERSION", "LONG_TERM_HORIZONS",
    "LongTermBuyRange", "LongTermExecution", "LongTermSignal", "LongTermTerminalState",
    "MODEL_PORTFOLIO_FILL_ASSUMPTION", "PORTFOLIO_CAPACITY_RULE_VERSION", "PipelineState",
    "PositionExitType", "REPORT_CARD_ACTIVATION_READY",
    "REPORT_CARD_PROSPECTIVE_ACTIVE",
    "SWING_HORIZONS", "SignalLifecycleEvent", "SignalOutcome", "SwingExecution", "SwingSignal",
    "SwingTerminalState", "append_immutable", "assert_signal_may_execute", "build_position_exit",
    "build_corporate_action", "build_long_term_buy_range", "build_long_term_signal",
    "build_swing_signal",
    "classify_long_term_gap", "evaluate_portfolio_capacity", "first_qualifying_long_term_execution",
    "pipeline_public_message", "portfolio_performance_population",
    "open_model_portfolio_position", "public_report_allowed", "record_prospective_execution",
    "record_prospective_signal", "resolve_daily_bar_target_stop", "signal_quality_population",
    "summarize_signal_outcomes", "swing_position_size",
]
