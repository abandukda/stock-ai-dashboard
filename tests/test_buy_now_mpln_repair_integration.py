from engines.component_builder import build_components
from services.professional_valuation_evidence import apply_peer_multiple_evidence
from services.twelve_data_trial_intelligence import normalize_trial_dossier
from services.valuation_evidence_strength import certify_peer_multiple


def _peer(ticker, security_type, market_cap, multiple=10):
    return {
        "ticker": ticker, "company": ticker, "industry": "Capital Markets",
        "sector": "Financial Services", "security_type": security_type,
        "market_cap": market_cap, "total_debt": 100, "cash_and_equivalents": 50,
        "forward_eps": 5, "provider_forward_pe": multiple,
        "forward_ebitda": 100, "provider_ev_ebitda": multiple,
        "professional_evidence_as_of": "2026-09-10T20:29:10Z",
        "professional_evidence_lineage": {
            "evidence_ids": [f"TD-{ticker}"],
            "fields": {"forward_ebitda": {"period_type": "TTM"}},
        },
    }


def test_buy_now_evidence_repairs_and_mpln_margin_authority_coexist():
    dossier = {"families": {
        "statistics": {"observed_at": "2026-09-10T20:29:10Z", "evidence_id": "TD-STATS", "payload": {
            "statistics": {"financials": {"operating_margin": -1.5520134877243657,
                "income_statement": {"revenue_ttm": 930_624_000}}}}},
        "income_statement": {"observed_at": "2026-09-10T20:29:10Z", "evidence_id": "TD-INCOME", "payload": {
            "income_statement": [{"fiscal_date": "2024-12-31", "period": "annual", "currency": "USD",
                                  "sales": 932_000_000, "operating_income": 98_931_000,
                                  "ebit": -1_444_341_000}]}}
    }}
    mpln = normalize_trial_dossier({"ticker": "MPLN"}, dossier)
    assert mpln["operating_profit_margin"] == 98_931_000 / 932_000_000
    assert mpln["operating_margin_lineage"]["numerator_period"] == mpln["operating_margin_lineage"]["denominator_period"]
    assert mpln["operating_margin_lineage"]["scale"] == "RATIO_DECIMAL"

    fundamentals = build_components({
        "Ticker": "NVDA", "Revenue Growth": 10,
        "professional_evidence_as_of": "2026-09-10T20:29:10Z",
    })["fundamentals"]
    assert fundamentals["as_of"] == "2026-09-10T20:29:10Z"

    subject = _peer("MKTX", "Common Stock", 10_000)
    peers = [
        _peer("ADR1", "ADR", 9_000, 8),
        _peer("ADS1", "ADS", 11_000, 10),
        _peer("COMMON", "Common Equity", 12_000, 12),
        _peer("TINY", "Common Stock", 100, 14),
    ]
    enriched = apply_peer_multiple_evidence([subject, *peers])[0]
    evidence = enriched["justified_forward_pe_peer_evidence"]
    assert set(evidence["final_peer_set"]) == {"ADR1", "ADS1", "COMMON"}
    assert any(item["peer_ticker"] == "TINY" and item["exclusion_reason"] == "SCALE_GAP_OVER_10X"
               for item in evidence["excluded_peers"])

    ev_model = {
        "methodology_id": "VAL_EV_EBITDA_V1",
        "key_assumptions": {"multiple": 10, "peer_evidence": evidence},
    }
    for peer in ev_model["key_assumptions"]["peer_evidence"]["included_peers"]:
        peer["peer_enterprise_value"] = peer["multiple"] * 100
        peer["peer_ebitda"] = 100
        peer["peer_ev_ebitda"] = peer["multiple"]
        peer["peer_ebitda_basis"] = "TTM"
        peer["peer_ev_ebitda_basis"] = "TTM"
    certification = certify_peer_multiple(ev_model)
    assert "SECURITY_TYPE_MISMATCH" not in certification["comparability_flags"]
    assert "PEER_EV_EBITDA_RECONCILIATION_FAILED" not in certification["reason_codes"]
