import json

from engines.ask_atlas_engine import ask_atlas
from services.customer.provider_neutral import (
    contains_customer_provider_branding,
    provider_neutral_customer_projection,
)


FORBIDDEN = ("TWELVE_DATA", "Twelve Data", "twelve_data")


def _assert_neutral(value):
    rendered = json.dumps(value, default=str)
    assert all(token not in rendered for token in FORBIDDEN)


def test_customer_projection_removes_provider_branding_without_mutating_provenance():
    canonical = {
        "provider": "TWELVE_DATA",
        "quote_source": "Twelve Data WebSocket",
        "source_type": "TWELVE_DATA_LATEST_COMPLETED_BAR",
        "action": "BUY_NOW",
        "fair_value": 125.5,
        "decision_confidence": 88.4,
        "potential": 27.1,
        "evidence_id": "TD1-immutable-evidence-id",
        "evidence_status": "DATA_UNAVAILABLE",
        "nested": {"attribution": "Source: Twelve Data", "value": 42, "complete": False},
    }
    projected = provider_neutral_customer_projection(canonical)
    _assert_neutral(projected)
    assert projected["source_type"] == "VERIFIED_ATLAS_MARKET_DATA"
    assert projected["nested"] == {"value": 42, "complete": False}
    assert projected["action"] == "BUY_NOW"
    assert projected["fair_value"] == 125.5
    assert projected["decision_confidence"] == 88.4
    assert projected["potential"] == 27.1
    assert projected["evidence_id"] == "TD1-immutable-evidence-id"
    assert projected["evidence_status"] == "DATA_UNAVAILABLE"
    assert canonical["provider"] == "TWELVE_DATA"
    assert canonical["nested"]["attribution"] == "Source: Twelve Data"


def test_customer_surface_contracts_are_provider_neutral():
    fixture = {
        "home": {"market_evidence": {"provider": "TWELVE_DATA"}},
        "research": {"history_provenance": {"source": "Twelve Data /time_series"}},
        "full_investment_case": {"source_attribution": "Source: Twelve Data"},
        "full_ranked": {"source_type": "TWELVE_DATA_LATEST_COMPLETED_BAR"},
        "earnings": {"provider": "TWELVE_DATA"},
        "recovery": {"message": "Twelve Data unavailable"},
        "customer_summary": "Certified using Twelve Data",
        "customer_projection": {"transport_provider": "TWELVE_DATA"},
        "twelve_data_internal_overlay": {"value": 1},
        "mobile": {"tooltip": "Twelve Data price"},
    }
    projected = provider_neutral_customer_projection(fixture)
    _assert_neutral(projected)
    assert set(projected) == set(fixture) - {"twelve_data_internal_overlay"}


def test_ask_atlas_never_receives_or_returns_provider_branding():
    report = {
        "ticker": "TEST",
        "company": "Test Company",
        "committee_verdict": "WAIT FOR CONFIRMATION",
        "executive_summary": "Evidence remains incomplete.",
        "history_provenance": {"source": "Twelve Data /time_series"},
        "wall_street_analysis": {"provider": "TWELVE_DATA", "attribution": "Source: Twelve Data"},
    }
    result = ask_atlas("Explain this simply", report)
    _assert_neutral(result)


def test_brand_detector_is_case_and_enum_aware():
    assert contains_customer_provider_branding("TWELVE_DATA")
    assert contains_customer_provider_branding("Source: Twelve Data")
    assert contains_customer_provider_branding("twelve_data")
    assert not contains_customer_provider_branding("Verified market data")
