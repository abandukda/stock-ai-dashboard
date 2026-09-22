from copy import deepcopy
from pathlib import Path

from scripts.finnhub_core_entitlement_smoke import (
    ENTITLEMENT_SMOKE_FAIL,
    ENTITLEMENT_SMOKE_PASS,
    REQUIRED_CAPABILITIES,
    SMOKE_SAMPLE,
    build_smoke_report,
    exit_code,
)
from scripts.finnhub_p_fcf_peer_certification import (
    ATLAS_INTEGRATION_FAILURE,
    CREDENTIAL_ENTITLEMENT_UNAVAILABLE,
    PROVIDER_CONTRACT_UNRESOLVED,
    PROVIDER_DATA_UNAVAILABLE,
    TARGETS,
)


class _Record:
    def __init__(self, value): self.value = value
    def as_dict(self): return deepcopy(self.value)


def _available(capability, symbol):
    payload = {
        "company_profile": {"name": symbol, "industry": "Representative", "currency": "USD"},
        "financial_statements": {"reports": [{
            "fiscal_period": "FY", "fiscal_date": "2025-12-31",
            "canonical_facts": {
                "free_cash_flow": {"value": 100.0, "currency": "USD"},
                "weighted_average_shares_diluted": {"value": 10.0, "normalized_unit": "SHARES"},
            },
        }]},
        "basic_financials": {"market_capitalization": 1000.0, "market_capitalization_lineage": {"unit": "USD"}},
    }[capability]
    return {"payload": payload, "provenance": {
        "provider": "FINNHUB", "certification_status": "UNVERIFIED_SHADOW",
        "endpoint_or_source_family": capability.upper(), "capture_timestamp": "2026-09-21T20:00:00+00:00",
        "raw_evidence_id": f"FINNHUB:{capability}:{symbol}",
    }}


class _Adapter:
    def __init__(self, replacement=None, raises=False):
        self.replacement = replacement or {}
        self.raises = raises
    def fetch(self, capability, symbol):
        if self.raises and capability == "company_profile" and symbol == next(iter(SMOKE_SAMPLE)):
            raise RuntimeError("bounded fixture failure")
        return _Record(self.replacement.get((symbol, capability), _available(capability, symbol)))


def _unavailable(status, reason):
    return {"payload": {"reason": reason}, "provenance": {
        "provider": "FINNHUB", "certification_status": status,
        "endpoint_or_source_family": "FINANCIAL_STATEMENTS", "capture_timestamp": "2026-09-21T20:00:00+00:00",
        "raw_evidence_id": "FINNHUB:unavailable",
    }}


def test_non_demo_cross_sector_smoke_passes_only_when_all_required_families_are_complete():
    report = build_smoke_report(_Adapter())
    assert set(SMOKE_SAMPLE).isdisjoint(TARGETS)
    assert len(set(SMOKE_SAMPLE.values())) == len(SMOKE_SAMPLE)
    assert tuple(report["required_capabilities"]) == REQUIRED_CAPABILITIES
    assert report["state"] == ENTITLEMENT_SMOKE_PASS
    assert report["grants_production_authority"] is False
    assert exit_code(report) == 0


def test_any_entitlement_failure_stops_before_broad_run():
    symbol = next(iter(SMOKE_SAMPLE))
    report = build_smoke_report(_Adapter({
        (symbol, "financial_statements"): _unavailable("ENTITLEMENT_UNAVAILABLE", "HTTP_403")
    }))
    assert report["state"] == ENTITLEMENT_SMOKE_FAIL
    assert report["failure_classification"] == CREDENTIAL_ENTITLEMENT_UNAVAILABLE
    assert exit_code(report) == 2


def test_provider_absence_and_contract_ambiguity_are_not_mislabeled_as_entitlement():
    symbol = next(iter(SMOKE_SAMPLE))
    absent = build_smoke_report(_Adapter({
        (symbol, "financial_statements"): _unavailable("DATA_UNAVAILABLE", "NO_COMPANY_DATA")
    }))
    assert absent["state"] == PROVIDER_DATA_UNAVAILABLE
    assert absent["failure_classification"] == PROVIDER_DATA_UNAVAILABLE
    assert exit_code(absent) == 3

    incomplete = _available("basic_financials", symbol)
    incomplete["payload"].pop("market_capitalization_lineage")
    unresolved = build_smoke_report(_Adapter({(symbol, "basic_financials"): incomplete}))
    assert unresolved["state"] == PROVIDER_CONTRACT_UNRESOLVED
    assert unresolved["failure_classification"] == PROVIDER_CONTRACT_UNRESOLVED
    assert exit_code(unresolved) == 4


def test_adapter_exception_is_atlas_integration_failure():
    report = build_smoke_report(_Adapter(raises=True))
    assert report["state"] == ATLAS_INTEGRATION_FAILURE
    assert report["failure_classification"] == ATLAS_INTEGRATION_FAILURE
    assert exit_code(report) == 5


def test_workflow_runs_smoke_before_broad_and_keeps_both_dispatch_only():
    workflow = Path(".github/workflows/atlas_finnhub_provider_certification.yml").read_text()
    smoke = "Run full-Core entitlement smoke"
    broad = "Run bounded real-data P/FCF peer certification"
    dispatch_condition = "github.event_name == 'workflow_dispatch' && inputs.run_broad_p_fcf"
    assert workflow.index(smoke) < workflow.index(broad)
    assert workflow.count(dispatch_condition) == 2
