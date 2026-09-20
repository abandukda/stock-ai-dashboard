"""Provider-neutral governed evidence contracts.

Vendor response shapes must terminate in adapters.  Nothing in this module
selects a provider or grants decision authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


CANONICAL_SCHEMA_VERSION = "ATLAS_PROVIDER_CONTRACTS_V1"


class DatasetFamily(str, Enum):
    CANONICAL_QUANTITATIVE = "CANONICAL_QUANTITATIVE"
    CONTEXTUAL_EXTERNAL_EVIDENCE = "CONTEXTUAL_EXTERNAL_EVIDENCE"
    OPTIONAL_QUALITATIVE_INTELLIGENCE = "OPTIONAL_QUALITATIVE_INTELLIGENCE"
    LIVE_DISPLAY_ONLY = "LIVE_DISPLAY_ONLY"
    CERTIFIED_ANALYTICAL = "CERTIFIED_ANALYTICAL"


class MarketCoverageClass(str, Enum):
    FULL_CONSOLIDATED = "FULL_CONSOLIDATED"
    PARTIAL_REALTIME = "PARTIAL_REALTIME"
    UNKNOWN = "UNKNOWN"


class CertificationStatus(str, Enum):
    UNVERIFIED_SHADOW = "UNVERIFIED_SHADOW"
    CERTIFIED = "CERTIFIED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    ENTITLEMENT_UNAVAILABLE = "ENTITLEMENT_UNAVAILABLE"
    REJECTED = "REJECTED"


class UsePermission(str, Enum):
    PROHIBITED = "PROHIBITED"
    SHADOW_ONLY = "SHADOW_ONLY"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    DISPLAY_ONLY = "DISPLAY_ONLY"
    CERTIFIED_CALCULATION = "CERTIFIED_CALCULATION"


@dataclass(frozen=True)
class ProvenanceEnvelope:
    provider: str
    dataset_family: DatasetFamily
    endpoint_or_source_family: str
    symbol: str
    canonical_security_id: str
    capture_timestamp: str
    raw_evidence_id: str
    source_timestamp: str | None = None
    effective_period: str | None = None
    fiscal_period: str | None = None
    content_hash: str | None = None
    freshness_status: str = "UNKNOWN"
    certification_status: CertificationStatus = CertificationStatus.UNVERIFIED_SHADOW
    license_class: str = "UNKNOWN"
    display_permission: UsePermission = UsePermission.PROHIBITED
    derived_use_permission: UsePermission = UsePermission.SHADOW_ONLY
    market_coverage_class: MarketCoverageClass = MarketCoverageClass.UNKNOWN
    venue_coverage_description: str | None = None
    covered_venues: tuple[str, ...] = ()
    estimated_volume_coverage_pct: float | None = None
    coverage_as_of: str | None = None
    provider_statement_reference: str | None = None
    adapter_version: str = "UNKNOWN"
    canonical_schema_version: str = CANONICAL_SCHEMA_VERSION
    supersedes: str | None = None
    superseded_by: str | None = None
    source_record_version: str | None = None

    def validate(self) -> None:
        required = (
            self.provider, self.endpoint_or_source_family, self.symbol,
            self.canonical_security_id, self.capture_timestamp,
            self.raw_evidence_id, self.adapter_version,
            self.canonical_schema_version,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("incomplete governed provenance envelope")
        if (
            self.dataset_family == DatasetFamily.LIVE_DISPLAY_ONLY
            and self.derived_use_permission == UsePermission.CERTIFIED_CALCULATION
        ):
            raise ValueError("live display evidence cannot authorize certified calculations")
        if (
            self.market_coverage_class == MarketCoverageClass.PARTIAL_REALTIME
            and self.derived_use_permission == UsePermission.CERTIFIED_CALCULATION
        ):
            raise ValueError("partial real-time evidence cannot authorize certified calculations")


@dataclass(frozen=True)
class GovernedRecord:
    provenance: ProvenanceEnvelope
    payload: Mapping[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.provenance.validate()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["provenance"]["dataset_family"] = self.provenance.dataset_family.value
        value["provenance"]["certification_status"] = self.provenance.certification_status.value
        value["provenance"]["display_permission"] = self.provenance.display_permission.value
        value["provenance"]["derived_use_permission"] = self.provenance.derived_use_permission.value
        value["provenance"]["market_coverage_class"] = self.provenance.market_coverage_class.value
        return value


def require_certified_calculation(record: GovernedRecord) -> Mapping[str, Any]:
    """Runtime boundary used by any future methodology consumer."""
    p = record.provenance
    if p.dataset_family not in {
        DatasetFamily.CANONICAL_QUANTITATIVE,
        DatasetFamily.CERTIFIED_ANALYTICAL,
    }:
        raise PermissionError(f"dataset family {p.dataset_family.value} is non-scoring")
    if p.certification_status != CertificationStatus.CERTIFIED:
        raise PermissionError("record has not passed ATLAS certification")
    if p.derived_use_permission != UsePermission.CERTIFIED_CALCULATION:
        raise PermissionError("record is not authorized for certified calculations")
    if p.market_coverage_class == MarketCoverageClass.PARTIAL_REALTIME:
        raise PermissionError("partial real-time evidence is display-only")
    return record.payload


# Domain aliases intentionally share one governed envelope while preserving
# distinct semantic contract names for capability typing.
CanonicalSecurityReference = GovernedRecord
CanonicalFinancialStatement = GovernedRecord
CanonicalFundamentalFact = GovernedRecord
CanonicalPriceBar = GovernedRecord
CertifiedPriceBar = GovernedRecord
LiveMarketQuote = GovernedRecord
LiveMarketVolume = GovernedRecord
CorporateAction = GovernedRecord
AnalystEstimateContext = GovernedRecord
AnalystRecommendationContext = GovernedRecord
AnalystActionContext = GovernedRecord
InstitutionalOwnershipContext = GovernedRecord
InsiderTransactionContext = GovernedRecord
ContextualNewsItem = GovernedRecord
RegulatoryFiling = GovernedRecord
CompanyProfileContext = GovernedRecord
PeerContext = GovernedRecord
TranscriptEvidence = GovernedRecord
TranscriptDerivedInsight = GovernedRecord


__all__ = [name for name in globals() if name[0].isupper()] + ["require_certified_calculation"]
