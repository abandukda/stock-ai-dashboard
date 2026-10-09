"""Prospectively frozen, structured thesis conditions for shadow management."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from services.position_management import ThesisState


ALLOWED_CONDITION_TYPES = frozenset({"HARD_BREAK", "MATERIAL_WEAKNESS"})
ALLOWED_CURRENT_STATES = frozenset({"PASS", "FAIL", "UNAVAILABLE"})


@dataclass(frozen=True)
class ThesisCondition:
    thesis_condition_id: str
    condition_type: str
    issuance_value: Any
    threshold_or_condition: str
    current_state: str
    triggered_at: str | None
    source_evidence: tuple[str, ...]
    methodology_version: str
    frozen_at: str

    def __post_init__(self) -> None:
        if self.condition_type not in ALLOWED_CONDITION_TYPES:
            raise ValueError("THESIS_CONDITION_TYPE_INVALID")
        if self.current_state not in ALLOWED_CURRENT_STATES:
            raise ValueError("THESIS_CONDITION_STATE_INVALID")
        if not self.thesis_condition_id or not self.threshold_or_condition or not self.source_evidence:
            raise ValueError("THESIS_CONDITION_INCOMPLETE")


def freeze_thesis_conditions(*, signal_id: str, frozen_at: str,
                             methodology_version: str,
                             conditions: Sequence[Mapping[str, Any]]) -> tuple[ThesisCondition, ...]:
    frozen: list[ThesisCondition] = []
    for index, raw in enumerate(conditions):
        if str(raw.get("assignment_authority") or "STRUCTURED_RULE") != "STRUCTURED_RULE":
            raise ValueError("AI_THESIS_ASSIGNMENT_FORBIDDEN")
        identity = {"signal_id": signal_id, "index": index, "condition_type": raw.get("condition_type"),
                    "threshold": raw.get("threshold_or_condition"), "methodology_version": methodology_version}
        condition_id = "thesis:" + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        frozen.append(ThesisCondition(
            thesis_condition_id=condition_id, condition_type=str(raw.get("condition_type") or ""),
            issuance_value=raw.get("issuance_value"),
            threshold_or_condition=str(raw.get("threshold_or_condition") or ""),
            current_state="PASS", triggered_at=None,
            source_evidence=tuple(sorted(str(item) for item in raw.get("source_evidence") or () if item)),
            methodology_version=methodology_version, frozen_at=frozen_at,
        ))
    return tuple(frozen)


def classify_thesis(conditions: Sequence[ThesisCondition]) -> ThesisState:
    if not conditions or any(item.current_state == "UNAVAILABLE" for item in conditions):
        return ThesisState.UNAVAILABLE
    if any(item.condition_type == "HARD_BREAK" and item.current_state == "FAIL" for item in conditions):
        return ThesisState.BROKEN
    if any(item.condition_type == "MATERIAL_WEAKNESS" and item.current_state == "FAIL" for item in conditions):
        return ThesisState.WEAKENED
    return ThesisState.INTACT


def condition_payload(condition: ThesisCondition) -> dict[str, Any]:
    return asdict(condition)


__all__ = ["ThesisCondition", "classify_thesis", "condition_payload", "freeze_thesis_conditions"]
