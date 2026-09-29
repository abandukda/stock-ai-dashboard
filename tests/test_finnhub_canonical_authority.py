from services.completed_session_volume_authority import certify_completed_session_volume
from services.finnhub_canonical_authority import (
    AUTHORITY_MATRIX, AUTHORITY_VERSION, FinnhubCanonicalAdapter, authority_contract,
)
from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, UsePermission, require_certified_calculation,
)


class Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _get(_url, *, params, timeout):
    if "profile2" in _url:
        return Response({"name": "Apple", "exchange": "NASDAQ", "finnhubIndustry": "Technology", "country": "US", "currency": "USD", "shareOutstanding": 100})
    if "financials-reported" in _url:
        return Response({"data": []})
    if "metric" in _url:
        return Response({"metric": {"marketCapitalization": 1000, "shareOutstanding": 100}})
    if "candle" in _url:
        return Response({"s": "ok", "t": [1], "o": [1], "h": [2], "l": [1], "c": [2], "v": [10]})
    if "eps-estimate" in _url:
        return Response({"freq": "annual", "data": [{"period": "2027-12-31", "epsAvg": 3.0}]})
    return Response({}, 404)


def test_authority_is_capability_scoped_not_global():
    assert authority_contract("financial_statements")["state"] == "CANONICAL_CERTIFIED"
    assert authority_contract("eps_estimates")["state"] == "CONTRACT_PENDING"
    assert authority_contract("bulk")["state"] == "NOT_CERTIFIED"
    assert authority_contract("unknown")["state"] == "NOT_AUTHORIZED"


def test_authorized_paid_core_record_is_promoted_to_certified_calculation():
    adapter = FinnhubCanonicalAdapter(api_key="secret", get=_get)
    record = adapter.fetch("basic_financials", "AAPL")
    assert record.provenance.provider == "FINNHUB"
    assert record.provenance.dataset_family == DatasetFamily.CANONICAL_QUANTITATIVE
    assert record.provenance.certification_status == CertificationStatus.CERTIFIED
    assert record.provenance.derived_use_permission == UsePermission.CERTIFIED_CALCULATION
    assert record.provenance.display_permission == UsePermission.PROHIBITED
    assert AUTHORITY_VERSION in record.provenance.adapter_version
    assert require_certified_calculation(record)["market_capitalization"] == 1_000_000_000


def test_forward_estimate_contract_remains_shadow_and_cannot_score():
    record = FinnhubCanonicalAdapter(api_key="secret", get=_get).fetch("eps_estimates", "AAPL")
    assert record.provenance.certification_status == CertificationStatus.UNVERIFIED_SHADOW
    assert record.provenance.derived_use_permission == UsePermission.SHADOW_ONLY
    assert "AUTHORITY_STATE:CONTRACT_PENDING" in record.limitations


def test_provider_failure_is_never_upgraded_by_authority_wrapper():
    def denied(*_args, **_kwargs):
        return Response({}, 403)
    record = FinnhubCanonicalAdapter(api_key="secret", get=denied).fetch("financial_statements", "AAPL")
    assert record.provenance.certification_status == CertificationStatus.ENTITLEMENT_UNAVAILABLE
    assert record.provenance.derived_use_permission == UsePermission.SHADOW_ONLY


def test_completed_session_volume_authority_is_provider_neutral_and_strict():
    evidence = {
        "completed_daily_evidence": True, "valid_daily_volume_baseline": True,
        "volume_session_scope": "COMPLETED_SESSION", "volume_semantics": "CONSOLIDATED_AFTER_4PM",
        "provider_authority": "CANONICAL_CERTIFIED", "volume_evidence_id": "FINNHUB:BAR:1",
        "as_of": "2026-09-28T20:00:00+00:00",
    }
    assert certify_completed_session_volume(evidence)["authorized"] is True
    assert certify_completed_session_volume({**evidence, "volume_session_scope": "INTRADAY"}) == {
        "version": "ATLAS_COMPLETED_SESSION_VOLUME_AUTHORITY_V1", "status": "REJECTED",
        "authorized": False, "blockers": ("SESSION_SCOPE_NOT_COMPLETED",),
    }


def test_matrix_contains_no_blanket_finnhub_authority():
    assert set(AUTHORITY_MATRIX) >= {"company_profile", "financial_statements", "basic_financials", "historical_ohlcv", "eps_estimates", "bulk"}
    assert all("global" not in key.lower() for key in AUTHORITY_MATRIX)
