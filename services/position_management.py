"""Deterministic, shadow-only position-management methodology.

This module answers a different question from discovery: how the current
certified evidence changes forward risk/reward for an already-owned position.
It never changes the canonical discovery Action or any customer publication.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "position_management_v1.json"


class ThesisState(StrEnum):
    INTACT = "INTACT"
    WEAKENED = "WEAKENED"
    BROKEN = "BROKEN"
    UNAVAILABLE = "UNAVAILABLE"


class ValuationState(StrEnum):
    ATTRACTIVE = "ATTRACTIVE"
    FAIR = "FAIR"
    STRETCHED = "STRETCHED"
    ABOVE_FV = "ABOVE_FV"
    UNAVAILABLE = "UNAVAILABLE"


class TechnicalState(StrEnum):
    HEALTHY = "HEALTHY"
    DETERIORATING = "DETERIORATING"
    BROKEN = "BROKEN"
    UNAVAILABLE = "UNAVAILABLE"


class DataCertainty(StrEnum):
    CERTIFIED = "CERTIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class PositionInstruction(StrEnum):
    HOLD = "HOLD"
    HOLD_NO_ADD = "HOLD_NO_ADD"
    TRIM = "TRIM"
    EXIT = "EXIT"
    SUSPENDED = "SUSPENDED"


class ReasonCode(StrEnum):
    THESIS_INTACT = "THESIS_INTACT"
    THESIS_BROKEN_STRUCTURED_CONDITION = "THESIS_BROKEN_STRUCTURED_CONDITION"
    THESIS_BROKEN_GUIDANCE = "THESIS_BROKEN_GUIDANCE"
    THESIS_BROKEN_BALANCE_SHEET = "THESIS_BROKEN_BALANCE_SHEET"
    THESIS_WEAKENED_ESTIMATES = "THESIS_WEAKENED_ESTIMATES"
    VALUATION_ATTRACTIVE = "VALUATION_ATTRACTIVE"
    VALUATION_FAIR = "VALUATION_FAIR"
    VALUATION_STRETCHED = "VALUATION_STRETCHED"
    VALUATION_ABOVE_UPPER_BAND = "VALUATION_ABOVE_UPPER_BAND"
    VALUATION_CONFIDENCE_UNAVAILABLE = "VALUATION_CONFIDENCE_UNAVAILABLE"
    VALUATION_PERSISTENCE_PENDING = "VALUATION_PERSISTENCE_PENDING"
    TECHNICAL_HEALTHY = "TECHNICAL_HEALTHY"
    TECHNICAL_DETERIORATION = "TECHNICAL_DETERIORATION"
    TECHNICAL_BREAK = "TECHNICAL_BREAK"
    DATA_UNCERTAIN = "DATA_UNCERTAIN"
    EVENT_REVIEW_PENDING = "EVENT_REVIEW_PENDING"
    VALUATION_BASIS_CHANGED = "VALUATION_BASIS_CHANGED"
    CURRENT_ACTION_BUY_NOW = "CURRENT_ACTION_BUY_NOW"
    CURRENT_ACTION_BUILD = "CURRENT_ACTION_BUILD"
    ADD_BLOCKED_BY_ACTION = "ADD_BLOCKED_BY_ACTION"
    ADD_BLOCKED_BY_REVIEW = "ADD_BLOCKED_BY_REVIEW"
    PROTECTED_ADD_RISK_GATE = "PROTECTED_ADD_RISK_GATE"
    UNDEFINED_RULE_COMBINATION = "UNDEFINED_RULE_COMBINATION"


def load_methodology(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {"methodology_version", "rule_table_version", "valuation_persistence_scans",
                "episode_end_confirmation_scans", "reentry_hysteresis_regular_sessions"}
    if not required.issubset(config) or config.get("customer_visible") is not False:
        raise ValueError("POSITION_METHODOLOGY_INVALID")
    return config


def _digest(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class FairValueBand:
    lower: float
    base: float
    upper: float
    confidence: float | None
    methodology_version: str

    def __post_init__(self) -> None:
        if not (0 < self.lower <= self.base <= self.upper):
            raise ValueError("FAIR_VALUE_BAND_INVALID")
        if not self.methodology_version:
            raise ValueError("VALUATION_METHODOLOGY_VERSION_REQUIRED")


@dataclass(frozen=True)
class PersistenceState:
    trigger: str | None = None
    count: int = 0
    first_triggered_at: str | None = None
    confirmed_at: str | None = None


@dataclass(frozen=True)
class ShadowDecision:
    methodology_version: str
    rule_table_version: str
    thesis_state: str
    valuation_state: str
    technical_state: str
    data_certainty: str
    instruction: str
    add_eligible: bool
    review_required: bool
    review_reason_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    persistence_scan_count: int
    first_triggered_at: str | None
    confirmed_at: str | None
    inputs_digest: str
    customer_visible: bool = False


def classify_valuation(price: Any, band: FairValueBand | None) -> ValuationState:
    try:
        current = float(price)
    except (TypeError, ValueError):
        return ValuationState.UNAVAILABLE
    if band is None or current <= 0 or band.confidence is None:
        return ValuationState.UNAVAILABLE
    try:
        confidence = float(band.confidence)
    except (TypeError, ValueError):
        return ValuationState.UNAVAILABLE
    if not 0 <= confidence <= 100:
        return ValuationState.UNAVAILABLE
    if current < band.lower:
        return ValuationState.ATTRACTIVE
    if current <= band.base:
        return ValuationState.FAIR
    if current <= band.upper:
        return ValuationState.STRETCHED
    return ValuationState.ABOVE_FV


def advance_persistence(*, trigger: str, scan_timestamp: str, previous: PersistenceState | None,
                        required_scans: int) -> PersistenceState:
    previous = previous or PersistenceState()
    count = previous.count + 1 if previous.trigger == trigger else 1
    first = previous.first_triggered_at if previous.trigger == trigger else scan_timestamp
    confirmed = previous.confirmed_at if previous.trigger == trigger else None
    if count >= required_scans and confirmed is None:
        confirmed = scan_timestamp
    return PersistenceState(trigger=trigger, count=count, first_triggered_at=first, confirmed_at=confirmed)


def evaluate_shadow_position(*, thesis_state: ThesisState, valuation_state: ValuationState,
                             technical_state: TechnicalState, data_certainty: DataCertainty,
                             current_action: str, scan_timestamp: str,
                             persistence: PersistenceState | None = None,
                             review_reason_codes: Sequence[str] = (), valuation_basis_changed: bool = False,
                             protected_add_blocked: bool = False, valuation_confidence_available: bool = True,
                             config: Mapping[str, Any] | None = None) -> ShadowDecision:
    cfg = dict(config or load_methodology())
    try:
        reviews = {ReasonCode(str(item)).value for item in review_reason_codes if item}
    except ValueError as exc:
        raise ValueError("UNKNOWN_POSITION_REASON_CODE") from exc
    reasons: list[str] = []
    instruction = PositionInstruction.SUSPENDED
    add_eligible = False

    certainty = data_certainty
    if valuation_basis_changed:
        certainty = DataCertainty.REVIEW_REQUIRED
        reviews.add(ReasonCode.VALUATION_BASIS_CHANGED.value)
    if ReasonCode.EVENT_REVIEW_PENDING.value in reviews:
        certainty = DataCertainty.REVIEW_REQUIRED
    if not valuation_confidence_available:
        valuation_state = ValuationState.UNAVAILABLE
        certainty = DataCertainty.REVIEW_REQUIRED
        reviews.add(ReasonCode.VALUATION_CONFIDENCE_UNAVAILABLE.value)
    if thesis_state == ThesisState.UNAVAILABLE or technical_state == TechnicalState.UNAVAILABLE:
        certainty = DataCertainty.REVIEW_REQUIRED
        reviews.add(ReasonCode.DATA_UNCERTAIN.value)
    if valuation_state == ValuationState.UNAVAILABLE and thesis_state != ThesisState.BROKEN:
        certainty = DataCertainty.REVIEW_REQUIRED
        if valuation_confidence_available:
            reviews.add(ReasonCode.DATA_UNCERTAIN.value)

    next_persistence = persistence or PersistenceState()
    protected_valuation = valuation_state.value in set(cfg["transitions_requiring_persistence"])
    if protected_valuation and thesis_state != ThesisState.BROKEN:
        next_persistence = advance_persistence(
            trigger=valuation_state.value, scan_timestamp=scan_timestamp, previous=persistence,
            required_scans=int(cfg["valuation_persistence_scans"]),
        )
        if next_persistence.confirmed_at is None:
            certainty = DataCertainty.REVIEW_REQUIRED
            reviews.add(ReasonCode.VALUATION_PERSISTENCE_PENDING.value)

    # Lexicographic precedence: certainty, thesis break, valuation, technical,
    # then discovery Action solely for derived ADD eligibility.
    if certainty != DataCertainty.CERTIFIED:
        instruction = PositionInstruction.SUSPENDED
        reasons.extend(sorted(reviews or {ReasonCode.DATA_UNCERTAIN.value}))
    elif thesis_state == ThesisState.BROKEN:
        instruction = PositionInstruction.EXIT
        reasons.append(ReasonCode.THESIS_BROKEN_STRUCTURED_CONDITION.value)
    elif thesis_state == ThesisState.WEAKENED:
        if valuation_state in {ValuationState.ATTRACTIVE, ValuationState.FAIR}:
            instruction = PositionInstruction.HOLD_NO_ADD
            reasons.extend((ReasonCode.THESIS_WEAKENED_ESTIMATES.value, ReasonCode(f"VALUATION_{valuation_state.value}").value))
        elif valuation_state in {ValuationState.STRETCHED, ValuationState.ABOVE_FV}:
            instruction = PositionInstruction.TRIM
            value_reason = (ReasonCode.VALUATION_ABOVE_UPPER_BAND if valuation_state == ValuationState.ABOVE_FV
                            else ReasonCode.VALUATION_STRETCHED)
            reasons.extend((ReasonCode.THESIS_WEAKENED_ESTIMATES.value, value_reason.value))
    elif thesis_state == ThesisState.INTACT:
        if valuation_state in {ValuationState.ATTRACTIVE, ValuationState.FAIR}:
            if technical_state == TechnicalState.HEALTHY:
                instruction = PositionInstruction.HOLD
                reasons.extend((ReasonCode.THESIS_INTACT.value, ReasonCode(f"VALUATION_{valuation_state.value}").value,
                                ReasonCode.TECHNICAL_HEALTHY.value))
                add_eligible = current_action in set(cfg["add_eligible_actions"]) and not protected_add_blocked
                if add_eligible:
                    reasons.append((ReasonCode.CURRENT_ACTION_BUY_NOW if current_action == "BUY_NOW"
                                    else ReasonCode.CURRENT_ACTION_BUILD).value)
                else:
                    reasons.append(ReasonCode.ADD_BLOCKED_BY_ACTION.value)
            elif technical_state in {TechnicalState.DETERIORATING, TechnicalState.BROKEN}:
                instruction = PositionInstruction.HOLD_NO_ADD
                technical_reason = (ReasonCode.TECHNICAL_BREAK if technical_state == TechnicalState.BROKEN
                                    else ReasonCode.TECHNICAL_DETERIORATION)
                reviews.add(technical_reason.value)
                reasons.extend((ReasonCode.THESIS_INTACT.value, ReasonCode(f"VALUATION_{valuation_state.value}").value,
                                technical_reason.value))
        elif valuation_state == ValuationState.STRETCHED:
            instruction = PositionInstruction.HOLD_NO_ADD if technical_state == TechnicalState.HEALTHY else PositionInstruction.TRIM
            technical_reason = (ReasonCode.TECHNICAL_HEALTHY if technical_state == TechnicalState.HEALTHY
                                else ReasonCode.TECHNICAL_BREAK if technical_state == TechnicalState.BROKEN
                                else ReasonCode.TECHNICAL_DETERIORATION)
            reasons.extend((ReasonCode.THESIS_INTACT.value, ReasonCode.VALUATION_STRETCHED.value,
                            technical_reason.value))
            if technical_state != TechnicalState.HEALTHY:
                reviews.add(technical_reason.value)
        elif valuation_state == ValuationState.ABOVE_FV:
            instruction = PositionInstruction.TRIM
            reasons.extend((ReasonCode.THESIS_INTACT.value, ReasonCode.VALUATION_ABOVE_UPPER_BAND.value))

    if not reasons:
        instruction = PositionInstruction.SUSPENDED
        reviews.add(ReasonCode.UNDEFINED_RULE_COMBINATION.value)
        reasons.append(ReasonCode.UNDEFINED_RULE_COMBINATION.value)
    if protected_add_blocked:
        add_eligible = False
        reasons.append(ReasonCode.PROTECTED_ADD_RISK_GATE.value)

    inputs = {
        "thesis_state": thesis_state.value, "valuation_state": valuation_state.value,
        "technical_state": technical_state.value, "data_certainty": certainty.value,
        "current_action": current_action, "scan_timestamp": scan_timestamp,
        "valuation_basis_changed": valuation_basis_changed, "protected_add_blocked": protected_add_blocked,
        "valuation_confidence_available": valuation_confidence_available,
        "persistence": asdict(next_persistence), "review_reason_codes": sorted(reviews),
        "methodology_version": cfg["methodology_version"], "rule_table_version": cfg["rule_table_version"],
    }
    return ShadowDecision(
        methodology_version=cfg["methodology_version"], rule_table_version=cfg["rule_table_version"],
        thesis_state=thesis_state.value, valuation_state=valuation_state.value,
        technical_state=technical_state.value, data_certainty=certainty.value,
        instruction=instruction.value, add_eligible=add_eligible,
        review_required=bool(reviews) or certainty != DataCertainty.CERTIFIED,
        review_reason_codes=tuple(sorted(reviews)), reason_codes=tuple(reasons),
        persistence_scan_count=next_persistence.count, first_triggered_at=next_persistence.first_triggered_at,
        confirmed_at=next_persistence.confirmed_at, inputs_digest=_digest(inputs),
    )


def episode_transition(*, current_action: str, prior_outside_count: int, scan_timestamp: str,
                       first_out_of_buy_now_at: str | None = None,
                       hard_exit: bool = False, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or load_methodology())
    if hard_exit:
        return {"status": "ENDED", "first_out_of_buy_now_at": first_out_of_buy_now_at or scan_timestamp,
                "confirmation_count": int(cfg["episode_end_confirmation_scans"]),
                "confirmed_episode_end_at": scan_timestamp}
    if current_action == "BUY_NOW":
        return {"status": "OPEN", "first_out_of_buy_now_at": None, "confirmation_count": 0,
                "confirmed_episode_end_at": None}
    count = prior_outside_count + 1
    required = int(cfg["episode_end_confirmation_scans"])
    first_out = first_out_of_buy_now_at or scan_timestamp
    return {"status": "ENDED" if count >= required else "PENDING_END",
            "first_out_of_buy_now_at": first_out,
            "confirmation_count": count,
            "confirmed_episode_end_at": scan_timestamp if count >= required else None}


def reentry_allowed(*, prior_episode_confirmed_ended: bool, consecutive_regular_sessions_outside_buy_now: int,
                    current_action: str, config: Mapping[str, Any] | None = None) -> bool:
    cfg = dict(config or load_methodology())
    return (prior_episode_confirmed_ended and current_action == "BUY_NOW" and
            consecutive_regular_sessions_outside_buy_now >= int(cfg["reentry_hysteresis_regular_sessions"]))


__all__ = ["DataCertainty", "FairValueBand", "PersistenceState", "PositionInstruction", "ReasonCode", "ShadowDecision",
           "TechnicalState", "ThesisState", "ValuationState", "advance_persistence", "classify_valuation",
           "episode_transition", "evaluate_shadow_position", "load_methodology", "reentry_allowed"]
