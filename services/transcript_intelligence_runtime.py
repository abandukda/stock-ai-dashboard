"""Non-scoring runtime for governed transcript retrieval and grounded summaries."""
from __future__ import annotations

import json
import os
import re
import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from services.provider_domain_contracts import GovernedRecord
from services.transcript_provider import (
    ConfiguredTranscriptProvider, build_transcript_derived_insight, transcript_customer_projection,
)


TRANSCRIPT_SUMMARY_PROMPT_VERSION = "ATLAS_TRANSCRIPT_SUMMARY_PROMPT_V1"
TRANSCRIPT_SUMMARY_SCHEMA_VERSION = "ATLAS_TRANSCRIPT_SUMMARY_SCHEMA_V1"
SUMMARY_FIELDS = (
    "management_themes", "key_takeaways", "supported_opportunities", "supported_risks",
    "verified_guidance_statements", "capital_allocation_comments", "demand_comments",
    "margin_comments", "analyst_question_themes", "monitoring_items",
    "material_changes_vs_prior_call",
)
_REQUEST_CACHE: dict[tuple[str, int, int, str], GovernedRecord] = {}
_EVIDENCE_CACHE: dict[tuple[str, int, int, str, str], GovernedRecord] = {}


@dataclass(frozen=True)
class TranscriptRuntimeResult:
    transcript: GovernedRecord
    insight: GovernedRecord | None
    customer_projection: Mapping[str, Any]
    operation_metadata: Mapping[str, Any]


def _provider_name(provider: ConfiguredTranscriptProvider) -> str:
    return str(getattr(provider, "_provider", "UNCONFIGURED_TRANSCRIPT_PROVIDER"))


def clear_transcript_runtime_cache() -> None:
    _REQUEST_CACHE.clear()
    _EVIDENCE_CACHE.clear()


def transcript_period_index(provider: ConfiguredTranscriptProvider, symbol: str) -> dict[str, Any]:
    record = provider.available_periods(symbol)
    return {
        "semantic_status": "AVAILABLE" if record.payload.get("periods") else "DATA_UNAVAILABLE",
        "data": {"periods": list(record.payload.get("periods") or ())},
        "evidence_ids": [record.provenance.raw_evidence_id],
        "status_detail": record.payload.get("reason"),
    }


def _claim_valid(claim: Any, source: str) -> bool:
    if not isinstance(claim, Mapping):
        return False
    text, evidence = str(claim.get("text") or "").strip(), str(claim.get("evidence") or "").strip()
    if not text or not evidence or len(evidence) > 500 or evidence not in source:
        return False
    source_numbers = set(re.findall(r"(?<!\w)[+-]?\d[\d,.]*%?", evidence))
    claim_numbers = set(re.findall(r"(?<!\w)[+-]?\d[\d,.]*%?", text))
    return claim_numbers.issubset(source_numbers)


def validate_grounded_summary(payload: Any, source: str) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(payload, Mapping):
        return False, ("SUMMARY_NOT_OBJECT",)
    violations: list[str] = []
    if not _claim_valid(payload.get("management_summary"), source):
        violations.append("MANAGEMENT_SUMMARY_UNGROUNDED")
    for field in SUMMARY_FIELDS:
        values = payload.get(field, [])
        if not isinstance(values, list) or any(not _claim_valid(item, source) for item in values):
            violations.append(f"{field.upper()}_UNGROUNDED")
    return not violations, tuple(violations)


def _redact_grounding_excerpts(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Retain derived claims and excerpt hashes, never raw grounding excerpts."""
    def cleaned(claim: Any) -> dict[str, Any] | None:
        if not isinstance(claim, Mapping):
            return None
        text, evidence = str(claim.get("text") or "").strip(), str(claim.get("evidence") or "").strip()
        if not text:
            return None
        return {
            "text": text,
            "grounding_evidence_hash": hashlib.sha256(evidence.encode()).hexdigest() if evidence else None,
        }
    result: dict[str, Any] = {"management_summary": cleaned(payload.get("management_summary"))}
    for field in SUMMARY_FIELDS:
        result[field] = [item for item in (cleaned(value) for value in payload.get(field, [])) if item]
    return result


def _openai_summarizer(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, str, str]:
    """Send transcript evidence only to the explicitly approved OpenAI boundary."""
    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    model = str(os.getenv("ATLAS_TRANSCRIPT_AI_MODEL", os.getenv("ATLAS_LLM_MODEL", "gpt-4o-mini"))).strip()
    if not api_key:
        return None, "OPENAI_NOT_CONFIGURED", model
    try:
        from openai import OpenAI
        response = OpenAI(api_key=api_key).chat.completions.create(
            model=model, temperature=0, max_tokens=2200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    "Summarize only the supplied earnings-call transcript. Do not use model memory, web facts, "
                    "investment ratings, or unsupported numbers. Return one JSON object. management_summary must "
                    "be {text,evidence}; every item in every list must be {text,evidence}. evidence must be a short "
                    "exact excerpt copied from the supplied transcript. Use empty lists when evidence is absent. "
                    "Never output the complete transcript."
                )},
                {"role": "user", "content": json.dumps({
                    "ticker": payload.get("ticker"),
                    "requested_period": payload.get("requested_period"),
                    "resolved_period": payload.get("resolved_period"),
                    "output_schema": {
                        "management_summary": {"text": "string", "evidence": "exact source excerpt"},
                        **{field: [{"text": "string", "evidence": "exact source excerpt"}] for field in SUMMARY_FIELDS},
                    },
                    "transcript": payload.get("transcript"),
                }, sort_keys=True, default=str)},
            ],
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        return parsed if isinstance(parsed, Mapping) else None, "OPENAI", model
    except Exception:
        return None, "OPENAI_ERROR", model


def retrieve_and_summarize_transcript(
    symbol: str, *, year: int, quarter: int,
    provider: ConfiguredTranscriptProvider | None = None,
    summarizer: Callable[[Mapping[str, Any]], tuple[Mapping[str, Any] | None, str, str]] | None = None,
) -> TranscriptRuntimeResult:
    """Retrieve evidence and optionally call an explicitly supplied approved summarizer.

    No default external model call exists: raw licensed text may leave this boundary
    only through a caller-supplied, separately approved summarizer.
    """
    provider = provider or ConfiguredTranscriptProvider()
    key = (str(symbol).upper(), int(year), int(quarter), _provider_name(provider))
    cache_hit = key in _REQUEST_CACHE
    evidence = _REQUEST_CACHE.get(key)
    provider_calls = 0
    if evidence is None:
        evidence = provider.transcript(symbol, year=year, quarter=quarter)
        provider_calls = 1
        evidence_id = evidence.provenance.raw_evidence_id
        resolved_year = int(evidence.payload.get("year") or year)
        resolved_quarter = int(evidence.payload.get("quarter") or quarter)
        identity_key = (key[0], resolved_year, resolved_quarter, key[3], evidence_id)
        evidence = _EVIDENCE_CACHE.setdefault(identity_key, evidence)
        _REQUEST_CACHE[key] = evidence
    raw = evidence.payload.get("raw_content")
    insight = None
    projection: Mapping[str, Any] = {
        "semantic_status": "DATA_UNAVAILABLE", "status_detail": "AI summary unavailable."
    }
    grounding = "NOT_RUN"
    ai_status = "AI_SUMMARY_UNAVAILABLE"
    if isinstance(raw, str) and raw.strip():
        generated, model_provider, model_version = (summarizer or _openai_summarizer)({
            "ticker": key[0], "requested_period": f"{year}-Q{quarter}",
            "resolved_period": evidence.payload.get("resolved_period"),
            "schema_version": TRANSCRIPT_SUMMARY_SCHEMA_VERSION,
            "transcript": raw,
        })
        valid, violations = validate_grounded_summary(generated, raw)
        grounding = "PASS" if valid else "NOT_RUN" if generated is None else "FAIL"
        ai_status = (
            "PASS" if valid else "AI_PROVIDER_NOT_CONFIGURED" if model_provider == "OPENAI_NOT_CONFIGURED"
            else "AI_SUMMARY_FAILED" if generated is None else "AI_SUMMARY_GROUNDING_FAILED"
        )
        if valid and generated is not None:
            derived_payload = _redact_grounding_excerpts(generated)
            insight = build_transcript_derived_insight(
                evidence, {**derived_payload, "grounding_status": "PASS", "grounding_violations": []},
                model_provider=model_provider, model_version=model_version,
                prompt_version=TRANSCRIPT_SUMMARY_PROMPT_VERSION,
            )
            projection = transcript_customer_projection(insight)
        elif violations:
            projection = {"semantic_status": "DATA_UNAVAILABLE", "status_detail": "AI summary grounding failed."}
    return TranscriptRuntimeResult(evidence, insight, projection, {
        "cache_status": "CACHE_HIT" if cache_hit else "CACHE_MISS",
        "provider_call_count": provider_calls,
        "transcript_evidence_id": evidence.provenance.raw_evidence_id,
        "requested_period": f"{year}-Q{quarter}",
        "resolved_period": evidence.payload.get("resolved_period"),
        "call_date": evidence.payload.get("call_date"),
        "raw_content_hash": evidence.payload.get("raw_content_hash"),
        "provider": evidence.provenance.provider,
        "capture_timestamp": evidence.provenance.capture_timestamp,
        "license_state": evidence.provenance.license_class,
        "grounding_status": grounding, "ai_summary_status": ai_status,
        "model_provider_status": model_provider if isinstance(raw, str) and raw.strip() else None,
        "non_scoring": True,
    })


__all__ = [
    "SUMMARY_FIELDS", "TranscriptRuntimeResult", "clear_transcript_runtime_cache",
    "retrieve_and_summarize_transcript", "transcript_period_index", "validate_grounded_summary",
]
