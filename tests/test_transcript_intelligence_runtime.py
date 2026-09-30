from __future__ import annotations

import hashlib

from services.transcript_intelligence_runtime import (
    _bind_source_excerpt_hashes, _source_span_ledger,
    clear_transcript_runtime_cache, retrieve_and_summarize_transcript,
    transcript_period_index, validate_grounded_summary,
)
from services.transcript_provider import ConfiguredTranscriptProvider


class Response:
    status_code = 200
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


def _provider(calls, *, license_state="COMMERCIAL_LICENSE_CONFIRMED"):
    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/events"):
            return Response({"events": [{"year": 2026, "quarter": 2, "conference_date": "2026-07-20"}]})
        return Response({
            "id": "call-1", "conference_date": "2026-07-20",
            "text": "Revenue grew 10% because customer demand improved. Margin pressure remains a risk.",
        })
    return ConfiguredTranscriptProvider(
        api_key="secret", base_url="https://v2.api.earningscall.biz", provider_name="earningscall",
        license_state=license_state, get=get,
    )


def _summary(_payload):
    def claim(text, excerpt, claim_type):
        return {
            "claim": text, "source_excerpt": excerpt,
            "source_excerpt_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
            "claim_type": claim_type, "source_section": "PREPARED_REMARKS",
        }
    return ({
        "management_summary": claim(
            "Revenue grew 10%.", "Revenue grew 10% because customer demand improved.", "PERFORMANCE"
        ),
        "management_themes": [claim(
            "Customer demand improved.", "Revenue grew 10% because customer demand improved.", "DEMAND"
        )],
        "key_takeaways": [], "supported_opportunities": [],
        "supported_risks": [claim(
            "Margin pressure remains a risk.", "Margin pressure remains a risk.", "RISK"
        )],
        "verified_guidance_statements": [], "capital_allocation_comments": [], "demand_comments": [],
        "margin_comments": [], "analyst_question_themes": [], "monitoring_items": [],
        "material_changes_vs_prior_call": [],
    }, "APPROVED_TEST_MODEL", "v1")


def test_period_index_and_exact_period_retrieval_cache():
    clear_transcript_runtime_cache()
    calls = []
    provider = _provider(calls)
    index = transcript_period_index(provider, "AAPL")
    assert index["data"]["periods"][0]["fiscal_quarter"] == 2
    first = retrieve_and_summarize_transcript("AAPL", year=2026, quarter=2, provider=provider, summarizer=_summary)
    second = retrieve_and_summarize_transcript("AAPL", year=2026, quarter=2, provider=provider, summarizer=_summary)
    assert first.operation_metadata["cache_status"] == "CACHE_MISS"
    assert second.operation_metadata["cache_status"] == "CACHE_HIT"
    assert first.transcript.provenance.raw_evidence_id == second.transcript.provenance.raw_evidence_id
    assert second.operation_metadata["provider_call_count"] == 0
    assert "raw_content" not in second.customer_projection
    assert "Revenue grew 10% because customer demand improved." not in str(second.insight.payload)
    assert all("source_excerpt" not in item for item in second.insight.payload["management_themes"])
    assert second.insight.payload["management_summary"]["source_excerpt_hash"]
    assert second.insight.payload["management_summary"]["claim"] == "Revenue grew 10%."


def test_no_approved_summarizer_fails_closed_and_remains_non_scoring(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    clear_transcript_runtime_cache()
    result = retrieve_and_summarize_transcript("MSFT", year=2026, quarter=2, provider=_provider([]))
    assert result.customer_projection["semantic_status"] == "DATA_UNAVAILABLE"
    assert result.operation_metadata["grounding_status"] == "NOT_RUN"
    assert result.operation_metadata["ai_summary_status"] == "AI_PROVIDER_NOT_CONFIGURED"
    assert result.operation_metadata["non_scoring"] is True


def test_precommercial_summary_never_reaches_customer_projection():
    clear_transcript_runtime_cache()
    result = retrieve_and_summarize_transcript(
        "NVDA", year=2026, quarter=2,
        provider=_provider([], license_state="DEVELOPMENT_PRECOMMERCIAL"), summarizer=_summary,
    )
    assert result.operation_metadata["grounding_status"] == "PASS"
    assert result.customer_projection == {
        "semantic_status": "DATA_UNAVAILABLE", "status_detail": "Transcript intelligence unavailable."
    }


def test_unsupported_numeric_claim_is_rejected():
    source = "Revenue grew 10% because customer demand improved."
    payload, _, _ = _summary({})
    payload["management_summary"]["claim"] = "Revenue grew 25%."
    valid, violations, diagnostics = validate_grounded_summary(payload, source + " Margin pressure remains a risk.")
    assert valid is False
    assert "MANAGEMENT_SUMMARY_UNGROUNDED" in violations
    assert diagnostics[0]["failure_reason"] == "NUMERIC_MISMATCH"
    assert diagnostics[0]["numeric_tokens"] == ["25%"]
    assert "source_excerpt" not in diagnostics[0]


def test_excerpt_hash_and_verbatim_span_are_required():
    source = "Revenue grew 10% because customer demand improved. Margin pressure remains a risk."
    payload, _, _ = _summary({})
    payload["management_summary"]["source_excerpt_hash"] = "0" * 64
    valid, _, diagnostics = validate_grounded_summary(payload, source)
    assert valid is False
    assert diagnostics[0]["failure_reason"] == "SCHEMA_FAILURE"
    assert diagnostics[0]["match_reason"] == "SOURCE_EXCERPT_HASH_MISMATCH"


def test_concise_paraphrase_is_allowed_only_when_traceable_to_exact_excerpt():
    source = (
        "Revenue grew 10% because customer demand improved. "
        "Enterprise demand remained strong during the quarter. Margin pressure remains a risk."
    )
    excerpt = "Enterprise demand remained strong during the quarter."
    payload, _, _ = _summary({})
    payload["management_summary"] = {
        "claim": "Enterprise demand remained strong.",
        "source_excerpt": excerpt,
        "source_excerpt_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "claim_type": "DEMAND", "source_section": "PREPARED_REMARKS",
    }
    valid, violations, diagnostics = validate_grounded_summary(payload, source)
    assert valid is True, violations
    assert all(item["failure_reason"] is None for item in diagnostics)


def test_unsupported_causal_and_forward_claims_fail_closed():
    source = "Demand improved during the quarter. Margin pressure remains a risk."
    excerpt = "Demand improved during the quarter."
    payload, _, _ = _summary({})
    payload["management_summary"] = {
        "claim": "Demand improved because pricing will increase.",
        "source_excerpt": excerpt,
        "source_excerpt_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "claim_type": "DEMAND", "source_section": "PREPARED_REMARKS",
    }
    valid, _, diagnostics = validate_grounded_summary(payload, source)
    assert valid is False
    assert diagnostics[0]["failure_reason"] in {"PARAPHRASE_NOT_TRACEABLE", "UNSUPPORTED_CLAIM"}


def test_generation_span_id_binds_to_exact_source_and_not_model_reconstruction():
    source = "Revenue was $10 billion. Demand remained strong."
    ledger, _ = _source_span_ledger(source)
    span_id = next(key for key, value in ledger.items() if "Revenue" in value)
    payload, _, _ = _summary({})
    payload["management_summary"].update({
        "source_span_id": span_id,
        "source_excerpt": "Revenue was approximately $10 billion.",
        "source_excerpt_hash": "model-does-not-compute-hashes",
        "claim": "Revenue was $10 billion.",
    })
    bound = _bind_source_excerpt_hashes(payload, ledger)
    assert bound["management_summary"]["source_excerpt"] == "Revenue was $10 billion."
    assert bound["management_summary"]["source_excerpt_hash"] == hashlib.sha256(
        b"Revenue was $10 billion."
    ).hexdigest()


def test_unknown_generation_span_id_fails_closed():
    source = "Revenue was $10 billion."
    ledger, _ = _source_span_ledger(source)
    payload, _, _ = _summary({})
    payload["management_summary"].update({
        "source_span_id": "SPAN_DOES_NOT_EXIST",
        "source_excerpt": source,
    })
    bound = _bind_source_excerpt_hashes(payload, ledger)
    valid, _, diagnostics = validate_grounded_summary(bound, source + " Margin pressure remains a risk.")
    assert valid is False
    assert diagnostics[0]["failure_reason"] == "SCHEMA_FAILURE"


def test_missing_management_summary_uses_only_an_existing_evidence_bound_claim():
    source = "Revenue was $10 billion. Margin pressure remains a risk."
    ledger, _ = _source_span_ledger(source)
    span_id = next(key for key, value in ledger.items() if "Revenue" in value)
    payload, _, _ = _summary({})
    payload["management_summary"] = None
    for field in (
        "management_themes", "key_takeaways", "supported_opportunities", "supported_risks",
        "verified_guidance_statements", "capital_allocation_comments", "demand_comments",
        "margin_comments", "analyst_question_themes", "monitoring_items", "material_changes_vs_prior_call",
    ):
        payload[field] = []
    payload["key_takeaways"] = [{
        "claim": "Revenue was $10 billion.", "source_span_id": span_id,
        "source_excerpt": "model reconstruction is ignored", "source_excerpt_hash": "",
        "claim_type": "FINANCIAL", "source_section": "PREPARED_REMARKS",
    }]
    bound = _bind_source_excerpt_hashes(payload, ledger)
    assert bound["management_summary"] == bound["key_takeaways"][0]
    valid, violations, diagnostics = validate_grounded_summary(bound, source)
    assert valid is True, violations
    assert all(item["failure_reason"] is None for item in diagnostics)
