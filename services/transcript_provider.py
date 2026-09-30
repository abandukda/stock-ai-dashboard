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


TRANSCRIPT_ADAPTER_VERSION = "ATLAS_TRANSCRIPT_ADAPTER_V2"
TRANSCRIPT_DERIVATION_VERSION = "ATLAS_TRANSCRIPT_DERIVATION_V1"
COMMERCIAL_LAUNCH_REQUIRES_TRANSCRIPT_ENTERPRISE_LICENSE = True


class TranscriptLicenseState(str, Enum):
    DEVELOPMENT_PRECOMMERCIAL = "DEVELOPMENT_PRECOMMERCIAL"
    DEVELOPMENT_DERIVED_DISPLAY_ALLOWED = "DEVELOPMENT_DERIVED_DISPLAY_ALLOWED"
    COMMERCIAL_LICENSE_CONFIRMED = "COMMERCIAL_LICENSE_CONFIRMED"


TRANSCRIPT_LICENSE_PERMISSIONS: Mapping[TranscriptLicenseState, Mapping[str, Any]] = {
    TranscriptLicenseState.DEVELOPMENT_PRECOMMERCIAL: {
        "raw_transcript_display": UsePermission.PROHIBITED,
        "derived_summary_display": UsePermission.PROHIBITED,
        "internal_use": True, "scoring_authority": "NONE",
    },
    TranscriptLicenseState.DEVELOPMENT_DERIVED_DISPLAY_ALLOWED: {
        "raw_transcript_display": UsePermission.PROHIBITED,
        "derived_summary_display": UsePermission.CONTEXT_ONLY,
        "internal_use": True, "scoring_authority": "NONE",
    },
    TranscriptLicenseState.COMMERCIAL_LICENSE_CONFIRMED: {
        "raw_transcript_display": UsePermission.PROHIBITED,
        "derived_summary_display": UsePermission.CONTEXT_ONLY,
        "internal_use": True, "scoring_authority": "NONE",
    },
}


def transcript_license_permissions(state: TranscriptLicenseState | str) -> Mapping[str, Any]:
    return TRANSCRIPT_LICENSE_PERMISSIONS[TranscriptLicenseState(str(getattr(state, "value", state)).upper())]


def enforce_transcript_commercial_launch_license(
    state: TranscriptLicenseState | str, *, commercial_launch: bool,
) -> None:
    """Fail closed when a paid commercial deployment lacks the enterprise license state."""
    normalized = TranscriptLicenseState(str(getattr(state, "value", state)).upper())
    if (commercial_launch and COMMERCIAL_LAUNCH_REQUIRES_TRANSCRIPT_ENTERPRISE_LICENSE
            and normalized != TranscriptLicenseState.COMMERCIAL_LICENSE_CONFIRMED):
        raise RuntimeError("COMMERCIAL_LAUNCH_REQUIRES_TRANSCRIPT_ENTERPRISE_LICENSE")


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
        enforce_transcript_commercial_launch_license(
            self._license,
            commercial_launch=str(os.getenv("ATLAS_COMMERCIAL_LAUNCH", "false")).strip().lower()
            in {"1", "true", "yes", "on"},
        )
        self._get = get

    def transcript(self, symbol: str, *, year: int, quarter: int) -> GovernedRecord:
        ticker = str(symbol).upper().strip()
        captured = _now()
        if not self._key:
            return self._unavailable(ticker, year, quarter, captured, "MISSING_API_KEY")
        if not self._base:
            return self._unavailable(ticker, year, quarter, captured, "TRANSCRIPT_PROVIDER_NOT_CONFIGURED")
        try:
            resolved_year, resolved_quarter = year, quarter
            if self._provider == "EARNINGSCALL":
                response = self._earningscall_transcript(ticker, year, quarter)
                status = int(getattr(response, "status_code", 0) or 0)
                payload = response.json() if status == 200 else {}
                if not _transcript_text(payload):
                    event = self._latest_earningscall_event(ticker)
                    if event:
                        resolved_year, resolved_quarter = int(event["year"]), int(event["quarter"])
                        response = self._earningscall_transcript(ticker, resolved_year, resolved_quarter)
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
        content = _transcript_text(payload)
        if not isinstance(content, str) or not content.strip():
            return self._unavailable(ticker, year, quarter, captured, "TRANSCRIPT_DATA_UNAVAILABLE")
        if self._provider == "EARNINGSCALL" and not (payload.get("call_date") or payload.get("conference_date")):
            event = self._earningscall_event(ticker, resolved_year, resolved_quarter)
            if event:
                payload = {
                    **dict(payload),
                    "conference_date": event.get("call_date") or event.get("conference_date") or event.get("date"),
                }
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        transcript_id = str(payload.get("id") or payload.get("event_id") or f"{ticker}-{resolved_year}-Q{resolved_quarter}-{content_hash[:12]}")
        permissions = transcript_license_permissions(self._license)
        provenance = ProvenanceEnvelope(
            provider=self._provider, dataset_family=DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
            endpoint_or_source_family="EARNINGS_TRANSCRIPT", symbol=ticker,
            canonical_security_id=ticker, source_timestamp=str(payload.get("call_date") or "") or None,
            capture_timestamp=captured, effective_period=f"{resolved_year}-Q{resolved_quarter}", fiscal_period=f"Q{resolved_quarter} {resolved_year}",
            raw_evidence_id=f"TRANSCRIPT:{transcript_id}:{content_hash[:20]}", content_hash=content_hash,
            freshness_status="CAPTURED", certification_status=CertificationStatus.UNVERIFIED_SHADOW,
            license_class=self._license.value,
            display_permission=UsePermission.PROHIBITED,
            derived_use_permission=permissions["derived_summary_display"],
            market_coverage_class=MarketCoverageClass.UNKNOWN,
            adapter_version=TRANSCRIPT_ADAPTER_VERSION,
            source_record_version=str(payload.get("version") or "") or None,
            supersedes=str(payload.get("supersedes") or "") or None,
            superseded_by=str(payload.get("superseded_by") or "") or None,
        )
        return GovernedRecord(provenance, {
            "provider_transcript_id": transcript_id, "company": payload.get("company"),
            "year": resolved_year, "quarter": resolved_quarter,
            "requested_period": f"{year}-Q{quarter}", "resolved_period": f"{resolved_year}-Q{resolved_quarter}",
            "call_date": payload.get("call_date") or payload.get("conference_date"),
            "speaker_metadata": payload.get("speakers") or [],
            "prepared_sections": payload.get("prepared_remarks") or [],
            "qa_segments": payload.get("questions_and_answers") or payload.get("qa") or [],
            "raw_content": content, "raw_content_hash": content_hash,
        }, ("Raw transcript content is internal source evidence and is never included in customer projection.",))

    def available_periods(self, symbol: str) -> GovernedRecord:
        """Return governed period metadata without transcript bodies."""
        ticker = str(symbol).upper().strip()
        captured = _now()
        if not self._key:
            return self._unavailable(ticker, 0, 0, captured, "MISSING_API_KEY")
        if not self._base or self._provider == "UNCONFIGURED_TRANSCRIPT_PROVIDER":
            return self._unavailable(ticker, 0, 0, captured, "TRANSCRIPT_PROVIDER_NOT_CONFIGURED")
        try:
            response = self._get(
                f"{self._base}/events", params={
                    **({"apikey": self._key, "exchange": "nasdaq"} if self._provider == "EARNINGSCALL" else {}),
                    "symbol": ticker.lower() if self._provider == "EARNINGSCALL" else ticker,
                }, headers={} if self._provider == "EARNINGSCALL" else {"Authorization": f"Bearer {self._key}"},
                timeout=20,
            )
            status = int(getattr(response, "status_code", 0) or 0)
            payload = response.json() if status == 200 else {}
        except Exception as exc:
            return self._unavailable(ticker, 0, 0, captured, f"PROVIDER_ERROR:{type(exc).__name__}")
        if status in {401, 403}:
            return self._unavailable(
                ticker, 0, 0, captured, "ENTITLEMENT_UNAVAILABLE", CertificationStatus.ENTITLEMENT_UNAVAILABLE,
            )
        events = payload.get("events") if isinstance(payload, Mapping) else None
        periods: list[dict[str, Any]] = []
        for event in events or ():
            if not isinstance(event, Mapping) or not event.get("year") or not event.get("quarter"):
                continue
            periods.append({
                "fiscal_year": int(event["year"]), "fiscal_quarter": int(event["quarter"]),
                "call_date": event.get("call_date") or event.get("conference_date") or event.get("date"),
                "provider_event_id": event.get("id") or event.get("event_id"),
            })
        periods.sort(key=lambda item: (item["fiscal_year"], item["fiscal_quarter"]), reverse=True)
        if not periods:
            return self._unavailable(ticker, 0, 0, captured, "TRANSCRIPT_DATA_UNAVAILABLE")
        digest = _hash({"ticker": ticker, "periods": periods, "provider": self._provider})
        return GovernedRecord(ProvenanceEnvelope(
            provider=self._provider, dataset_family=DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
            endpoint_or_source_family="EARNINGS_TRANSCRIPT_INDEX", symbol=ticker,
            canonical_security_id=ticker, capture_timestamp=captured,
            raw_evidence_id=f"TRANSCRIPT_INDEX:{ticker}:{digest[:20]}", content_hash=digest,
            freshness_status="CAPTURED", certification_status=CertificationStatus.UNVERIFIED_SHADOW,
            license_class=self._license.value, display_permission=UsePermission.CONTEXT_ONLY,
            derived_use_permission=UsePermission.CONTEXT_ONLY,
            market_coverage_class=MarketCoverageClass.UNKNOWN, adapter_version=TRANSCRIPT_ADAPTER_VERSION,
        ), {"periods": periods}, (
            "The period index contains metadata only and grants no transcript publication permission.",
        ))

    def _earningscall_transcript(self, ticker: str, year: int, quarter: int) -> Any:
        return self._get(
            f"{self._base}/transcript",
            params={"apikey": self._key, "exchange": "nasdaq", "symbol": ticker.lower(),
                    "year": year, "quarter": quarter}, timeout=20,
        )

    def _latest_earningscall_event(self, ticker: str) -> Mapping[str, Any] | None:
        response = self._get(
            f"{self._base}/events",
            params={"apikey": self._key, "exchange": "nasdaq", "symbol": ticker.lower()}, timeout=20,
        )
        if int(getattr(response, "status_code", 0) or 0) != 200:
            return None
        payload = response.json()
        events = payload.get("events") if isinstance(payload, Mapping) else None
        valid = [event for event in (events or []) if isinstance(event, Mapping) and event.get("year") and event.get("quarter")]
        return max(valid, key=lambda event: (int(event["year"]), int(event["quarter"]))) if valid else None

    def _earningscall_event(self, ticker: str, year: int, quarter: int) -> Mapping[str, Any] | None:
        response = self._get(
            f"{self._base}/events",
            params={"apikey": self._key, "exchange": "nasdaq", "symbol": ticker.lower()}, timeout=20,
        )
        if int(getattr(response, "status_code", 0) or 0) != 200:
            return None
        payload = response.json()
        events = payload.get("events") if isinstance(payload, Mapping) else None
        return next((event for event in (events or ()) if isinstance(event, Mapping)
                     and int(event.get("year") or 0) == int(year)
                     and int(event.get("quarter") or 0) == int(quarter)), None)

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
    permissions = transcript_license_permissions(evidence.provenance.license_class)
    return GovernedRecord(ProvenanceEnvelope(
        provider="ATLAS_AI", dataset_family=DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
        endpoint_or_source_family="TRANSCRIPT_DERIVED_INSIGHT", symbol=evidence.provenance.symbol,
        canonical_security_id=evidence.provenance.canonical_security_id, source_timestamp=evidence.provenance.source_timestamp,
        capture_timestamp=captured, effective_period=evidence.provenance.effective_period,
        fiscal_period=evidence.provenance.fiscal_period, raw_evidence_id=f"TRANSCRIPT_DERIVED:{digest[:24]}",
        content_hash=digest, freshness_status="DERIVED", certification_status=CertificationStatus.UNVERIFIED_SHADOW,
        license_class=evidence.provenance.license_class,
        display_permission=permissions["derived_summary_display"],
        derived_use_permission=permissions["derived_summary_display"],
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
    prohibited = {"raw_content", "source_excerpt", "transcript", "prepared_remarks", "qa_segments"}
    def sanitized(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: sanitized(item) for key, item in value.items() if key not in prohibited}
        if isinstance(value, list):
            return [sanitized(item) for item in value]
        if isinstance(value, tuple):
            return [sanitized(item) for item in value]
        return value
    payload = sanitized(dict(insight.payload))
    payload["semantic_status"] = "AVAILABLE"
    payload["source_evidence_ids"] = [payload.get("source_transcript_evidence_id")]
    return payload


def build_internal_transcript_research_package(
    evidence: GovernedRecord, insight: GovernedRecord | None = None,
) -> dict[str, Any]:
    """Create an internal-only research package without decision authority."""
    available = bool(evidence.payload.get("raw_content_hash"))
    derived = dict(insight.payload) if insight is not None else {}
    return {
        "version": "ATLAS_TRANSCRIPT_RESEARCH_PACKAGE_V1",
        "status": "AVAILABLE" if available else "DATA_UNAVAILABLE",
        "license_state": evidence.provenance.license_class,
        "non_scoring": True, "customer_publication_prohibited": True,
        "latest_available_period": evidence.payload.get("resolved_period") or evidence.provenance.effective_period,
        "transcript_evidence_id": evidence.provenance.raw_evidence_id,
        "ai_summary": derived.get("management_summary"),
        "key_positives": list(derived.get("key_positives") or ()),
        "key_risks": list(derived.get("material_risks") or derived.get("key_risks") or ()),
        "guidance_context": derived.get("guidance_context"),
        "prepared_remarks": list(evidence.payload.get("prepared_sections") or ()),
        "qa_structure": list(evidence.payload.get("qa_segments") or ()),
        "limitations": list(evidence.limitations),
        "protected_decision_fields": ("six_pillars", "fair_value", "opportunity", "decision_confidence", "canonical_action"),
    }


def _transcript_text(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("text") or payload.get("content")
    return value if isinstance(value, str) and value.strip() else None


__all__ = [
    "COMMERCIAL_LAUNCH_REQUIRES_TRANSCRIPT_ENTERPRISE_LICENSE", "ConfiguredTranscriptProvider",
    "TRANSCRIPT_LICENSE_PERMISSIONS", "TranscriptLicenseState", "build_internal_transcript_research_package",
    "build_transcript_derived_insight", "enforce_transcript_commercial_launch_license",
    "transcript_customer_projection", "transcript_license_permissions",
]
