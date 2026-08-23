from __future__ import annotations

import json

import agents.runtime_qa_architecture as qa


def _family(status="DATA_UNAVAILABLE", provider=None, cache="TEMPORARILY_UNAVAILABLE"):
    return {"semantic_status": status, "provider": provider, "cache_status": cache, "evidence_ids": []}


def _context(ticker="NVDA"):
    return {
        "version": "RESEARCH_CONTEXT_V1", "ticker": ticker, "security_type": "EQUITY",
        "production_decision": {"semantic_status": "AVAILABLE", "recommendation": "WATCH"},
        "evidence_families": {name: _family() for name in qa.EVIDENCE_FAMILIES},
        "evidence_registry": {}, "limitations": [],
    }


def test_architecture_preflight_and_drift_fail_closed(monkeypatch):
    assert qa.architecture_preflight()["status"] == "PASS"
    monkeypatch.setattr(qa, "RESEARCH_CONTEXT_VERSION", "UNEXPECTED")
    assert qa.architecture_preflight()["status"] == "ARCHITECTURE_DRIFT"


def test_missing_provider_registry_version_fails_closed(monkeypatch):
    monkeypatch.setattr(qa, "PROVIDER_OWNERSHIP_VERSION", "")
    result = qa.architecture_preflight()
    assert result["status"] == "ARCHITECTURE_DRIFT"
    assert "PROVIDER_REGISTRY_VERSION_DRIFT" in result["failures"]


def test_yahoo_registry_count_drift_fails_closed(monkeypatch):
    monkeypatch.setattr(qa, "YAHOO_DEPENDENCIES", qa.YAHOO_DEPENDENCIES[:-1])
    assert "YAHOO_DEPENDENCY_COUNT_DRIFT" in qa.architecture_preflight()["failures"]


def test_production_decision_mutation_is_p0():
    result = qa.certify_immutable_decision({"recommendation": "WATCH"}, {"recommendation": "BUY NOW"})
    assert result["classification"] == "PRODUCT_DEFECT" and result["severity"] == "P0"


def test_displayed_without_evidence_and_stale_labeled_live_fail():
    absent = qa.reconcile_family(_family(), {"displayed": "true"})
    assert absent["result"] == "DISPLAYED_WITHOUT_CANONICAL_EVIDENCE"
    stale = qa.reconcile_family(_family("AVAILABLE", "FMP", "STALE_FALLBACK"), {"displayed": "true", "freshness": "LIVE"})
    assert stale["result"] == "STALE_OR_FRESHNESS_MISMATCH"


def test_wrong_ask_ticker_is_p0():
    result = qa.certify_ask_context({"ticker": "NVDA"}, {"ticker": "AAPL"})
    assert result["classification"] == "PRODUCT_DEFECT" and result["severity"] == "P0"


def test_sanitized_context_contains_metadata_not_canonical_values_or_secrets():
    context = _context()
    context["evidence_families"]["profile"] = {
        **_family("AVAILABLE", "FMP", "FETCHED"), "data": {"market_cap": 123, "api_key": "secret"},
    }
    encoded = json.dumps(qa.sanitize_research_context(context))
    assert "market_cap" not in encoded and "api_key" not in encoded and "secret" not in encoded
    assert "FMP" in encoded


def test_valuation_roles_and_sec_authority_fail_closed():
    decision = {"atlas_fair_value": None, "analyst_consensus": 200}
    rendered = {"atlas_fair_value": {"displayed": "true", "source_family": "wall_street"}}
    assert qa.certify_valuation_separation(decision, rendered)["severity"] == "P0"
    assert qa.certify_sec_authority({"semantic_status": "AVAILABLE", "provider": "FMP"}, {"displayed": "true"})["severity"] == "P0"


def test_missing_ticker_etf_and_ticker_matrix_contracts():
    missing = {"production_decision": {"semantic_status": "DATA_UNAVAILABLE"}}
    assert qa.certify_missing_production_ticker(missing)["classification"] == "PASS_WITH_EVIDENCE_LIMITATIONS"
    etf = _context("SPY")
    etf["security_type"] = "ETF"
    for family in qa.CORPORATE_ONLY_FAMILIES:
        etf["evidence_families"][family]["semantic_status"] = "NOT_APPLICABLE"
    assert qa.certify_etf_context(etf)["classification"] == "PASS_WITH_EVIDENCE_LIMITATIONS"
    matrix = qa.research_ticker_matrix()
    assert {"NVDA", "AAPL", "SPY", "INVALID123"}.issubset(matrix["tickers"])
