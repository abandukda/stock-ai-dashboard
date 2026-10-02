"""Fail-closed Research submission planning for exact-candidate QA."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping


EXACT_CANDIDATE_QA_ENV = "ATLAS_EXACT_CANDIDATE_QA"
CERTIFIED_IMMEDIATE = "CERTIFIED_IMMEDIATE"
CERTIFIED_RECORD_MISSING = "CERTIFIED_RECORD_MISSING"
LIVE_RESEARCH = "LIVE_RESEARCH"
EXACT_RESEARCH_SESSION_KEY = "atlas_exact_candidate_research"
PUBLISHED_RESEARCH_COMPLETE = "PUBLISHED_RESEARCH_COMPLETE"


@dataclass(frozen=True)
class ResearchSubmissionPlan:
    mode: str
    certified_record: dict[str, Any] | None

    @property
    def provider_calls_allowed(self) -> bool:
        return self.mode == LIVE_RESEARCH


def exact_candidate_qa_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(EXACT_CANDIDATE_QA_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def research_submission_plan(
    saved_record: Mapping[str, Any] | None,
    *,
    environ: Mapping[str, str] | None = None,
) -> ResearchSubmissionPlan:
    """Choose the Research binding path without changing the certified record."""
    if not exact_candidate_qa_enabled(environ):
        return ResearchSubmissionPlan(LIVE_RESEARCH, None)
    if not isinstance(saved_record, Mapping) or not saved_record:
        return ResearchSubmissionPlan(CERTIFIED_RECORD_MISSING, None)
    return ResearchSubmissionPlan(CERTIFIED_IMMEDIATE, dict(saved_record))


def persist_certified_research(
    session_state: dict[str, Any], ticker: str, certified_record: Mapping[str, Any]
) -> dict[str, Any]:
    """Persist one exact-candidate result across Streamlit reruns."""
    normalized = str(ticker or "").strip().upper()
    state = {
        "ticker": normalized,
        "certified_record": dict(certified_record),
        "lifecycle": PUBLISHED_RESEARCH_COMPLETE,
        "provider_calls": 0,
    }
    session_state[EXACT_RESEARCH_SESSION_KEY] = state
    session_state["active_research_ticker"] = normalized
    session_state["research_status"] = "complete"
    session_state["research_error"] = ""
    return state


def persisted_certified_research(
    session_state: Mapping[str, Any], ticker: str | None = None
) -> dict[str, Any] | None:
    state = session_state.get(EXACT_RESEARCH_SESSION_KEY)
    if not isinstance(state, Mapping):
        return None
    normalized = str(state.get("ticker") or "").strip().upper()
    requested = str(ticker or "").strip().upper()
    if not normalized or (requested and requested != normalized):
        return None
    if state.get("lifecycle") != PUBLISHED_RESEARCH_COMPLETE:
        return None
    record = state.get("certified_record")
    if not isinstance(record, Mapping) or not record:
        return None
    return {
        "ticker": normalized,
        "certified_record": dict(record),
        "lifecycle": PUBLISHED_RESEARCH_COMPLETE,
        "provider_calls": 0,
    }


def clear_persisted_certified_research(session_state: dict[str, Any]) -> None:
    session_state.pop(EXACT_RESEARCH_SESSION_KEY, None)
