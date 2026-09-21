"""Provider-neutral acceptance contract for canonical valuation evidence.

This module evaluates normalized shadow evidence only.  It does not acquire
vendor data, select a production authority, or execute valuation methodology.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol

from engines.methodology_registry import methodology
from services.provider_domain_contracts import (
    CertificationStatus,
    DatasetFamily,
    GovernedRecord,
    UsePermission,
)


VERSION = "ATLAS_CANONICAL_VALUATION_PROVIDER_ACCEPTANCE_V1"
REPRESENTATIVE_SYMBOLS = ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA")

PROVIDER_ROLE_FREEZE = {
    "FINNHUB": {
        "eligible": (
            "LIVE_DISPLAY_PRICES", "COMPLETED_SESSION_OHLCV", "TECHNICAL_INDICATORS",
            "CONTEXTUAL_ANALYST_DATA", "NEWS", "OWNERSHIP", "INSIDERS", "SEC_FILINGS",
            "NONCANONICAL_ESTIMATE_CONTEXT",
        ),
        "prohibited": ("CANONICAL_FUNDAMENTALS", "CANONICAL_FORWARD_ESTIMATES", "CANONICAL_VALUATION_INPUTS"),
        "forward_estimates": "CONTEXT_ONLY",
        "canonical_valuation_authority": False,
        "status": "MARKET_TECHNICAL_PASS_WITH_LIMITATIONS;VALUATION_FAIL",
    },
    "EARNINGSCALL": {
        "eligible": ("TRANSCRIPT_CONTEXT",),
        "prohibited": ("SCORING", "CUSTOMER_PUBLICATION", "CANONICAL_VALUATION_INPUTS"),
        "license": "DEVELOPMENT_PRECOMMERCIAL",
        "scoring": False,
        "customer_publication": False,
        "canonical_valuation_authority": False,
        "status": "PASS_WITH_LIMITATIONS_FOR_DEVELOPMENT",
    },
}


HISTORICAL_FIELDS = (
    "revenue", "gross_profit", "operating_income", "ebit", "ebitda", "net_income",
    "cash", "short_term_debt", "long_term_debt", "total_debt", "operating_cash_flow",
    "capex", "free_cash_flow", "current_shares_outstanding",
    "weighted_average_shares_basic", "weighted_average_shares_diluted",
)
FORWARD_FIELDS = ("forward_eps", "forward_revenue", "forward_ebit", "forward_ebitda", "forward_fcf")

HISTORICAL_METADATA = (
    "unit", "currency", "frequency", "fiscal_period", "period_end", "filing_or_source_identity",
    "capture_timestamp", "evidence_id",
)
FORWARD_METADATA = (
    "unit", "currency", "frequency", "fiscal_period", "estimate_horizon", "period_end",
    "provider_update_timestamp", "capture_timestamp", "revision_semantics", "evidence_id",
)

ROUTE_REQUIREMENTS = {
    "VAL_FORWARD_PE_V1": ("forward_eps", "forward_eps_period", "justified_pe", "multiple_basis"),
    "VAL_EV_EBITDA_V1": (
        "forward_ebitda", "justified_ev_ebitda", "multiple_basis", "total_debt",
        "cash", "weighted_average_shares_diluted",
    ),
    "VAL_P_FCF_V1": ("normalized_fcf", "justified_p_fcf", "multiple_basis", "weighted_average_shares_diluted"),
    "VAL_FCFF_DCF_V1": ("forecast_fcff", "wacc", "terminal_growth", "total_debt", "cash", "weighted_average_shares_diluted"),
    "VAL_DDM_GORDON_V1": ("dividend_next", "cost_of_equity", "terminal_growth"),
}


class CanonicalValuationProvider(Protocol):
    """Adapter boundary for a future candidate provider.

    Vendor-specific response shapes must terminate before this method returns.
    The harness accepts only one governed, normalized evidence package per
    security and never calls a production publication path.
    """

    provider_id: str
    provider_contract_reference: str
    adapter_version: str

    def valuation_evidence(self, symbol: str) -> GovernedRecord: ...


@dataclass(frozen=True)
class FieldAcceptance:
    field: str
    status: str
    blockers: tuple[str, ...]


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != () and value != []


def _field_result(name: str, item: Any, *, forward: bool) -> FieldAcceptance:
    if not isinstance(item, Mapping) or not _present(item.get("value")):
        return FieldAcceptance(name, "DATA_UNAVAILABLE", ("VALUE_MISSING",))
    blockers: list[str] = []
    required = FORWARD_METADATA if forward else HISTORICAL_METADATA
    for key in required:
        if not _present(item.get(key)):
            blockers.append(f"{key.upper()}_MISSING")
    frequency = str(item.get("frequency") or "").upper()
    if frequency and frequency not in {"ANNUAL", "QUARTERLY"}:
        blockers.append("FREQUENCY_NOT_EXPLICIT_ANNUAL_OR_QUARTERLY")
    if forward and item.get("consensus_based") is True and not _present(item.get("contributor_count")):
        blockers.append("CONTRIBUTOR_COUNT_MISSING")
    status = "CERTIFIED_INPUT" if not blockers else "CONTRACT_INCOMPLETE"
    return FieldAcceptance(name, status, tuple(blockers))


def _assumption_blockers(name: str, item: Any) -> tuple[str, ...]:
    if not isinstance(item, Mapping) or not _present(item.get("value")):
        return ("MISSING",)
    blockers = []
    if str(item.get("certification_status") or "").upper() != "CERTIFIED":
        blockers.append("NOT_CERTIFIED")
    if not _present(item.get("evidence_id")):
        blockers.append("EVIDENCE_ID_MISSING")
    if not _present(item.get("source_methodology")):
        blockers.append("SOURCE_METHODOLOGY_MISSING")
    return tuple(blockers)


def _route_result(route: str, accepted: Mapping[str, FieldAcceptance], inputs: Mapping[str, Any]) -> dict[str, Any]:
    registered = methodology(route)
    requirements = ROUTE_REQUIREMENTS[route]
    blockers: list[str] = []
    for name in requirements:
        field = accepted.get(name)
        if field is not None:
            if field.status != "CERTIFIED_INPUT":
                blockers.extend(f"{name}:{reason}" for reason in field.blockers)
        else:
            blockers.extend(f"{name}:{reason}" for reason in _assumption_blockers(name, inputs.get(name)))
    return {
        "methodology_id": route,
        "methodology_name": registered.name,
        "status": "PASS" if not blockers else "FAIL",
        "blockers": tuple(blockers),
    }


def evaluate_evidence_record(record: GovernedRecord) -> dict[str, Any]:
    """Evaluate one normalized candidate record without running valuation."""
    provenance = record.provenance
    boundary_blockers = []
    if provenance.dataset_family != DatasetFamily.CANONICAL_QUANTITATIVE:
        boundary_blockers.append("DATASET_FAMILY_NOT_CANONICAL_QUANTITATIVE")
    if provenance.certification_status != CertificationStatus.CERTIFIED:
        boundary_blockers.append("PROVIDER_RECORD_NOT_CERTIFIED")
    if provenance.derived_use_permission != UsePermission.CERTIFIED_CALCULATION:
        boundary_blockers.append("CERTIFIED_CALCULATION_NOT_AUTHORIZED")
    if not provenance.provider_statement_reference:
        boundary_blockers.append("PROVIDER_CONTRACT_REFERENCE_MISSING")
    if not provenance.raw_evidence_id:
        boundary_blockers.append("EVIDENCE_IDENTITY_MISSING")

    payload = record.payload
    historical = payload.get("historical") if isinstance(payload.get("historical"), Mapping) else {}
    forward = payload.get("forward") if isinstance(payload.get("forward"), Mapping) else {}
    valuation_inputs = payload.get("valuation_inputs") if isinstance(payload.get("valuation_inputs"), Mapping) else {}
    accepted = {
        **{name: _field_result(name, historical.get(name), forward=False) for name in HISTORICAL_FIELDS},
        **{name: _field_result(name, forward.get(name), forward=True) for name in FORWARD_FIELDS},
    }
    route_fields = dict(accepted)
    route_fields["forward_eps_period"] = accepted["forward_eps"]
    route_fields["total_debt"] = accepted["total_debt"]
    route_fields["cash"] = accepted["cash"]
    route_fields["weighted_average_shares_diluted"] = accepted["weighted_average_shares_diluted"]
    route_fields["normalized_fcf"] = accepted["free_cash_flow"]
    routes = {
        route: _route_result(route, route_fields, valuation_inputs)
        for route in ROUTE_REQUIREMENTS
    }
    certified_methods = tuple(route for route, item in routes.items() if item["status"] == "PASS")
    possible = not boundary_blockers and bool(certified_methods)
    capital_bridge_complete = all(
        accepted[name].status == "CERTIFIED_INPUT"
        for name in ("current_shares_outstanding", "total_debt", "cash")
    )
    return {
        "version": VERSION,
        "provider": provenance.provider,
        "symbol": provenance.symbol,
        "boundary_status": "PASS" if not boundary_blockers else "FAIL",
        "boundary_blockers": tuple(boundary_blockers),
        "historical_financial_contract_complete": all(
            accepted[name].status == "CERTIFIED_INPUT" for name in HISTORICAL_FIELDS if name != "ebitda"
        ),
        "forward_estimate_contract_complete": all(
            accepted[name].status == "CERTIFIED_INPUT" for name in FORWARD_FIELDS if name != "forward_fcf"
        ),
        "current_share_debt_cash_complete": capital_bridge_complete,
        "field_acceptance": {name: asdict(item) for name, item in accepted.items()},
        "valuation_routes": routes,
        "certified_valuation_methods": certified_methods,
        "atlas_fair_value_possible": possible,
        "opportunity_possible": possible,
        "confidence_possible": possible,
        "action_possible": possible,
    }


def acceptance_report(provider: CanonicalValuationProvider) -> dict[str, Any]:
    companies = {symbol: evaluate_evidence_record(provider.valuation_evidence(symbol)) for symbol in REPRESENTATIVE_SYMBOLS}
    passing = sum(bool(item["certified_valuation_methods"]) for item in companies.values())
    boundary_pass = all(item["boundary_status"] == "PASS" for item in companies.values())
    if boundary_pass and passing == len(REPRESENTATIVE_SYMBOLS):
        verdict = "PASS"
    elif boundary_pass and passing > len(REPRESENTATIVE_SYMBOLS) / 2:
        verdict = "PASS_WITH_LIMITATIONS"
    else:
        verdict = "FAIL"
    return {
        "version": VERSION,
        "provider": provider.provider_id,
        "provider_contract_reference": provider.provider_contract_reference,
        "adapter_version": provider.adapter_version,
        "representative_symbols": REPRESENTATIVE_SYMBOLS,
        "companies": companies,
        "companies_with_certified_valuation_route": passing,
        "verdict": verdict,
        "production_authority_changed": False,
        "publication_performed": False,
    }


def acceptance_matrix_template() -> dict[str, Any]:
    return {
        "version": VERSION,
        "provider": "CANDIDATE_PROVIDER",
        "historical_contract": "NOT_TESTED",
        "forward_estimate_contract": "NOT_TESTED",
        "valuation_routes": {
            route: {"status": "NOT_TESTED", "required_inputs": requirements, "blockers": ()}
            for route, requirements in ROUTE_REQUIREMENTS.items()
        },
        "companies": {
            symbol: {
                "historical_financial_contract_complete": None,
                "forward_estimate_contract_complete": None,
                "current_share_debt_cash_complete": None,
                "certified_valuation_methods": (),
                "atlas_fair_value_possible": None,
                "opportunity_possible": None,
                "confidence_possible": None,
                "action_possible": None,
            }
            for symbol in REPRESENTATIVE_SYMBOLS
        },
        "cross_sector_coverage": {
            "status": "NOT_TESTED",
            "companies_with_certified_valuation_route": None,
            "companies_tested": len(REPRESENTATIVE_SYMBOLS),
        },
        "provenance_quality": "NOT_TESTED",
        "commercial_licensing_notes": None,
        "canonical_verdict": "NOT_TESTED",
    }


__all__ = [
    "CanonicalValuationProvider", "FORWARD_FIELDS", "FORWARD_METADATA", "HISTORICAL_FIELDS",
    "HISTORICAL_METADATA", "PROVIDER_ROLE_FREEZE", "REPRESENTATIVE_SYMBOLS", "ROUTE_REQUIREMENTS",
    "VERSION", "acceptance_matrix_template", "acceptance_report", "evaluate_evidence_record",
]
