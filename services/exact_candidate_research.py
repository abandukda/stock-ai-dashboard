"""Fail-closed Research submission planning for exact-candidate QA."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping


EXACT_CANDIDATE_QA_ENV = "ATLAS_EXACT_CANDIDATE_QA"
CERTIFIED_IMMEDIATE = "CERTIFIED_IMMEDIATE"
CERTIFIED_RECORD_MISSING = "CERTIFIED_RECORD_MISSING"
LIVE_RESEARCH = "LIVE_RESEARCH"


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

