from datetime import datetime, timezone

from services.canonical_valuation_provider_contract import (
    PROVIDER_ROLE_FREEZE, REPRESENTATIVE_SYMBOLS, ROUTE_REQUIREMENTS,
    acceptance_matrix_template, evaluate_evidence_record,
)
from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, GovernedRecord, ProvenanceEnvelope, UsePermission,
)


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc).isoformat()


def _fact(value, *, forward=False, **overrides):
    item = {
        "value": value, "unit": "USD", "currency": "USD", "frequency": "ANNUAL",
        "fiscal_period": "FY2027" if forward else "FY2025", "period_end": "2027-12-31" if forward else "2025-12-31",
        "capture_timestamp": NOW, "evidence_id": "E-1",
    }
    if forward:
        item.update({"estimate_horizon": "FY+1", "provider_update_timestamp": NOW,
                     "revision_semantics": "CURRENT_CONSENSUS", "consensus_based": True,
                     "contributor_count": 8})
    else:
        item["filing_or_source_identity"] = "10-K:0001"
    item.update(overrides)
    return item


def _record(*, frequency="ANNUAL", certified=True):
    historical = {name: _fact(100) for name in (
        "revenue", "gross_profit", "operating_income", "ebit", "net_income", "cash",
        "short_term_debt", "long_term_debt", "total_debt", "operating_cash_flow", "capex",
        "free_cash_flow", "current_shares_outstanding", "weighted_average_shares_basic",
        "weighted_average_shares_diluted",
    )}
    forward = {
        "forward_eps": _fact(10, forward=True, unit="PER_SHARE", frequency=frequency),
        "forward_revenue": _fact(120, forward=True, frequency=frequency),
        "forward_ebit": _fact(30, forward=True, frequency=frequency),
        "forward_ebitda": _fact(35, forward=True, frequency=frequency),
    }
    return GovernedRecord(ProvenanceEnvelope(
        provider="CANDIDATE", dataset_family=DatasetFamily.CANONICAL_QUANTITATIVE,
        endpoint_or_source_family="VALUATION_EVIDENCE_PACKAGE", symbol="AAPL",
        canonical_security_id="AAPL", capture_timestamp=NOW, raw_evidence_id="RAW-1",
        provider_statement_reference="CANDIDATE_CONTRACT_V1", adapter_version="ADAPTER_V1",
        certification_status=CertificationStatus.CERTIFIED if certified else CertificationStatus.UNVERIFIED_SHADOW,
        derived_use_permission=UsePermission.CERTIFIED_CALCULATION if certified else UsePermission.SHADOW_ONLY,
    ), {"historical": historical, "forward": forward, "valuation_inputs": {
        "justified_pe": {"value": 20, "certification_status": "CERTIFIED", "evidence_id": "PEERS-1",
                         "source_methodology": "DETERMINISTIC_PEER_MEDIAN"},
        "multiple_basis": {"value": "CERTIFIED_PEERS", "certification_status": "CERTIFIED",
                           "evidence_id": "PEERS-1", "source_methodology": "DETERMINISTIC_PEER_MEDIAN"},
    }})


def test_provider_roles_are_frozen_outside_canonical_valuation():
    assert "CANONICAL_VALUATION_INPUTS" in PROVIDER_ROLE_FREEZE["FINNHUB"]["prohibited"]
    assert PROVIDER_ROLE_FREEZE["EARNINGSCALL"]["license"] == "DEVELOPMENT_PRECOMMERCIAL"
    assert "CUSTOMER_PUBLICATION" in PROVIDER_ROLE_FREEZE["EARNINGSCALL"]["prohibited"]


def test_production_reachable_forward_pe_contract_passes_without_running_valuation():
    result = evaluate_evidence_record(_record())
    assert result["boundary_status"] == "PASS"
    assert result["current_share_debt_cash_complete"] is True
    assert result["valuation_routes"]["VAL_FORWARD_PE_V1"]["status"] == "PASS"
    assert result["atlas_fair_value_possible"] is True


def test_ambiguous_frequency_fails_without_date_or_magnitude_inference():
    result = evaluate_evidence_record(_record(frequency=""))
    eps = result["field_acceptance"]["forward_eps"]
    assert eps["status"] == "CONTRACT_INCOMPLETE"
    assert "FREQUENCY_MISSING" in eps["blockers"]
    assert result["valuation_routes"]["VAL_FORWARD_PE_V1"]["status"] == "FAIL"


def test_unverified_shadow_record_cannot_pass_acceptance_boundary():
    result = evaluate_evidence_record(_record(certified=False))
    assert result["boundary_status"] == "FAIL"
    assert result["atlas_fair_value_possible"] is False


def test_raw_unprovenanced_multiple_cannot_complete_a_route():
    record = _record()
    payload = dict(record.payload)
    payload["valuation_inputs"] = {"justified_pe": 20, "multiple_basis": "PEERS"}
    unsafe = GovernedRecord(record.provenance, payload)
    result = evaluate_evidence_record(unsafe)
    assert result["valuation_routes"]["VAL_FORWARD_PE_V1"]["status"] == "FAIL"
    assert "justified_pe:MISSING" in result["valuation_routes"]["VAL_FORWARD_PE_V1"]["blockers"]


def test_templates_cover_registered_routes_and_fixed_cross_sector_set():
    template = acceptance_matrix_template()
    assert tuple(template["companies"]) == REPRESENTATIVE_SYMBOLS
    assert set(template["valuation_routes"]) == set(ROUTE_REQUIREMENTS)
    assert template["valuation_routes"]["VAL_FCFF_DCF_V1"]["status"] == "NOT_TESTED"
