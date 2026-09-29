"""Field/family-scoped Finnhub canonical authority.

The certified adapter delegates transport and normalization to the preserved
shadow adapter, then upgrades only explicitly authorized capabilities.  It is
not a global provider switch and cannot authorize unresolved estimate fields,
live partial-market data, Bulk, or undocumented metrics.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from services.finnhub_shadow_provider import (
    FINNHUB_PAID_CORE_CERTIFICATION_LICENSE,
    FinnhubShadowAdapter,
)
from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, GovernedRecord, UsePermission,
    require_certified_calculation,
)


AUTHORITY_VERSION = "FINNHUB_CANONICAL_AUTHORITY_V1_FIELD_SCOPED"
CANONICAL_AUTHORITY = "CANONICAL_CERTIFIED"
CONTRACT_PENDING = "CONTRACT_PENDING"

AUTHORITY_MATRIX = {
    "company_profile": {
        "state": CANONICAL_AUTHORITY,
        "authorized_fields": ("name", "exchange", "industry", "country", "currency", "shares_outstanding_millions"),
        "limitations": ("CLASSIFICATION_REQUIRES_GOVERNED_ATLAS_ROUTING",),
    },
    "financial_statements": {
        "state": CANONICAL_AUTHORITY,
        "authorized_fields": (
            "revenue", "gross_profit", "operating_income", "ebit", "net_income",
            "cash", "short_term_debt", "long_term_debt", "total_debt",
            "operating_cash_flow", "capex", "free_cash_flow",
            "weighted_average_shares_basic", "weighted_average_shares_diluted",
            "fiscal_period", "filing_identity",
        ),
        "limitations": ("ONLY_NORMALIZED_FINITE_FACTS", "NO_FORWARD_INFERENCE"),
    },
    "basic_financials": {
        "state": CANONICAL_AUTHORITY,
        "authorized_fields": (
            "market_capitalization", "shares_outstanding", "grossMarginTTM",
            "operatingMarginTTM", "netProfitMarginTTM", "revenueGrowthTTMYoy",
            "epsGrowthTTMYoy", "roeTTM", "roaTTM", "payoutRatioTTM",
        ),
        "limitations": ("CURRENT_SHARES_HAVE_NO_PROVIDER_TIMESTAMP", "ONLY_CONTRACTED_METRICS"),
    },
    "historical_ohlcv": {
        "state": CANONICAL_AUTHORITY,
        "authorized_fields": ("open", "high", "low", "close", "completed_session_volume"),
        "limitations": (
            "SPLIT_ADJUSTED_ONLY", "NOT_DIVIDEND_ADJUSTED",
            "VOLUME_ONLY_AFTER_COMPLETED_POST_4PM_SESSION",
        ),
    },
    "splits": {"state": CANONICAL_AUTHORITY, "authorized_fields": ("corporate_actions",), "limitations": ()},
    "eps_estimates": {"state": CONTRACT_PENDING, "reason": "UNIT_CURRENCY_SCALE_CONTRACT_PENDING"},
    "revenue_estimates": {"state": CONTRACT_PENDING, "reason": "UNIT_CURRENCY_SCALE_CONTRACT_PENDING"},
    "ebit_estimates": {"state": CONTRACT_PENDING, "reason": "UNIT_CURRENCY_SCALE_CONTRACT_PENDING"},
    "ebitda_estimates": {"state": CONTRACT_PENDING, "reason": "UNIT_CURRENCY_SCALE_CONTRACT_PENDING"},
    "live_quote": {"state": "DISPLAY_ONLY", "reason": "PARTIAL_REALTIME_CANNOT_SCORE"},
    "bulk": {"state": "NOT_CERTIFIED", "reason": "BULK_PRODUCTION_PATH_NOT_CERTIFIED"},
}

AUTHORIZED_CAPABILITIES = frozenset(
    capability for capability, contract in AUTHORITY_MATRIX.items()
    if contract["state"] == CANONICAL_AUTHORITY
)


def authority_contract(capability: str) -> dict[str, Any]:
    return {"authority_version": AUTHORITY_VERSION, "capability": capability,
            **dict(AUTHORITY_MATRIX.get(capability) or {"state": "NOT_AUTHORIZED"})}


class FinnhubCanonicalAdapter:
    """Certified-calculation adapter for the explicitly authorized families."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["license_class"] = FINNHUB_PAID_CORE_CERTIFICATION_LICENSE
        self._delegate = FinnhubShadowAdapter(*args, **kwargs)

    def fetch(self, capability: str, symbol: str, **parameters: Any) -> GovernedRecord:
        contract = authority_contract(capability)
        record = self._delegate.fetch(capability, symbol, **parameters)
        if contract["state"] != CANONICAL_AUTHORITY:
            return GovernedRecord(
                record.provenance, record.payload,
                tuple(record.limitations) + (f"AUTHORITY_STATE:{contract['state']}",),
            )
        if record.provenance.license_class != FINNHUB_PAID_CORE_CERTIFICATION_LICENSE:
            raise PermissionError("FINNHUB_PAID_CORE_LICENSE_REQUIRED")
        if record.provenance.certification_status != CertificationStatus.UNVERIFIED_SHADOW:
            # Unavailable and entitlement records retain their exact fail-closed
            # provider status and are never promoted by the authority wrapper.
            return record
        provenance = replace(
            record.provenance,
            dataset_family=DatasetFamily.CANONICAL_QUANTITATIVE,
            certification_status=CertificationStatus.CERTIFIED,
            derived_use_permission=UsePermission.CERTIFIED_CALCULATION,
            display_permission=UsePermission.PROHIBITED,
            adapter_version=f"{record.provenance.adapter_version}+{AUTHORITY_VERSION}",
        )
        limitations = tuple(record.limitations) + tuple(contract.get("limitations") or ()) + (
            f"AUTHORIZED_CAPABILITY:{capability}",
        )
        certified = GovernedRecord(provenance, record.payload, limitations)
        require_certified_calculation(certified)
        return certified


__all__ = [
    "AUTHORITY_MATRIX", "AUTHORITY_VERSION", "AUTHORIZED_CAPABILITIES",
    "CANONICAL_AUTHORITY", "CONTRACT_PENDING", "FinnhubCanonicalAdapter",
    "authority_contract",
]
