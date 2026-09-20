"""License-aware, provider-neutral earnings transcript capability."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from typing import Any, Callable, Mapping

import requests

from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, GovernedRecord, MarketCoverageClass,
    ProvenanceEnvelope, UsePermission,
)


TRANSCRIPT_ADAPTER_VERSION = "ATLAS_TRANSCRIPT_ADAPTER_V1"
TRANSCRIPT_DERIVATION_VERSION = "ATLAS_TRANSCRIPT_DERIVATION_V1"


class TranscriptLicenseState(str, Enum):
    DEVELOPMENT_PRECOMMERCIAL = "DEVELOPMENT_PRECOMMERCIAL"
    COMMERCIAL_LICENSE_CONFIRMED = "COMMERCIAL_LICENSE_CONFIRMED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class ConfiguredTranscriptProvider:
    """Adapter for the separately contracted transcript API.

    Endpoint and credential are environment configuration because the vendor
    contract is intentionally independent from market/fundamental providers.
    """

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 provider_name: str | None = None, license_state: str | None = None,
                 get: Callable[..., Any] = requests.get) -> None:
        self._key = str(api_key if api_key is not None else os.getenv("ATLAS_TRANSCRIPT_API_KEY", "")).strip()
        self._base = str(base_url if base_url is not None else os.getenv("ATLAS_TRANSCRIPT_API_BASE_URL", "")).strip().rstrip("/")
        configured_provider = str(
            provider_name if provider_name is not None else os.getenv("ATLAS_TRANSCRIPT_PROVIDER", "")
        ).strip().upper()
        self._provider = configured_provider or "UNCONFIGURED_TRANSCRIPT_PROVIDER"
        configured_state = str(license_state if license_state is not None else os.getenv(
            "ATLAS_TRANSCRIPT_LICENSE_STATE", TranscriptLicenseState.DEVELOPMENT_PRECOMMERCIAL.value,
        )).strip().upper()
        self._license = TranscriptLicenseState(configured_state)
        self._get = get

    def transcript(self, symbol: str, *, year: int, quarter: int) -> GovernedRecord:
        ticker = str(symbol).upper().strip()
        captured = _now()
        if not self._key:
            return self._unavailable(ticker, year, quarter, captured, "MISSING_API_KEY")
        if not self._base:
            return self._unavailable(ticker, year, quarter, captured, "TRANSCRIPT_PROVIDER_NOT_CONFIGURED")
        try:
            if self._provider == "EARNINGSCALL":
                response = self._get(
                    f"{self._base}/transcript",
                    params={"apikey": self._key, "exchange": "nasdaq", "symbol": ticker.lower(),
                            "year": year, "quarter": quarter}, timeout=20,
                )
            else:
                response = self._get(
                    f"{self._base}/transcripts",
                    params={"symbol": ticker, "year": year, "quarter": quarter},
                    headers={"Authorization": f"Bearer {self._key}"}, timeout=20,
                )
            status = int(getattr(response, "status_code", 0) or 0)
            payload = response.json() if status == 200 else {}
        except Exception as exc:
            return self._unavailable(ticker, year, quarter, captured, f"PROVIDER_ERROR:{type(exc).__name__}")
        if status in {401, 403}:
            return self._unavailable(ticker, year, quarter, captured, "ENTITLEMENT_UNAVAILABLE",
                                     CertificationStatus.ENTITLEMENT_UNAVAILABLE)
        content = payload.get("content") if isinstance(payload, Mapping) else None
        if not isinstance(content, str) or not content.strip():
            return self._unavailable(ticker, year, quarter, captured, "TRANSCRIPT_DATA_UNAVAILABLE")
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        transcript_id = str(payload.get("id") or f"{ticker}-{year}-Q{quarter}-{content_hash[:12]}")
        public = self._license == TranscriptLicenseState.COMMERCIAL_LICENSE_CONFIRMED
        provenance = ProvenanceEnvelope(
            provider=self._provider, dataset_family=DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
            endpoint_or_source_family="EARNINGS_TRANSCRIPT", symbol=ticker,
            canonical_security_id=ticker, source_timestamp=str(payload.get("call_date") or "") or None,
            capture_timestamp=captured, effective_period=f"{year}-Q{quarter}", fiscal_period=f"Q{quarter} {year}",
            raw_evidence_id=f"TRANSCRIPT:{transcript_id}:{content_hash[:20]}", content_hash=content_hash,
            freshness_status="CAPTURED", certification_status=CertificationStatus.UNVERIFIED_SHADOW,
            license_class=self._license.value,
            display_permission=UsePermission.CONTEXT_ONLY if public else UsePermission.PROHIBITED,
            derived_use_permission=UsePermission.CONTEXT_ONLY if public else UsePermission.SHADOW_ONLY,
            market_coverage_class=MarketCoverageClass.UNKNOWN,
            adapter_version=TRANSCRIPT_ADAPTER_VERSION,
            source_record_version=str(payload.get("version") or "") or None,
            supersedes=str(payload.get("supersedes") or "") or None,
            superseded_by=str(payload.get("superseded_by") or "") or None,
        )
        return GovernedRecord(provenance, {
            "provider_transcript_id": transcript_id, "company": payload.get("company"),
            "year": year, "quarter": quarter, "call_date": payload.get("call_date"),
            "speaker_metadata": payload.get("speakers") or [], "qa_segments": payload.get("qa") or [],
            "raw_content": content, "raw_content_hash": content_hash,
        }, ("Raw transcript content is internal source evidence and is never included in customer projection.",))

    def _unavailable(self, ticker: str, year: int, quarter: int, captured: str, reason: str,
                     status: CertificationStatus = CertificationStatus.DATA_UNAVAILABLE) -> GovernedRecord:
        evidence = _hash({"symbol": ticker, "year": year, "quarter": quarter, "reason": reason})
        return GovernedRecord(ProvenanceEnvelope(
            provider=self._provider, dataset_family=DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
            endpoint_or_source_family="EARNINGS_TRANSCRIPT", symbol=ticker, canonical_security_id=ticker,
            capture_timestamp=captured, effective_period=f"{year}-Q{quarter}", fiscal_period=f"Q{quarter} {year}",
            raw_evidence_id=f"TRANSCRIPT:{ticker}:{evidence[:20]}", freshness_status="UNAVAILABLE",
            certification_status=status, license_class=self._license.value,
            display_permission=UsePermission.PROHIBITED, derived_use_permission=UsePermission.SHADOW_ONLY,
            market_coverage_class=MarketCoverageClass.UNKNOWN, adapter_version=TRANSCRIPT_ADAPTER_VERSION,
        ), {"status": status.value, "reason": reason}, ("Transcript intelligence unavailable; no fallback was fabricated.",))


def build_transcript_derived_insight(
    evidence: GovernedRecord, derived_payload: Mapping[str, Any], *,
    model_provider: str, model_version: str, prompt_version: str,
) -> GovernedRecord:
    if evidence.provenance.endpoint_or_source_family != "EARNINGS_TRANSCRIPT":
        raise ValueError("derived transcript insight requires transcript evidence")
    source_id = evidence.provenance.raw_evidence_id
    captured = _now()
    digest = _hash({"source": source_id, "output": derived_payload, "model": model_version, "prompt": prompt_version})
    public = evidence.provenance.license_class == TranscriptLicenseState.COMMERCIAL_LICENSE_CONFIRMED.value
    return GovernedRecord(ProvenanceEnvelope(
        provider="ATLAS_AI", dataset_family=DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
        endpoint_or_source_family="TRANSCRIPT_DERIVED_INSIGHT", symbol=evidence.provenance.symbol,
        canonical_security_id=evidence.provenance.canonical_security_id, source_timestamp=evidence.provenance.source_timestamp,
        capture_timestamp=captured, effective_period=evidence.provenance.effective_period,
        fiscal_period=evidence.provenance.fiscal_period, raw_evidence_id=f"TRANSCRIPT_DERIVED:{digest[:24]}",
        content_hash=digest, freshness_status="DERIVED", certification_status=CertificationStatus.UNVERIFIED_SHADOW,
        license_class=evidence.provenance.license_class,
        display_permission=UsePermission.CONTEXT_ONLY if public else UsePermission.PROHIBITED,
        derived_use_permission=UsePermission.CONTEXT_ONLY if public else UsePermission.SHADOW_ONLY,
        market_coverage_class=MarketCoverageClass.UNKNOWN, adapter_version=TRANSCRIPT_DERIVATION_VERSION,
    ), {
        **dict(derived_payload), "source_transcript_evidence_id": source_id,
        "model_provider": model_provider, "model_version": model_version,
        "prompt_template_version": prompt_version, "generation_timestamp": captured,
        "output_schema_version": TRANSCRIPT_DERIVATION_VERSION,
    }, ("Transcript-derived insight is non-scoring and cannot change ATLAS decisions.",))


def transcript_customer_projection(insight: GovernedRecord) -> dict[str, Any]:
    if insight.provenance.display_permission != UsePermission.CONTEXT_ONLY:
        return {"semantic_status": "DATA_UNAVAILABLE", "status_detail": "Transcript intelligence unavailable."}
    payload = dict(insight.payload)
    payload.pop("raw_content", None)
    payload["semantic_status"] = "AVAILABLE"
    payload["source_evidence_ids"] = [payload.get("source_transcript_evidence_id")]
    return payload


__all__ = ["ConfiguredTranscriptProvider", "TranscriptLicenseState", "build_transcript_derived_insight", "transcript_customer_projection"]
