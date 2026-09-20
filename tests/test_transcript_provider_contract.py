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


def test_missing_transcript_provider_returns_explicit_unavailable_without_fallback():
    record = ConfiguredTranscriptProvider(api_key="", base_url="").transcript("AAPL", year=2026, quarter=2)
    assert record.payload == {"status": "DATA_UNAVAILABLE", "reason": "MISSING_API_KEY"}
    assert record.provenance.provider != "FMP"
    assert record.provenance.provider == "UNCONFIGURED_TRANSCRIPT_PROVIDER"
    assert record.provenance.certification_status == CertificationStatus.DATA_UNAVAILABLE
    assert record.provenance.display_permission == UsePermission.PROHIBITED


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
