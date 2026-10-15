"""Fail-closed acceptance helpers for the R3 AI-first customer experience.

These checks evaluate supplied evidence only.  They do not render the product,
call a provider, or turn an automated result into a human visual-acceptance
decision.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any


REQUIRED_VIEWPORTS = {
    "desktop_1440": (1440, 1000),
    "mobile_390": (390, 844),
    "mobile_360": (360, 800),
}
REQUIRED_HOME_STATES = (
    "home_ai_first_opening",
    "home_top_ideas",
    "home_secondary_intelligence",
)
REQUIRED_USEFULNESS_FIELDS = (
    "bottom_line",
    "reasons",
    "risks",
    "strengthen",
    "weaken",
    "invalidate",
    "what_to_watch",
    "freshness",
)
_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\$?\d[\d,.]*(?:%|x|[BMK])?(?![A-Za-z])")
_TOKEN = re.compile(r"[a-z0-9]+")


def validate_screenshot_manifest(
    entries: Sequence[Mapping[str, Any]], *, exact_sha: str
) -> list[str]:
    """Require original, distinct evidence at 1440, 390 and 360 widths."""
    failures: list[str] = []
    by_key = {(str(e.get("state")), str(e.get("viewport"))): e for e in entries}
    for state in REQUIRED_HOME_STATES:
        for viewport, dimensions in REQUIRED_VIEWPORTS.items():
            item = by_key.get((state, viewport))
            if not item:
                failures.append(f"MISSING_SCREENSHOT:{state}:{viewport}")
                continue
            if str(item.get("source_sha")) != exact_sha:
                failures.append(f"SOURCE_SHA_MISMATCH:{state}:{viewport}")
            actual = (item.get("width"), item.get("height"))
            if actual != dimensions:
                failures.append(f"DIMENSION_MISMATCH:{state}:{viewport}:{actual}")
            if item.get("horizontal_overflow") is not False:
                failures.append(f"HORIZONTAL_OVERFLOW:{state}:{viewport}")
            if item.get("exception") is not False:
                failures.append(f"RENDER_EXCEPTION:{state}:{viewport}")
    required = [by_key.get((s, v)) for s in REQUIRED_HOME_STATES for v in REQUIRED_VIEWPORTS]
    present = [e for e in required if e]
    for field in ("path", "sha256"):
        values = [str(e.get(field) or "") for e in present]
        if any(not value for value in values):
            failures.append(f"SCREENSHOT_{field.upper()}_MISSING")
        if len(set(values)) != len(values):
            failures.append(f"SCREENSHOT_{field.upper()}_NOT_UNIQUE")
    return failures


def validate_source_grounding(
    claims: Sequence[Mapping[str, Any]], *, allowed_field_ids: Iterable[str],
    allowed_evidence_ids: Iterable[str],
) -> list[str]:
    """Require every supplied customer claim to bind to authoritative IDs."""
    fields = set(allowed_field_ids)
    evidence = set(allowed_evidence_ids)
    failures: list[str] = []
    for index, claim in enumerate(claims):
        text = str(claim.get("text") or "").strip()
        field_ids = {str(v) for v in claim.get("field_ids") or () if v}
        evidence_ids = {str(v) for v in claim.get("evidence_ids") or () if v}
        if not text:
            failures.append(f"EMPTY_CLAIM:{index}")
            continue
        if not field_ids or not evidence_ids:
            failures.append(f"UNGROUNDED_CLAIM:{index}")
        if field_ids - fields:
            failures.append(f"UNKNOWN_FIELD_ID:{index}")
        if evidence_ids - evidence:
            failures.append(f"UNKNOWN_EVIDENCE_ID:{index}")
        if _NUMBER.search(text) and not field_ids:
            failures.append(f"UNGROUNDED_NUMERIC_CLAIM:{index}")
    return failures


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower()))


def narrative_distinctness(narratives: Mapping[str, str], *, max_jaccard: float = 0.72) -> tuple[float, list[str]]:
    """Return worst pairwise overlap and fail near-copy ticker narratives."""
    keys = sorted(narratives)
    worst = 0.0
    failures: list[str] = []
    for index, left in enumerate(keys):
        for right in keys[index + 1:]:
            left_tokens, right_tokens = _tokens(narratives[left]), _tokens(narratives[right])
            union = left_tokens | right_tokens
            score = len(left_tokens & right_tokens) / len(union) if union else 1.0
            worst = max(worst, score)
            if score > max_jaccard:
                failures.append(f"NARRATIVE_NEAR_DUPLICATE:{left}:{right}:{score:.3f}")
    return worst, failures


def validate_readability(text: str, *, max_words: int = 120, max_sentence_words: int = 32) -> list[str]:
    words = text.split()
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    failures: list[str] = []
    if not words:
        return ["NARRATIVE_EMPTY"]
    if len(words) > max_words:
        failures.append(f"NARRATIVE_TOO_LONG:{len(words)}")
    if sentences and max(len(sentence.split()) for sentence in sentences) > max_sentence_words:
        failures.append("SENTENCE_TOO_LONG")
    return failures


def validate_usefulness(record: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    for field in REQUIRED_USEFULNESS_FIELDS:
        value = record.get(field)
        if value is None or value == "" or value == []:
            failures.append(f"USEFULNESS_FIELD_MISSING:{field}")
    reasons = record.get("reasons") or []
    if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes)) or not (1 <= len(reasons) <= 3):
        failures.append("REASONS_MUST_BE_ONE_TO_THREE")
    bottom_line = str(record.get("bottom_line") or "")
    sentences = [s for s in re.split(r"[.!?]+", bottom_line) if s.strip()]
    if not (1 <= len(sentences) <= 2):
        failures.append("BOTTOM_LINE_MUST_BE_ONE_OR_TWO_SENTENCES")
    return failures


def human_acceptance_status(results: Sequence[Mapping[str, Any]]) -> tuple[str, list[str]]:
    """Validate evidence completeness; never manufacture a human PASS."""
    failures: list[str] = []
    people = {str(row.get("participant_id") or "") for row in results}
    if len(results) != 5 or len(people - {""}) != 5:
        failures.append("FIVE_UNIQUE_PARTICIPANTS_REQUIRED")
    for index, row in enumerate(results):
        if row.get("completed") is not True:
            failures.append(f"PARTICIPANT_INCOMPLETE:{index}")
        if not str(row.get("evidence_ref") or "").strip():
            failures.append(f"PARTICIPANT_EVIDENCE_MISSING:{index}")
        for metric in ("distinctness", "readability", "usefulness"):
            score = row.get(metric)
            if not isinstance(score, int) or not 1 <= score <= 5:
                failures.append(f"INVALID_HUMAN_SCORE:{index}:{metric}")
    return ("EVIDENCE_COMPLETE_REVIEW_REQUIRED" if not failures else "NOT_RUN_OR_INCOMPLETE", failures)
