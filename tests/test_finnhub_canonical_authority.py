from services.completed_session_volume_authority import certify_completed_session_volume
from services.finnhub_canonical_authority import (
    AUTHORITY_MATRIX, AUTHORITY_VERSION, FinnhubCanonicalAdapter, authority_contract,
)
from services.provider_domain_contracts import (
    CertificationStatus, DatasetFamily, UsePermission, require_certified_calculation,
)


def _peer_row(ticker, market_cap, fcf):
    return {
        "ticker": ticker, "company": ticker, "sector": "Technology", "industry": "Software",
        "security_type": "COMMON_STOCK", "market_cap": market_cap,
        "normalized_fcf": fcf, "free_cash_flow": fcf, "diluted_shares": 10.0,
        "current_price": market_cap / 10.0, "professional_evidence_as_of": "2026-09-28T20:00:00+00:00",
        "professional_evidence_lineage": {"provider": "FINNHUB", "evidence_ids": [f"E:{ticker}"], "fields": {
            "market_cap": {"evidence_id": f"M:{ticker}", "unit": "USD", "currency": "USD", "as_of": "2026-09-28T20:00:00+00:00"},
            "normalized_fcf": {"evidence_id": f"F:{ticker}", "unit": "USD", "currency": "USD", "period": "2025-12-31"},
            "free_cash_flow": {"evidence_id": f"F:{ticker}", "unit": "USD", "currency": "USD", "period": "2025-12-31"},
        }},
    }


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


def test_target_local_peer_support_is_order_invariant_and_does_not_evaluate_support(monkeypatch):
    import scripts.finnhub_canonical_proving_set as proving

    rows = {symbol: _peer_row(symbol, cap, fcf) for symbol, cap, fcf in (
        ("AAA", 200.0, 20.0), ("P1", 100.0, 10.0),
        ("P2", 120.0, 10.0), ("P3", 140.0, 10.0),
    )}
    catalog = {symbol: {
        "ticker": symbol, "sector": "Technology", "industry": "Software",
        "security_type": "COMMON_STOCK", "reference_market_cap": row["market_cap"],
    } for symbol, row in rows.items()}
    monkeypatch.setattr(proving, "SYMBOLS", ("AAA",))
    monkeypatch.setattr(proving, "acquire_row", lambda _adapter, symbol, _classification, _pace: (rows[symbol], {"unresolved_fields": []}))
    prepared, evidence, calls = proving._target_local_peer_support(
        object(), targets={"AAA": rows["AAA"]}, catalog=catalog, pace_seconds=0,
    )
    result = evidence["targets"]["AAA"]
    assert result["p_fcf_route_status"] == "CERTIFIED"
    assert result["selected_peers"] == ["P3", "P2", "P1"]
    assert result["evaluation_order_invariance"] == "PASS"
    assert set(prepared) == {"AAA"}
    assert calls == 9
