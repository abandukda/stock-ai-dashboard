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
    confidence: float
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
    if band is None or current <= 0:
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
                             protected_add_blocked: bool = False,
                             config: Mapping[str, Any] | None = None) -> ShadowDecision:
    cfg = dict(config or load_methodology())
    reviews = {str(item) for item in review_reason_codes if item}
    reasons: list[str] = []
    instruction = PositionInstruction.SUSPENDED
    add_eligible = False

    certainty = data_certainty
    if valuation_basis_changed:
        certainty = DataCertainty.REVIEW_REQUIRED
        reviews.add("VALUATION_BASIS_CHANGED")
    if thesis_state == ThesisState.UNAVAILABLE or valuation_state == ValuationState.UNAVAILABLE or technical_state == TechnicalState.UNAVAILABLE:
        certainty = DataCertainty.REVIEW_REQUIRED
        reviews.add("DATA_UNCERTAIN")

    next_persistence = persistence or PersistenceState()
    protected_valuation = valuation_state.value in set(cfg["transitions_requiring_persistence"])
    if protected_valuation:
        next_persistence = advance_persistence(
            trigger=valuation_state.value, scan_timestamp=scan_timestamp, previous=persistence,
            required_scans=int(cfg["valuation_persistence_scans"]),
        )
        if next_persistence.confirmed_at is None:
            certainty = DataCertainty.REVIEW_REQUIRED
            reviews.add("VALUATION_PERSISTENCE_PENDING")

    # Lexicographic precedence: certainty, thesis break, valuation, technical,
    # then discovery Action solely for derived ADD eligibility.
    if certainty != DataCertainty.CERTIFIED:
        instruction = PositionInstruction.SUSPENDED
        reasons.append("DATA_CERTAINTY_REVIEW_REQUIRED")
    elif thesis_state == ThesisState.BROKEN:
        instruction = PositionInstruction.EXIT
        reasons.append("THESIS_BROKEN")
    elif thesis_state == ThesisState.WEAKENED:
        if valuation_state in {ValuationState.ATTRACTIVE, ValuationState.FAIR}:
            instruction = PositionInstruction.HOLD_NO_ADD
            reasons.extend(("THESIS_WEAKENED", f"VALUATION_{valuation_state.value}"))
        elif valuation_state in {ValuationState.STRETCHED, ValuationState.ABOVE_FV}:
            instruction = PositionInstruction.TRIM
            reasons.extend(("THESIS_WEAKENED", f"VALUATION_{valuation_state.value}"))
    elif thesis_state == ThesisState.INTACT:
        if valuation_state in {ValuationState.ATTRACTIVE, ValuationState.FAIR}:
            if technical_state == TechnicalState.HEALTHY:
                instruction = PositionInstruction.HOLD
                reasons.extend(("THESIS_INTACT", f"VALUATION_{valuation_state.value}", "TECHNICAL_HEALTHY"))
                add_eligible = current_action in set(cfg["add_eligible_actions"]) and not protected_add_blocked
                if add_eligible:
                    reasons.append(f"CURRENT_ACTION_{current_action}")
            elif technical_state in {TechnicalState.DETERIORATING, TechnicalState.BROKEN}:
                instruction = PositionInstruction.HOLD_NO_ADD
                reviews.add("TECHNICAL_BREAK" if technical_state == TechnicalState.BROKEN else "TECHNICAL_DETERIORATION")
                reasons.extend(("THESIS_INTACT", f"VALUATION_{valuation_state.value}", f"TECHNICAL_{technical_state.value}"))
        elif valuation_state == ValuationState.STRETCHED:
            instruction = PositionInstruction.HOLD_NO_ADD if technical_state == TechnicalState.HEALTHY else PositionInstruction.TRIM
            reasons.extend(("THESIS_INTACT", "VALUATION_STRETCHED", f"TECHNICAL_{technical_state.value}"))
        elif valuation_state == ValuationState.ABOVE_FV:
            instruction = PositionInstruction.TRIM
            reasons.extend(("THESIS_INTACT", "VALUATION_ABOVE_UPPER_BAND"))

    if not reasons:
        instruction = PositionInstruction.SUSPENDED
        reviews.add("UNDEFINED_RULE_COMBINATION")
        reasons.append("FAIL_CLOSED_UNDEFINED_COMBINATION")
    if protected_add_blocked:
        add_eligible = False
        reasons.append("PROTECTED_ADD_RISK_GATE")

    inputs = {
        "thesis_state": thesis_state.value, "valuation_state": valuation_state.value,
        "technical_state": technical_state.value, "data_certainty": certainty.value,
        "current_action": current_action, "scan_timestamp": scan_timestamp,
        "valuation_basis_changed": valuation_basis_changed, "protected_add_blocked": protected_add_blocked,
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
                       hard_exit: bool = False, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or load_methodology())
    if hard_exit:
        return {"status": "ENDED", "first_out_of_buy_now_at": scan_timestamp,
                "confirmation_count": int(cfg["episode_end_confirmation_scans"]),
                "confirmed_episode_end_at": scan_timestamp}
    if current_action == "BUY_NOW":
        return {"status": "OPEN", "first_out_of_buy_now_at": None, "confirmation_count": 0,
                "confirmed_episode_end_at": None}
    count = prior_outside_count + 1
    required = int(cfg["episode_end_confirmation_scans"])
    return {"status": "ENDED" if count >= required else "PENDING_END",
            "first_out_of_buy_now_at": scan_timestamp if prior_outside_count == 0 else None,
            "confirmation_count": count,
            "confirmed_episode_end_at": scan_timestamp if count >= required else None}


def reentry_allowed(*, prior_episode_confirmed_ended: bool, consecutive_regular_sessions_outside_buy_now: int,
                    current_action: str, config: Mapping[str, Any] | None = None) -> bool:
    cfg = dict(config or load_methodology())
    return (prior_episode_confirmed_ended and current_action == "BUY_NOW" and
            consecutive_regular_sessions_outside_buy_now >= int(cfg["reentry_hysteresis_regular_sessions"]))


__all__ = ["DataCertainty", "FairValueBand", "PersistenceState", "PositionInstruction", "ShadowDecision",
           "TechnicalState", "ThesisState", "ValuationState", "advance_persistence", "classify_valuation",
           "episode_transition", "evaluate_shadow_position", "load_methodology", "reentry_allowed"]
