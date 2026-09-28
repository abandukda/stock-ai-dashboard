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
    FULL_CORE_RERUN_CONTRACT, P_FCF_ROUTE_CERTIFICATION_FAILURE,
    P_FCF_ROUTE_CERTIFIED, P_FCF_ROUTE_UNAVAILABLE_INSUFFICIENT_COMPARABLE_PEERS,
    PROVIDER_DATA_UNAVAILABLE, PROVIDER_INPUTS_CERTIFIED,
    TARGETS, acquire_universe, classify_provider_record, derive_candidate_symbols,
    acquire_adaptive_peer_coverage, classify_target_route,
    _p_fcf_output_signature, load_governed_classifications, main,
)
from tests.test_professional_valuation_evidence import row


def test_acquisition_serializes_one_issuer_integration_failure_and_continues(monkeypatch):
    import scripts.finnhub_p_fcf_peer_certification as module

    def fake_acquire(_adapter, symbol, _classification, _pace):
        if symbol == "BAD":
            raise ValueError("provider sentinel")
        return {"ticker": symbol}, {"ticker": symbol, "unresolved_fields": []}

    monkeypatch.setattr(module, "acquire_row", fake_acquire)
    rows, diagnostics = acquire_universe(
        object(), ("GOOD", "BAD"),
        {symbol: {"sector": "Technology", "industry": "Software"} for symbol in ("GOOD", "BAD")},
        0.0,
    )
    assert rows == [{"ticker": "GOOD"}]
    assert diagnostics["BAD"]["unresolved_fields"] == ["atlas_integration_failure"]
    assert diagnostics["BAD"]["atlas_integration_failure"] == {"exception_type": "ValueError"}


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


def test_adaptive_acquisition_uses_governed_order_and_stops_at_peer_minimum(monkeypatch):
    import scripts.finnhub_p_fcf_peer_certification as module
    catalog = {
        "TGT": {"ticker": "TGT", "sector": "Technology", "industry": "Software", "reference_market_cap": 100},
        "I1": {"ticker": "I1", "sector": "Technology", "industry": "Software", "reference_market_cap": 90},
        "I2": {"ticker": "I2", "sector": "Technology", "industry": "Software", "reference_market_cap": 80},
        "S1": {"ticker": "S1", "sector": "Technology", "industry": "Hardware", "reference_market_cap": 110},
        "S2": {"ticker": "S2", "sector": "Technology", "industry": "Hardware", "reference_market_cap": 120},
    }
    counts = iter((1, 3))
    monkeypatch.setattr(module, "_peer_count_for_target", lambda *_args: next(counts))

    def fake_acquire(_adapter, symbols, _catalog, _pace):
        return ([{"ticker": symbol} for symbol in symbols],
                {symbol: {"ticker": symbol, "unresolved_fields": []} for symbol in symbols})

    monkeypatch.setattr(module, "acquire_universe", fake_acquire)
    rows, acquisition, diagnostics = acquire_adaptive_peer_coverage(
        object(), rows=[{"ticker": "TGT"}], acquisition={"TGT": {}}, catalog=catalog,
        targets=("TGT",), pace_seconds=0, batch_size=2, max_additional_symbols_per_target=4,
    )
    assert diagnostics["physical_provider_calls"] == ["I1", "I2"]
    assert diagnostics["targets"]["TGT"]["stopped_on_minimum_peer_coverage"] is True
    assert set(acquisition) == {"TGT", "I1", "I2"}
    assert {item["ticker"] for item in rows} == {"TGT", "I1", "I2"}


def test_target_local_adaptive_scopes_do_not_cross_contaminate_and_reuse_cache(monkeypatch):
    import scripts.finnhub_p_fcf_peer_certification as module
    catalog = {
        "A": {"ticker": "A", "sector": "Technology", "industry": "Alpha", "reference_market_cap": 100},
        "B": {"ticker": "B", "sector": "Technology", "industry": "Beta", "reference_market_cap": 100},
        "SHARED": {"ticker": "SHARED", "sector": "Technology", "industry": "Gamma", "reference_market_cap": 100},
    }
    scope_counts = {"A": iter((0, 3)), "B": iter((0, 3))}
    monkeypatch.setattr(module, "_peer_count_for_target", lambda _rows, target: next(scope_counts[target]))
    calls = []

    def fake_acquire(_adapter, symbols, _catalog, _pace):
        calls.extend(symbols)
        return ([{"ticker": symbol} for symbol in symbols],
                {symbol: {"ticker": symbol, "unresolved_fields": []} for symbol in symbols})

    monkeypatch.setattr(module, "acquire_universe", fake_acquire)
    _rows, _acquisition, diagnostics = acquire_adaptive_peer_coverage(
        object(), rows=[{"ticker": "A"}, {"ticker": "B"}],
        acquisition={"A": {}, "B": {}}, catalog=catalog, targets=("A", "B"),
        pace_seconds=0, batch_size=1, max_additional_symbols_per_target=3,
    )
    assert calls == ["SHARED"]
    assert diagnostics["targets"]["A"]["logical_evidence_scope_symbols"] == ["A", "B", "SHARED"]
    assert diagnostics["targets"]["B"]["logical_evidence_scope_symbols"] == ["A", "B", "SHARED"]
    assert diagnostics["targets"]["B"]["candidates_tested"][0]["provider_response_reused_from_cache"] is True


def test_adaptive_candidate_for_one_target_does_not_enter_another_target_scope(monkeypatch):
    import scripts.finnhub_p_fcf_peer_certification as module
    catalog = {
        "A": {"ticker": "A", "sector": "Technology", "industry": "Alpha", "reference_market_cap": 100},
        "B": {"ticker": "B", "sector": "Technology", "industry": "Beta", "reference_market_cap": 100},
        "B_ONLY": {"ticker": "B_ONLY", "sector": "Technology", "industry": "Beta", "reference_market_cap": 90},
    }
    scope_counts = {"A": iter((3,)), "B": iter((0, 3))}
    monkeypatch.setattr(module, "_peer_count_for_target", lambda _rows, target: next(scope_counts[target]))

    def fake_acquire(_adapter, symbols, _catalog, _pace):
        return ([{"ticker": symbol} for symbol in symbols],
                {symbol: {"ticker": symbol, "unresolved_fields": []} for symbol in symbols})

    monkeypatch.setattr(module, "acquire_universe", fake_acquire)
    _rows, _acquisition, diagnostics = acquire_adaptive_peer_coverage(
        object(), rows=[{"ticker": "A"}, {"ticker": "B"}],
        acquisition={"A": {}, "B": {}}, catalog=catalog, targets=("A", "B"),
        pace_seconds=0, batch_size=1, max_additional_symbols_per_target=3,
    )
    assert "B_ONLY" not in diagnostics["targets"]["A"]["logical_evidence_scope_symbols"]
    assert "B_ONLY" in diagnostics["targets"]["B"]["logical_evidence_scope_symbols"]


def test_provider_input_and_route_status_are_separate_for_exhausted_peer_universe():
    result = classify_target_route(
        target_row_present=True, certified_peer_count=1,
        route_certified=False, candidate_universe_exhausted=True,
    )
    assert result == {
        "provider_input_status": PROVIDER_INPUTS_CERTIFIED,
        "p_fcf_route_status": P_FCF_ROUTE_UNAVAILABLE_INSUFFICIENT_COMPARABLE_PEERS,
    }
    assert classify_target_route(
        target_row_present=True, certified_peer_count=3,
        route_certified=True, candidate_universe_exhausted=False,
    )["p_fcf_route_status"] == P_FCF_ROUTE_CERTIFIED
    assert classify_target_route(
        target_row_present=True, certified_peer_count=2,
        route_certified=False, candidate_universe_exhausted=False,
    )["p_fcf_route_status"] == P_FCF_ROUTE_CERTIFICATION_FAILURE


def test_sufficient_target_numerical_output_is_invariant_to_other_target_adaptive_rows():
    base = [row("F", industry="Auto", pe=10), row("P1", industry="Auto", pe=20),
            row("P2", industry="Auto", pe=30), row("P3", industry="Auto", pe=40)]
    baseline = _p_fcf_output_signature(base, "F")
    # An unrelated target may fetch another otherwise-comparable issuer, but it
    # is not in F's logical evidence scope and cannot change F's result.
    physical_cache = [*base, row("OTHER_TARGET_EXTRA", industry="Auto", pe=5)]
    isolated = _p_fcf_output_signature(
        [item for item in physical_cache if item["ticker"] != "OTHER_TARGET_EXTRA"], "F"
    )
    contaminated = _p_fcf_output_signature(physical_cache, "F")
    assert isolated == baseline
    assert contaminated != baseline


def test_target_local_queue_exhausts_without_consuming_another_targets_budget(monkeypatch):
    import scripts.finnhub_p_fcf_peer_certification as module
    catalog = {
        "A": {"ticker": "A", "sector": "Tech", "industry": "A", "reference_market_cap": 100},
        "B": {"ticker": "B", "sector": "Retail", "industry": "B", "reference_market_cap": 100},
        "B1": {"ticker": "B1", "sector": "Retail", "industry": "B", "reference_market_cap": 90},
        "B2": {"ticker": "B2", "sector": "Retail", "industry": "B", "reference_market_cap": 80},
    }
    monkeypatch.setattr(module, "_peer_count_for_target", lambda _rows, target: 3 if target == "A" else 2)
    monkeypatch.setattr(module, "acquire_universe", lambda _adapter, symbols, _catalog, _pace: (
        [{"ticker": symbol} for symbol in symbols],
        {symbol: {"ticker": symbol, "unresolved_fields": []} for symbol in symbols},
    ))
    _rows, _acquisition, diagnostics = acquire_adaptive_peer_coverage(
        object(), rows=[{"ticker": "A"}, {"ticker": "B"}], acquisition={"A": {}, "B": {}},
        catalog=catalog, targets=("A", "B"), pace_seconds=0, batch_size=1,
        max_additional_symbols_per_target=10,
    )
    b = diagnostics["targets"]["B"]
    assert [item["ticker"] for item in b["candidates_tested"]] == ["B1", "B2"]
    assert b["governed_candidate_universe_exhausted"] is True
    assert b["stopped_on_target_provider_call_bound"] is False


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
