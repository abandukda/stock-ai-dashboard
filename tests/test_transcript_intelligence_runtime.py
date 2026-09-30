from __future__ import annotations

from services.transcript_intelligence_runtime import (
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
    return ({
        "management_summary": {"text": "Revenue grew 10%.", "evidence": "Revenue grew 10% because customer demand improved."},
        "management_themes": [{"text": "Customer demand improved.", "evidence": "Revenue grew 10% because customer demand improved."}],
        "key_takeaways": [], "supported_opportunities": [],
        "supported_risks": [{"text": "Margin pressure remains a risk.", "evidence": "Margin pressure remains a risk."}],
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
    assert all("evidence" not in item for item in second.insight.payload["management_themes"])
    assert second.insight.payload["management_summary"]["grounding_evidence_hash"]


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
    payload["management_summary"] = {"text": "Revenue grew 25%.", "evidence": source}
    valid, violations = validate_grounded_summary(payload, source + " Margin pressure remains a risk.")
    assert valid is False
    assert "MANAGEMENT_SUMMARY_UNGROUNDED" in violations
