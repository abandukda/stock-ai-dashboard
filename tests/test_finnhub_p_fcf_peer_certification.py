from pathlib import Path
import json
import sys

from services.finnhub_shadow_provider import (
    FINNHUB_DEMO_SYMBOL_WHITELIST, FINNHUB_PAID_CORE_CERTIFICATION_LICENSE,
    FinnhubShadowAdapter,
)

from scripts.finnhub_p_fcf_peer_certification import (
    ATLAS_INTEGRATION_FAILURE, CERTIFIED_DATA_AVAILABLE,
    CREDENTIAL_ENTITLEMENT_UNAVAILABLE, EXPECTED_DEMO_SYMBOL_RESTRICTION,
    FULL_CORE_RERUN_CONTRACT, PROVIDER_DATA_UNAVAILABLE,
    TARGETS, classify_provider_record, derive_candidate_symbols, load_governed_classifications, main,
)


def test_candidate_universe_is_derived_from_governed_classification_not_hard_coded(tmp_path: Path):
    rows = [
        {"ticker": "AAPL", "sector": "Technology", "industry": "Hardware", "market_cap": 100},
        {"ticker": "P1", "sector": "Technology", "industry": "Hardware", "market_cap": 80},
        {"ticker": "P2", "sector": "Technology", "industry": "Hardware", "market_cap": 120},
        {"ticker": "P3", "sector": "Technology", "industry": "Hardware", "market_cap": 150},
        {"ticker": "S1", "sector": "Technology", "industry": "Software", "market_cap": 90},
    ]
    primary = tmp_path / "classification.json"; primary.write_text(json.dumps(rows))
    supplemental = tmp_path / "supplemental.json"; supplemental.write_text(json.dumps({"universe": []}))
    catalog, provenance = load_governed_classifications(primary, supplemental)
    symbols, diagnostics = derive_candidate_symbols(catalog, ("AAPL",))
    assert symbols == ["AAPL", "P1", "P2", "P3", "S1"]
    assert diagnostics["AAPL"]["industry_candidates_available"] == 3
    assert provenance["primary_sha256"]


def test_required_targets_are_fixed_but_peer_lists_are_not_embedded_per_target():
    assert TARGETS == ("AAPL", "MSFT", "NVDA", "WMT", "IBM", "F", "PFE", "TSLA")
    import inspect
    import scripts.finnhub_p_fcf_peer_certification as module
    source = inspect.getsource(module.derive_candidate_symbols)
    assert "AAPL" not in source and "MSFT" not in source
    assert "minimum_peer_count" not in source


def test_supplemental_gics_consumer_staples_joins_governed_consumer_defensive_taxonomy(tmp_path: Path):
    primary = tmp_path / "classification.json"; primary.write_text(json.dumps([
        {"ticker": "COST", "sector": "Consumer Defensive", "industry": "Discount Stores", "market_cap": 400},
    ]))
    supplemental = tmp_path / "supplemental.json"; supplemental.write_text(json.dumps({"assets": [
        {"ticker": "WMT", "type": "STOCK", "sector": "Consumer Staples"},
    ]}))
    catalog, _ = load_governed_classifications(primary, supplemental)
    assert catalog["WMT"]["sector"] == "Consumer Defensive"
    assert catalog["WMT"]["source_sector"] == "Consumer Staples"
    assert catalog["WMT"]["sector_normalization"] == "ATLAS_GOVERNED_SECTOR_TAXONOMY_EQUIVALENCE_V1"


def test_entitlement_is_not_misclassified_as_provider_data_absence():
    entitlement = {"provenance": {"certification_status": "ENTITLEMENT_UNAVAILABLE"},
                   "payload": {"reason": "HTTP_403"}}
    missing = {"provenance": {"certification_status": "DATA_UNAVAILABLE"},
               "payload": {"reason": "NO_COMPANY_DATA"}}
    available = {"provenance": {"certification_status": "UNVERIFIED_SHADOW"}, "payload": {}}
    assert classify_provider_record(entitlement) == CREDENTIAL_ENTITLEMENT_UNAVAILABLE
    assert classify_provider_record(missing) == PROVIDER_DATA_UNAVAILABLE
    assert classify_provider_record(available) == CERTIFIED_DATA_AVAILABLE
    assert ATLAS_INTEGRATION_FAILURE not in {
        classify_provider_record(entitlement), classify_provider_record(missing), classify_provider_record(available)
    }


def test_outside_whitelist_demo_403_is_expected_restriction_not_core_failure():
    assert FINNHUB_DEMO_SYMBOL_WHITELIST == {
        "AAPL", "TSLA", "WMT", "IBM", "F", "NVDA", "MSFT", "PFE", "SPY", "IVV", "AVUV",
    }
    demo_restriction = {
        "provenance": {
            "certification_status": "ENTITLEMENT_UNAVAILABLE",
            "license_class": "DEMO_MIGRATION_VALIDATION_ONLY",
            "symbol": "ORCL",
        },
        "payload": {"reason": "HTTP_403"},
    }
    demo_whitelist_failure = {
        "provenance": {
            "certification_status": "ENTITLEMENT_UNAVAILABLE",
            "license_class": "DEMO_MIGRATION_VALIDATION_ONLY",
            "symbol": "AAPL",
        },
        "payload": {"reason": "HTTP_403"},
    }
    paid_core_failure = {
        "provenance": {
            "certification_status": "ENTITLEMENT_UNAVAILABLE",
            "license_class": "PAID_CORE_CERTIFICATION",
            "symbol": "ORCL",
        },
        "payload": {"reason": "HTTP_403"},
    }
    assert classify_provider_record(demo_restriction) == EXPECTED_DEMO_SYMBOL_RESTRICTION
    assert classify_provider_record(demo_whitelist_failure) == CREDENTIAL_ENTITLEMENT_UNAVAILABLE
    assert classify_provider_record(paid_core_failure) == CREDENTIAL_ENTITLEMENT_UNAVAILABLE


def test_adapter_preserves_explicit_paid_core_certification_license_on_unavailable_record():
    class Response:
        status_code = 403
        @staticmethod
        def json(): return {}
    adapter = FinnhubShadowAdapter(
        api_key="not-a-real-key", license_class=FINNHUB_PAID_CORE_CERTIFICATION_LICENSE,
        get=lambda *args, **kwargs: Response(),
    )
    record = adapter.fetch("company_profile", "ORCL").as_dict()
    assert record["provenance"]["license_class"] == FINNHUB_PAID_CORE_CERTIFICATION_LICENSE
    assert classify_provider_record(record) == CREDENTIAL_ENTITLEMENT_UNAVAILABLE


def test_full_core_rerun_contract_preserves_existing_p_fcf_certification_rules():
    assert FULL_CORE_RERUN_CONTRACT["required_families"] == (
        "company_profile", "financial_statements", "basic_financials"
    )
    assert FULL_CORE_RERUN_CONTRACT["credential_entitlement_failures_required"] == 0
    assert FULL_CORE_RERUN_CONTRACT["minimum_certified_peers_per_target"] == 3
    assert FULL_CORE_RERUN_CONTRACT["all_targets_must_publish_p_fcf"] is True
    assert FULL_CORE_RERUN_CONTRACT["forward_estimate_contract_required_for_p_fcf"] is False


def test_demo_license_blocks_broad_acquisition_before_provider_calls(monkeypatch, tmp_path: Path):
    output = tmp_path / "report.json"
    monkeypatch.delenv("ATLAS_FINNHUB_LICENSE_CLASS", raising=False)
    monkeypatch.setattr(sys, "argv", ["certify", "--output", str(output), "--pace-seconds", "0"])
    assert main() == 6
    report = json.loads(output.read_text())
    assert report["broad_acquisition_executed"] is False
    assert report["launch_readiness"]["finnhub_core_state"] == "PAID_CORE_BREADTH_UNTESTED"
