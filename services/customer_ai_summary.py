"""Fail-closed customer explanations derived only from governed ATLAS evidence.

These builders are deterministic presentation adapters.  They never calculate or
replace a protected investment field and do not call an LLM or a data provider.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


VERSION = "ATLAS_GROUNDED_CUSTOMER_SUMMARY_V1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: Any, limit: int = 3) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        return []
    result: list[str] = []
    for item in value:
        text = str(_mapping(item).get("text") or item).strip()
        if text and text not in result:
            result.append(text)
    return result[:limit]


def build_research_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return an explanatory summary without deriving financial truth."""
    certified = _mapping(report.get("certified_customer_evaluation"))
    decision = _mapping(certified.get("decision"))
    if certified and certified.get("customer_publication_allowed") is not True:
        return {"status": "UNAVAILABLE", "reason": "RATING_NOT_PUBLISHED", "sections": {}, "evidence_ids": []}
    context = _mapping(report.get("research_context"))
    production = _mapping(context.get("production_decision"))
    action = decision.get("action") if certified else production.get("recommendation")
    if not action:
        return {"status": "UNAVAILABLE", "reason": "CERTIFIED_ACTION_UNAVAILABLE", "sections": {}, "evidence_ids": []}
    intelligence = _mapping(report.get("intelligence"))
    guidance = _mapping(report.get("guidance_summary"))
    conditions = _mapping(guidance.get("thesis_change_conditions"))
    evidence_ids = sorted({str(item) for item in report.get("evidence_ids") or () if item})
    sections = {
        "Investment view": f"The certified ATLAS Action is {str(action).replace('_', ' ')}.",
        "Why it is attractive": _items(intelligence.get("why_atlas_supports_it"), 3),
        "Valuation": "Use the certified ATLAS Fair Value and Potential shown above; this explanation does not recalculate them.",
        "Technical setup": str(_mapping(report.get("technical_summary")).get("summary") or "Technical evidence is unavailable."),
        "Fundamental context": str(_mapping(_mapping(report.get("sections")).get("financials")).get("interpretation") or "Fundamental context is unavailable."),
        "Key risk": _items(intelligence.get("key_risks"), 3),
        "Entry consideration": str(_mapping(guidance.get("action_now")).get("current_action") or "Use the certified entry range when published."),
        "What to monitor": _items([*(_items(conditions.get("strengthen"))), *(_items(conditions.get("invalidate")))], 4),
    }
    return {"status": "AVAILABLE", "authority": "CERTIFIED_ATLAS_FACTS", "explanation": "AI_GENERATED_EXPLANATION", "sections": sections, "evidence_ids": evidence_ids, "version": VERSION}


def build_earnings_summary(story: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize normalized transcript evidence; absence always fails closed."""
    transcript = _mapping(story.get("transcript_intelligence"))
    if transcript.get("semantic_status") != "AVAILABLE":
        return {"status": "UNAVAILABLE", "message": "Transcript analysis unavailable", "sections": {}, "evidence_ids": []}
    data = _mapping(transcript.get("data")) or transcript
    evidence_ids = sorted({str(item) for item in (transcript.get("evidence_ids") or data.get("source_evidence_ids") or ()) if item})
    sections = {
        "What happened": _items(data.get("what_happened") or data.get("management_themes"), 4),
        "Management themes": _items(data.get("management_themes"), 5),
        "Guidance": _items(data.get("verified_guidance_statements"), 5),
        "Demand and growth drivers": _items(data.get("supported_opportunities"), 4),
        "Risks / watch items": _items([*(_items(data.get("supported_risks"), 4)), *(_items(data.get("monitoring_items"), 4))], 6),
        "Q&A insights": _items(data.get("qa_insights") or data.get("analyst_management_exchanges"), 4),
    }
    return {"status": "AVAILABLE", "classification": "CONTEXTUAL_NON_SCORING", "sections": sections, "evidence_ids": evidence_ids, "provider": transcript.get("provider"), "retrieved_at": transcript.get("retrieved_at"), "version": VERSION}


__all__ = ["VERSION", "build_earnings_summary", "build_research_summary"]
