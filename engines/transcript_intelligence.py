"""Grounded deterministic transcript synthesis with no decision authority."""
from __future__ import annotations

import re
from typing import Any, Final, Mapping

from engines.semantic_fields import AVAILABLE, DATA_UNAVAILABLE


TRANSCRIPT_SYNTHESIS_VERSION: Final = "TRANSCRIPT_SYNTHESIS_V1"


def _sentences(content: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", content or " ").strip()
    return [part.strip()[:280] for part in re.split(r"(?<=[.!?])\s+", cleaned) if 35 <= len(part.strip()) <= 600]


def _select(sentences: list[str], words: tuple[str, ...], limit: int) -> list[str]:
    selected: list[str] = []
    for sentence in sentences:
        lower = sentence.lower()
        if any(word in lower for word in words) and sentence not in selected:
            selected.append(sentence)
        if len(selected) >= limit:
            break
    return selected


def derive_transcript_intelligence(transcript: Mapping[str, Any], *, evidence_id: str) -> dict[str, Any]:
    content = transcript.get("content")
    if not isinstance(content, str) or not content.strip() or not evidence_id:
        return {
            "version": TRANSCRIPT_SYNTHESIS_VERSION,
            "semantic_status": DATA_UNAVAILABLE,
            "status_detail": "Transcript intelligence not yet available.",
            "source_evidence_ids": [],
        }
    sentences = _sentences(content)
    themes = _select(sentences, ("revenue", "demand", "customer", "product", "growth", "margin"), 5)
    opportunities = _select(sentences, ("opportunity", "expansion", "accelerat", "pipeline", "adoption"), 4)
    risks = _select(sentences, ("risk", "pressure", "uncertain", "decline", "headwind", "challenge"), 4)
    guidance = _select(sentences, ("guidance", "outlook", "we expect", "we anticipate", "forecast"), 4)
    monitoring = _select(sentences, ("next quarter", "going forward", "monitor", "watch", "over the next"), 4)
    if not themes:
        themes = sentences[:3]
    return {
        "version": "TRANSCRIPT_INTELLIGENCE_V2",
        "synthesis_version": TRANSCRIPT_SYNTHESIS_VERSION,
        "semantic_status": AVAILABLE,
        "fiscal_quarter": f"Q{transcript.get('quarter')} {transcript.get('year')}",
        "call_date": transcript.get("call_date"),
        "verified_source": "FMP earnings-call transcript",
        "provider": "FMP",
        "management_themes": themes,
        "supported_opportunities": opportunities,
        "supported_risks": risks,
        "verified_guidance_statements": guidance,
        "monitoring_items": monitoring,
        "source_evidence_ids": [evidence_id],
        "limitations": list(transcript.get("limitations") or ()) + [
            "Statements are deterministic transcript extracts; they do not alter any ATLAS investment output."
        ],
    }


__all__ = ["TRANSCRIPT_SYNTHESIS_VERSION", "derive_transcript_intelligence"]
