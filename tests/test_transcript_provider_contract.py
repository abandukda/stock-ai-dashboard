from __future__ import annotations

from services.provider_domain_contracts import DatasetFamily, UsePermission, CertificationStatus
from services.transcript_provider import (
    ConfiguredTranscriptProvider, TranscriptLicenseState,
    build_transcript_derived_insight, transcript_customer_projection,
)


class Response:
    status_code = 200
    def json(self):
        return {
            "id": "call-1", "company": "Example", "call_date": "2026-07-20T20:00:00Z",
            "version": "2", "content": "Management discussed revenue growth. Analysts asked about margin risk.",
            "speakers": [{"name": "CEO"}], "qa": [{"question": "Margins?", "answer": "Investing."}],
        }


class EarningsCallResponse:
    status_code = 200
    def __init__(self, payload): self._payload = payload
    def json(self): return self._payload


def _get(*_args, **_kwargs):
    return Response()


def test_precommercial_transcript_is_internal_and_customer_fails_closed():
    evidence = ConfiguredTranscriptProvider(
        api_key="secret", base_url="https://transcripts.invalid", provider_name="VENDOR",
        license_state=TranscriptLicenseState.DEVELOPMENT_PRECOMMERCIAL.value, get=_get,
    ).transcript("AAPL", year=2026, quarter=2)
    assert evidence.provenance.dataset_family == DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE
    assert evidence.provenance.display_permission == UsePermission.PROHIBITED
    assert evidence.payload["raw_content_hash"]
    insight = build_transcript_derived_insight(
        evidence, {"management_summary": "Management discussed revenue growth."},
        model_provider="TEST_MODEL", model_version="v1", prompt_version="prompt-v1",
    )
    assert insight.payload["source_transcript_evidence_id"] == evidence.provenance.raw_evidence_id
    assert transcript_customer_projection(insight) == {
        "semantic_status": "DATA_UNAVAILABLE", "status_detail": "Transcript intelligence unavailable."
    }


def test_commercial_transcript_projection_is_bounded_and_traceable():
    evidence = ConfiguredTranscriptProvider(
        api_key="secret", base_url="https://transcripts.invalid", provider_name="VENDOR",
        license_state=TranscriptLicenseState.COMMERCIAL_LICENSE_CONFIRMED.value, get=_get,
    ).transcript("AAPL", year=2026, quarter=2)
    insight = build_transcript_derived_insight(
        evidence, {"management_summary": "Grounded summary", "material_risks": ["Margin pressure"]},
        model_provider="TEST_MODEL", model_version="v1", prompt_version="prompt-v1",
    )
    projected = transcript_customer_projection(insight)
    assert projected["semantic_status"] == "AVAILABLE"
    assert projected["source_evidence_ids"] == [evidence.provenance.raw_evidence_id]
    assert "raw_content" not in projected
    assert projected["model_version"] == "v1"


def test_known_earningscall_provider_missing_key_preserves_provider_identity():
    record = ConfiguredTranscriptProvider(
        api_key="", base_url="https://v2.api.earningscall.biz", provider_name="earningscall",
    ).transcript("AAPL", year=2026, quarter=2)
    assert record.payload == {"status": "DATA_UNAVAILABLE", "reason": "MISSING_API_KEY"}
    assert record.provenance.provider != "FMP"
    assert record.provenance.provider == "EARNINGSCALL"
    assert record.provenance.certification_status == CertificationStatus.DATA_UNAVAILABLE
    assert record.provenance.display_permission == UsePermission.PROHIBITED


def test_truly_unconfigured_provider_uses_explicit_unconfigured_identity(monkeypatch):
    monkeypatch.delenv("ATLAS_TRANSCRIPT_PROVIDER", raising=False)
    record = ConfiguredTranscriptProvider(
        api_key="configured-but-redacted", base_url="", provider_name="",
    ).transcript("AAPL", year=2026, quarter=2)
    assert record.payload == {"status": "DATA_UNAVAILABLE", "reason": "TRANSCRIPT_PROVIDER_NOT_CONFIGURED"}
    assert record.provenance.provider == "UNCONFIGURED_TRANSCRIPT_PROVIDER"
    assert record.provenance.certification_status == CertificationStatus.DATA_UNAVAILABLE


def test_configured_provider_without_base_returns_valid_unavailable_record():
    record = ConfiguredTranscriptProvider(
        api_key="secret", base_url="", provider_name="earningscall",
    ).transcript("AAPL", year=2026, quarter=2)
    assert record.payload["reason"] == "TRANSCRIPT_PROVIDER_NOT_CONFIGURED"
    assert record.provenance.provider == "EARNINGSCALL"
    assert record.provenance.raw_evidence_id
    assert record.provenance.adapter_version


def test_earningscall_uses_documented_endpoint_without_logging_raw_text():
    calls = []
    provider = ConfiguredTranscriptProvider(
        api_key="secret", base_url="https://v2.api.earningscall.biz",
        provider_name="earningscall", get=lambda url, **kwargs: calls.append((url, kwargs)) or Response(),
    )
    record = provider.transcript("AAPL", year=2026, quarter=2)
    assert calls[0][0] == "https://v2.api.earningscall.biz/transcript"
    assert calls[0][1]["params"]["apikey"] == "secret"
    assert record.provenance.dataset_family == DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE


def test_earningscall_reads_documented_text_envelope():
    provider = ConfiguredTranscriptProvider(
        api_key="secret", base_url="https://v2.api.earningscall.biz", provider_name="earningscall",
        get=lambda *_a, **_k: EarningsCallResponse({"text": "Real transcript text", "speakers": [{"name": "CEO"}]}),
    )
    record = provider.transcript("AAPL", year=2025, quarter=4)
    assert record.payload["raw_content_hash"]
    assert record.payload["speaker_metadata"] == [{"name": "CEO"}]
    assert record.payload["resolved_period"] == "2025-Q4"


def test_earningscall_discovers_latest_available_period_when_requested_period_empty():
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/events"):
            return EarningsCallResponse({"events": [{"year": 2025, "quarter": 3}, {"year": 2026, "quarter": 1}]})
        if kwargs["params"]["year"] == 2026 and kwargs["params"]["quarter"] == 1:
            return EarningsCallResponse({"text": "Available transcript", "conference_date": "2026-04-20"})
        return EarningsCallResponse({})
    record = ConfiguredTranscriptProvider(
        api_key="secret", base_url="https://v2.api.earningscall.biz", provider_name="earningscall", get=get,
    ).transcript("AAPL", year=2026, quarter=2)
    assert [call[0].rsplit("/", 1)[-1] for call in calls] == ["transcript", "events", "transcript"]
    assert record.payload["requested_period"] == "2026-Q2"
    assert record.payload["resolved_period"] == "2026-Q1"
    assert record.provenance.effective_period == "2026-Q1"
