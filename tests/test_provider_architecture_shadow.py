from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.finnhub_shadow_provider import ENDPOINT_BY_CAPABILITY, FinnhubShadowAdapter
from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, GovernedRecord, MarketCoverageClass,
    ProvenanceEnvelope, UsePermission, require_certified_calculation,
)
from services.provider_family_policy import assert_family_not_certified_input, bounded_customer_context
from services.provider_reconciliation import compare_scalar, reconcile_fields, reconcile_ohlcv


NOW = datetime(2026, 9, 20, tzinfo=timezone.utc).isoformat()


class Response:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _record(family, payload, *, provider="TEST", certified=False, coverage=MarketCoverageClass.UNKNOWN):
    return GovernedRecord(ProvenanceEnvelope(
        provider=provider, dataset_family=family, endpoint_or_source_family="TEST",
        symbol="AAPL", canonical_security_id="AAPL", capture_timestamp=NOW,
        raw_evidence_id=f"{provider}:1", adapter_version="TEST_V1",
        certification_status=CertificationStatus.CERTIFIED if certified else CertificationStatus.UNVERIFIED_SHADOW,
        display_permission=UsePermission.CONTEXT_ONLY,
        derived_use_permission=UsePermission.CERTIFIED_CALCULATION if certified else UsePermission.SHADOW_ONLY,
        market_coverage_class=coverage,
    ), payload)


@pytest.mark.parametrize("family", [
    DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE,
    DatasetFamily.OPTIONAL_QUALITATIVE_INTELLIGENCE,
    DatasetFamily.LIVE_DISPLAY_ONLY,
])
def test_non_scoring_families_cannot_feed_certified_calculations(family):
    record = _record(family, {"value": 99})
    with pytest.raises(PermissionError):
        require_certified_calculation(record)
    with pytest.raises(PermissionError):
        assert_family_not_certified_input(family)


def test_partial_realtime_is_rejected_even_if_misconfigured_as_certified():
    with pytest.raises(ValueError):
        _record(DatasetFamily.CANONICAL_QUANTITATIVE, {"volume": 10}, certified=True,
                coverage=MarketCoverageClass.PARTIAL_REALTIME)


def test_certified_full_consolidated_quantitative_record_is_reachable():
    record = _record(DatasetFamily.CANONICAL_QUANTITATIVE, {"close": 10}, certified=True,
                     coverage=MarketCoverageClass.FULL_CONSOLIDATED)
    assert require_certified_calculation(record)["close"] == 10


def test_finnhub_demo_normalizes_live_quote_as_partial_display_family():
    calls = []
    adapter = FinnhubShadowAdapter("demo", get=lambda url, **kwargs: calls.append((url, kwargs)) or Response({
        "c": 201.5, "o": 200, "h": 202, "l": 199, "pc": 198, "t": 1,
    }))
    record = adapter.fetch("live_quote", "aapl")
    assert calls[0][0].endswith("/quote")
    assert record.payload["price"] == 201.5
    assert record.provenance.dataset_family == DatasetFamily.LIVE_DISPLAY_ONLY
    assert record.provenance.market_coverage_class == MarketCoverageClass.PARTIAL_REALTIME
    assert record.provenance.display_permission == UsePermission.PROHIBITED
    with pytest.raises(PermissionError):
        require_certified_calculation(record)


def test_finnhub_historical_bars_are_shadow_not_automatically_certified():
    adapter = FinnhubShadowAdapter("demo", get=lambda *_a, **_k: Response({
        "s": "ok", "t": [1], "o": [10], "h": [11], "l": [9], "c": [10.5], "v": [1000],
    }))
    record = adapter.fetch("historical_ohlcv", "AAPL", **{"from": 1, "to": 2, "resolution": "D"})
    assert record.provenance.market_coverage_class == MarketCoverageClass.FULL_CONSOLIDATED
    assert record.provenance.certification_status == CertificationStatus.UNVERIFIED_SHADOW
    assert record.provenance.derived_use_permission == UsePermission.SHADOW_ONLY
    with pytest.raises(PermissionError):
        require_certified_calculation(record)


def test_finnhub_split_request_includes_documented_date_window():
    calls = []
    record = FinnhubShadowAdapter("demo", get=lambda url, **kwargs: calls.append((url, kwargs)) or Response([])).fetch("splits", "AAPL")
    assert calls[0][0].endswith("/stock/split")
    assert calls[0][1]["params"]["from"] < calls[0][1]["params"]["to"]
    assert record.payload == {"corporate_actions": []}
    assert record.provenance.certification_status == CertificationStatus.UNVERIFIED_SHADOW


def test_reported_financials_normalize_period_units_and_canonical_facts():
    payload = {"data": [{"endDate": "2025-09-27", "filedDate": "2025-10-31", "quarter": 0,
                         "form": "10-K", "accessNumber": "0001", "report": {"ic": [
                             {"concept": "us-gaap_Revenues", "unit": "usd", "value": 100},
                             {"concept": "us-gaap_OperatingIncomeLoss", "unit": "usd", "value": 25},
                         ]}}]}
    record = FinnhubShadowAdapter("demo", get=lambda *_a, **_k: Response(payload)).fetch("financial_statements", "AAPL")
    report = record.payload["reports"][0]
    assert report["fiscal_period"] == "FY"
    assert report["currency"] == "USD"
    assert report["canonical_facts"]["revenue"]["value"] == 100
    assert report["canonical_facts"]["ebit"]["source_record_version"] == "0001"


def test_successful_empty_payload_remains_available_empty_not_provider_failure():
    record = FinnhubShadowAdapter("demo", get=lambda *_a, **_k: Response([])).fetch("splits", "AAPL")
    assert record.provenance.certification_status == CertificationStatus.UNVERIFIED_SHADOW
    assert record.payload["corporate_actions"] == []


def test_finnhub_missing_and_entitlement_data_fail_closed_without_zero_substitution():
    missing = FinnhubShadowAdapter("").fetch("basic_financials", "AAPL")
    denied = FinnhubShadowAdapter("demo", get=lambda *_a, **_k: Response({}, 403)).fetch("financial_statements", "AAPL")
    assert missing.payload["status"] == "DATA_UNAVAILABLE"
    assert denied.payload["status"] == "ENTITLEMENT_UNAVAILABLE"
    assert "value" not in missing.payload and "value" not in denied.payload


def test_endpoint_families_keep_wall_street_news_and_ownership_non_scoring():
    for name in ("recommendations", "price_targets", "analyst_actions", "ownership", "insider_transactions", "company_news"):
        assert ENDPOINT_BY_CAPABILITY[name].family == DatasetFamily.CONTEXTUAL_EXTERNAL_EVIDENCE


def test_every_finnhub_capability_terminates_vendor_shape_inside_adapter():
    for capability in ENDPOINT_BY_CAPABILITY:
        payload = {"data": []}
        if capability == "live_quote": payload = {"c": 10, "o": 9, "h": 11, "l": 8, "pc": 9, "t": 1}
        elif capability == "historical_ohlcv": payload = {"s": "ok", "t": [1], "o": [9], "h": [11], "l": [8], "c": [10], "v": [100]}
        elif capability == "company_profile": payload = {"name": "Example", "exchange": "NASDAQ"}
        elif capability == "peers": payload = ["MSFT"]
        record = FinnhubShadowAdapter("demo", get=lambda *_a, _payload=payload, **_k: Response(_payload)).fetch(capability, "AAPL")
        assert record.provenance.certification_status == CertificationStatus.UNVERIFIED_SHADOW
        assert "data" not in record.payload, capability


def test_adapter_never_places_secret_in_record_or_diagnostics():
    secret = "do-not-leak"
    adapter = FinnhubShadowAdapter(secret, get=lambda *_a, **_k: Response({"name": "Apple"}))
    rendered = str(adapter.fetch("company_profile", "AAPL").as_dict())
    assert secret not in rendered


def test_demo_context_is_bounded_out_of_home_research_ask_and_export():
    record = FinnhubShadowAdapter("demo", get=lambda *_a, **_k: Response({
        "targetMean": 250, "rawVendorField": "must-not-leak",
    })).fetch("price_targets", "AAPL")
    expected = {"semantic_status": "DATA_UNAVAILABLE"}
    assert bounded_customer_context(record) == expected  # Home
    assert bounded_customer_context(record) == expected  # Research
    assert bounded_customer_context(record) == expected  # Ask ATLAS
    assert bounded_customer_context(record) == expected  # customer export


def test_methodology_modules_do_not_import_finnhub_adapter():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    methodology = (
        root / "engines" / "atlas_valuation.py",
        root / "engines" / "canonical_investment_evaluation_v1.py",
        root / "services" / "full_universe_decision_publication.py",
    )
    for path in methodology:
        source = path.read_text(encoding="utf-8")
        assert "finnhub_shadow_provider" not in source
        assert "finnhub.io" not in source


def test_reconciliation_is_observational_and_does_not_select_authority():
    current = _record(DatasetFamily.CANONICAL_QUANTITATIVE, {"revenue": 100}, provider="TWELVE_DATA")
    shadow = _record(DatasetFamily.CANONICAL_QUANTITATIVE, {"revenue": 101}, provider="FINNHUB")
    report = reconcile_fields(current, shadow, {"revenue": ("revenue", "revenue")})
    assert report["fields"]["revenue"]["status"] == "WITHIN_TOLERANCE"
    assert report["authority_changed"] is False
    assert compare_scalar(100, 120)["status"] == "MATERIAL_MISMATCH"


def test_ohlcv_reconciliation_reports_session_and_value_mismatches():
    report = reconcile_ohlcv(
        [{"date": "2026-09-18", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100}],
        [{"date": "2026-09-18", "open": 10, "high": 11, "low": 9, "close": 12, "volume": 100}],
    )
    assert report["common_sessions"] == 1
    assert report["material_mismatch_count"] == 1
    assert report["authority_changed"] is False
