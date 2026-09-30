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


TRANSCRIPT_SUMMARY_PROMPT_VERSION = "ATLAS_TRANSCRIPT_SUMMARY_PROMPT_V2"
TRANSCRIPT_SUMMARY_SCHEMA_VERSION = "ATLAS_TRANSCRIPT_SUMMARY_SCHEMA_V2"
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


_FAILURE_TAXONOMY = frozenset({
    "EXACT_MATCH_TOO_STRICT", "PARAPHRASE_NOT_TRACEABLE", "NUMERIC_MISMATCH",
    "UNSUPPORTED_CLAIM", "MISSING_SOURCE_SPAN", "SCHEMA_FAILURE",
})
_MEANING_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "for", "from",
    "had", "has", "have", "in", "is", "it", "its", "of", "on", "or", "said", "says",
    "that", "the", "their", "they", "this", "to", "was", "were", "with",
})
_CAUSAL_MARKERS = frozenset({"because", "caused", "driven", "due", "resulted"})
_FORWARD_MARKERS = frozenset({"anticipate", "expect", "forecast", "guidance", "outlook", "project", "will"})


def _excerpt_hash(excerpt: str) -> str:
    return hashlib.sha256(excerpt.encode("utf-8")).hexdigest()


def _source_span_ledger(source: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Create stable, exact source spans so generation selects evidence instead of recreating it."""
    pieces = re.split(r"(?<=[.!?])\s+|\n+", source)
    spans: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) <= 700:
            spans.append(piece)
            continue
        for start in range(0, len(piece), 700):
            chunk = piece[start:start + 700].strip()
            if chunk:
                spans.append(chunk)
    ledger = {f"SPAN_{index:05d}": span for index, span in enumerate(spans, start=1)}
    return ledger, [{"source_span_id": key, "source_excerpt": value} for key, value in ledger.items()]


def _bind_source_excerpt_hashes(payload: Any, span_ledger: Mapping[str, str] | None = None) -> Any:
    """Attach canonical selected spans and hashes; models do not calculate cryptographic identities."""
    if not isinstance(payload, Mapping):
        return payload

    def bound(value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        item = dict(value)
        span_id = str(item.get("source_span_id") or "").strip()
        selected = (span_ledger or {}).get(span_id)
        excerpt = (
            selected if selected is not None else ""
            if span_ledger is not None else str(item.get("source_excerpt") or "").strip()
        )
        item["source_excerpt"] = excerpt
        item["source_excerpt_hash"] = _excerpt_hash(excerpt) if excerpt else ""
        return item

    result = dict(payload)
    result["management_summary"] = bound(payload.get("management_summary"))
    for field in SUMMARY_FIELDS:
        values = payload.get(field, [])
        result[field] = [bound(item) for item in values] if isinstance(values, list) else values
    if not isinstance(result.get("management_summary"), Mapping):
        for field in ("key_takeaways", "management_themes") + SUMMARY_FIELDS:
            values = result.get(field)
            if isinstance(values, list) and values and isinstance(values[0], Mapping):
                result["management_summary"] = dict(values[0])
                break
    return result


def _number_tokens(text: str) -> tuple[str, ...]:
    """Keep numeric units attached so percent/basis-point claims cannot cross-match."""
    pattern = r"(?<!\w)(?:[$€£])?[+-]?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent|percentage points?|bps?|basis points?|million|billion|thousand))?"
    return tuple(re.sub(r"\s+", " ", item.strip().lower()) for item in re.findall(pattern, text, re.I))


def _words(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z][a-z'-]+", text.lower())
        if word not in _MEANING_STOPWORDS and len(word) > 2
    }


def _claim_diagnostic(claim: Any, source: str, *, field: str, index: int) -> dict[str, Any]:
    diagnostic: dict[str, Any] = {
        "field": field, "claim_index": index, "claim_type": None, "claim_text": None,
        "numeric_tokens": [], "candidate_supporting_excerpt_hash": None,
        "match_reason": None, "failure_reason": None,
    }
    if not isinstance(claim, Mapping):
        diagnostic.update(match_reason="CLAIM_NOT_OBJECT", failure_reason="SCHEMA_FAILURE")
        return diagnostic
    text = str(claim.get("claim") or "").strip()
    excerpt = str(claim.get("source_excerpt") or "").strip()
    supplied_hash = str(claim.get("source_excerpt_hash") or "").strip().lower()
    claim_type = str(claim.get("claim_type") or "").strip().upper()
    diagnostic.update(
        claim_type=claim_type or None, claim_text=text or None,
        numeric_tokens=list(_number_tokens(text)),
        candidate_supporting_excerpt_hash=_excerpt_hash(excerpt) if excerpt else None,
    )
    if not text or not excerpt or not claim_type or not supplied_hash:
        diagnostic.update(match_reason="REQUIRED_CLAIM_FIELD_MISSING", failure_reason="SCHEMA_FAILURE")
        return diagnostic
    if len(excerpt) > 700:
        diagnostic.update(match_reason="SOURCE_EXCERPT_TOO_LONG", failure_reason="SCHEMA_FAILURE")
        return diagnostic
    expected_hash = _excerpt_hash(excerpt)
    if supplied_hash != expected_hash:
        diagnostic.update(match_reason="SOURCE_EXCERPT_HASH_MISMATCH", failure_reason="SCHEMA_FAILURE")
        return diagnostic
    if excerpt not in source:
        compact = lambda value: re.sub(r"\s+", " ", value).strip().casefold()
        failure = "EXACT_MATCH_TOO_STRICT" if compact(excerpt) in compact(source) else "MISSING_SOURCE_SPAN"
        diagnostic.update(match_reason="SOURCE_EXCERPT_NOT_VERBATIM", failure_reason=failure)
        return diagnostic
    claim_numbers, excerpt_numbers = set(_number_tokens(text)), set(_number_tokens(excerpt))
    if not claim_numbers.issubset(excerpt_numbers):
        diagnostic.update(match_reason="NUMERIC_TOKEN_OR_UNIT_NOT_IN_EXCERPT", failure_reason="NUMERIC_MISMATCH")
        return diagnostic
    claim_words, excerpt_words = _words(text), _words(excerpt)
    missing = claim_words - excerpt_words
    if missing:
        diagnostic.update(
            match_reason="CLAIM_MATERIAL_TERMS_NOT_TRACEABLE:" + ",".join(sorted(missing)[:8]),
            failure_reason="PARAPHRASE_NOT_TRACEABLE",
        )
        return diagnostic
    for markers, reason in ((_CAUSAL_MARKERS, "UNSUPPORTED_CAUSAL_STATEMENT"),
                            (_FORWARD_MARKERS, "UNSUPPORTED_FORWARD_STATEMENT")):
        if claim_words & markers and not excerpt_words & markers:
            diagnostic.update(match_reason=reason, failure_reason="UNSUPPORTED_CLAIM")
            return diagnostic
    diagnostic.update(match_reason="VERBATIM_SPAN_HASH_NUMBERS_AND_MEANING_PASS", failure_reason=None)
    return diagnostic


def validate_grounded_summary(
    payload: Any, source: str,
) -> tuple[bool, tuple[str, ...], tuple[Mapping[str, Any], ...]]:
    if not isinstance(payload, Mapping):
        return False, ("SUMMARY_NOT_OBJECT",), ({
            "field": "summary", "claim_index": 0, "claim_type": None, "claim_text": None,
            "numeric_tokens": [], "candidate_supporting_excerpt_hash": None,
            "match_reason": "SUMMARY_NOT_OBJECT", "failure_reason": "SCHEMA_FAILURE",
        },)
    violations: list[str] = []
    diagnostics: list[Mapping[str, Any]] = []
    management = _claim_diagnostic(payload.get("management_summary"), source, field="management_summary", index=0)
    diagnostics.append(management)
    if management["failure_reason"]:
        violations.append("MANAGEMENT_SUMMARY_UNGROUNDED")
    for field in SUMMARY_FIELDS:
        values = payload.get(field, [])
        if not isinstance(values, list):
            violations.append(f"{field.upper()}_UNGROUNDED")
            diagnostics.append({
                "field": field, "claim_index": 0, "claim_type": None, "claim_text": None,
                "numeric_tokens": [], "candidate_supporting_excerpt_hash": None,
                "match_reason": "CLAIM_LIST_NOT_ARRAY", "failure_reason": "SCHEMA_FAILURE",
            })
            continue
        field_failed = False
        for index, item in enumerate(values):
            diagnostic = _claim_diagnostic(item, source, field=field, index=index)
            diagnostics.append(diagnostic)
            field_failed = field_failed or bool(diagnostic["failure_reason"])
        if field_failed:
            violations.append(f"{field.upper()}_UNGROUNDED")
    assert all(not item.get("failure_reason") or item["failure_reason"] in _FAILURE_TAXONOMY for item in diagnostics)
    return not violations, tuple(violations), tuple(diagnostics)


def _redact_grounding_excerpts(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Retain derived claims and excerpt hashes, never raw grounding excerpts."""
    def cleaned(claim: Any) -> dict[str, Any] | None:
        if not isinstance(claim, Mapping):
            return None
        text = str(claim.get("claim") or "").strip()
        evidence = str(claim.get("source_excerpt") or "").strip()
        if not text:
            return None
        return {
            "claim": text,
            "claim_type": str(claim.get("claim_type") or "").strip().upper(),
            "source_section": str(claim.get("source_section") or "").strip() or None,
            "source_excerpt_hash": _excerpt_hash(evidence) if evidence else None,
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
        span_ledger, source_spans = _source_span_ledger(str(payload.get("transcript") or ""))
        response = OpenAI(api_key=api_key).chat.completions.create(
            model=model, temperature=0, max_tokens=2200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    "Summarize only the supplied earnings-call transcript. Do not use model memory, web facts, "
                    "investment ratings, calculations, or unsupported numbers. Return one JSON object. Every "
                    "material claim must be an object with claim, source_span_id, source_excerpt, "
                    "source_excerpt_hash, claim_type, and source_section. Select one supplied source_span_id and "
                    "copy its source_excerpt exactly; the selected span must contain every number and unit in claim. "
                    "source_excerpt_hash must be present as an empty string; ATLAS computes it deterministically. "
                    "Use only material words found in the excerpt when writing a concise paraphrase. Do not add a "
                    "company name, fiscal year, cause, intent, or outlook unless it appears in that exact span. "
                    "Keep each claim no broader than its excerpt; omit unsupported claims and use empty lists when "
                    "evidence is absent. Never output the complete transcript."
                )},
                {"role": "user", "content": json.dumps({
                    "ticker": payload.get("ticker"),
                    "requested_period": payload.get("requested_period"),
                    "resolved_period": payload.get("resolved_period"),
                    "output_schema": {
                        "management_summary": {
                            "claim": "string", "source_excerpt": "exact source excerpt",
                            "source_span_id": "SPAN_00001", "source_excerpt_hash": "",
                            "claim_type": "string", "source_section": "string",
                        },
                        **{field: [{
                            "claim": "string", "source_excerpt": "exact source excerpt",
                            "source_span_id": "SPAN_00001", "source_excerpt_hash": "",
                            "claim_type": "string", "source_section": "string",
                        }] for field in SUMMARY_FIELDS},
                    },
                    "source_spans": source_spans,
                }, sort_keys=True, default=str)},
            ],
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        return _bind_source_excerpt_hashes(parsed, span_ledger) if isinstance(parsed, Mapping) else None, "OPENAI", model
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
        valid, violations, claim_diagnostics = validate_grounded_summary(generated, raw)
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
        "grounding_violations": list(violations) if isinstance(raw, str) and raw.strip() else [],
        "claim_diagnostics": list(claim_diagnostics) if isinstance(raw, str) and raw.strip() else [],
        "model_provider_status": model_provider if isinstance(raw, str) and raw.strip() else None,
        "non_scoring": True,
    })


__all__ = [
    "SUMMARY_FIELDS", "TranscriptRuntimeResult", "clear_transcript_runtime_cache",
    "retrieve_and_summarize_transcript", "transcript_period_index", "validate_grounded_summary",
]
