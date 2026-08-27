"""ATLAS_CRITICAL_LOCAL_GATE: offline release gate for Research rendering.

Canonical command::

    python3 -m pytest -q tests/test_atlas_critical_local_gate.py

Targeted deployed QA must not be recommended after a Research or customer-
journey change until this local gate passes.
"""

from __future__ import annotations

import re
from copy import deepcopy

import pytest

from engines.ask_atlas_engine import ask_atlas
from engines.analyst_intelligence import build_analyst_intelligence
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.political_evidence import normalize_political_transaction
from engines.research_context import CORPORATE_ONLY_FAMILIES, build_research_context
from engines.research_engine import research_navigation_state
from engines.semantic_fields import (
    is_missing_scalar, number, safe_date_text, safe_mapping,
    safe_scalar_display, safe_sequence, semantic_identity,
)
from services.session_stability import consume_navigation_handoff, stabilize_authenticated_session
from ui.research_report_v2 import _analyst_intelligence_html


PAGES = ("Home", "Research Any Ticker", "Ask AI")
ATLAS_CRITICAL_LOCAL_GATE_COMMAND = (
    "python3 -m pytest -q tests/test_atlas_critical_local_gate.py"
)
STRUCTURAL_VALUES = (
    "normal", None, "", 0, -2.5, ["nested"], [], {"nested": "value"}, {},
    ("nested",), "not-a-date",
)


def equity(ticker: str = "NVDA") -> dict:
    return {
        "ticker": ticker,
        "company": f"{ticker} Example",
        "security_type": "EQUITY",
        "current_price": 100.0,
        "atlas_fair_value": 120.0,
        "opportunity_score": 80.0,
        "confidence_pct": 75.0,
        "analyst_actions": [
            {"firm": "Example Research", "action": "upgrade", "date": "2026-08-20"},
        ],
        "earnings_history": [
            {"fiscal_period": "Q2 2026", "report_date": "2026-08-01", "eps_actual": 0, "eps_estimate": -0.1},
        ],
        "analyst_estimates": [{"date": "2026-12-31", "eps_estimate_avg": 0}],
        "ratios": {"return_on_equity": 0, "debt_to_equity": -1},
        "company_news": [{"headline": "Company update", "published_at": "2026-08-20"}],
        "institutional_holders": [{"investor": "Example Fund", "shares": 0, "weight": -0.1}],
    }


@pytest.fixture(autouse=True)
def no_history_provider(monkeypatch):
    monkeypatch.setattr(
        "engines.atlas_research_builder_v2.attach_price_history", lambda row: dict(row)
    )


def test_safe_evidence_helper_contract():
    assert is_missing_scalar(None) and is_missing_scalar("")
    assert not is_missing_scalar(0) and not is_missing_scalar(-2.5)
    assert safe_scalar_display(["x"]) == ""
    assert safe_mapping(["x"]) == {}
    assert safe_sequence({"x": 1}) == []
    assert number(0) == 0 and number(-2.5) == -2.5
    assert safe_date_text(["2026-08-20"]) is None
    assert safe_date_text("not-a-date") is None
    assert safe_date_text("2026-08-20") == "2026-08-20"
    assert hash(semantic_identity({"nested": [0, -1, {"x": "y"}]}))


def test_local_gate_contract_precedes_targeted_deployed_qa():
    assert ATLAS_CRITICAL_LOCAL_GATE_COMMAND == (
        "python3 -m pytest -q tests/test_atlas_critical_local_gate.py"
    )
    assert "must not be recommended" in (__doc__ or "")


def test_nvda_edu_crm_and_missing_production_research_complete():
    for ticker in ("NVDA", "EDU", "CRM", "MSFT"):
        report = build_atlas_research_v2(equity(ticker))
        assert report["ticker"] == ticker
        assert report["analyst_intelligence"]["recent_actions"]
        assert set(report["sections"]) >= {
            "financials", "analysts", "earnings", "risk", "news",
            "ownership", "political", "technical",
        }
        assert isinstance(report["valuation_families"], dict)
        assert isinstance(report["earnings_intelligence"], dict)
        assert isinstance(report["policy_intelligence"], dict)
    missing = build_research_context("MSFT", production_row=None)
    assert missing["production_decision"]["semantic_status"] == "DATA_UNAVAILABLE"
    assert set(missing["production_decision"]) == {"semantic_status"}


def test_spy_etf_and_invalid_ticker_boundaries():
    spy_context = build_research_context(
        "SPY", production_row={"ticker": "SPY", "security_type": "ETF"}, security_type="ETF"
    )
    assert all(
        spy_context["evidence_families"][family]["semantic_status"] == "NOT_APPLICABLE"
        for family in CORPORATE_ONLY_FAMILIES
    )
    spy_report = build_atlas_research_v2({"ticker": "SPY", "security_type": "ETF"})
    assert spy_report["security_type"] == "ETF"
    assert spy_report["earnings_intelligence"]["semantic_status"] == "NOT_APPLICABLE"
    assert re.fullmatch(r"[A-Z]{1,10}(?:[.-][A-Z]{1,3})?", "INVALID123") is None


@pytest.mark.parametrize("family", (
    "profile", "financials", "ratios", "earnings_history",
    "analyst_estimates", "analyst_recommendation_counts", "analyst_consensus",
    "analyst_targets", "analyst_actions", "valuation_families", "technical",
    "institutional_holders", "ownership", "company_news", "press_releases",
    "political", "management_guidance", "transcript_intelligence",
    "market_context_inputs",
))
@pytest.mark.parametrize("value", STRUCTURAL_VALUES)
def test_complete_research_builder_structural_fuzz(family, value):
    row = equity()
    row[family] = deepcopy(value)
    report = build_atlas_research_v2(row)
    assert report["ticker"] == "NVDA"
    assert isinstance(report["sections"], dict)
    assert isinstance(report["evidence_registry"], dict)


@pytest.mark.parametrize("value", STRUCTURAL_VALUES)
def test_analyst_render_preparation_is_container_safe(value):
    intelligence = {
        "wall_street_mean_target": value,
        "wall_street_implied_upside_pct": value,
        "analyst_coverage": value,
        "analyst_agreement": value,
    }
    html = _analyst_intelligence_html(intelligence)
    assert html.startswith('<div class="atlas-analyst-grid">')
    if isinstance(value, (list, dict, tuple)):
        assert "nested" not in html


def test_deployed_analyst_container_sentinel_regression():
    """A list metric must never enter hash-based scalar-sentinel membership."""
    html = _analyst_intelligence_html({
        "analyst_coverage": ["malformed-provider-shape"],
        "analyst_agreement": {"malformed": "provider-shape"},
    })
    assert "malformed-provider-shape" not in html
    assert "provider-shape" not in html


@pytest.mark.parametrize("row", STRUCTURAL_VALUES)
def test_deployed_analyst_source_traversal_accepts_only_mappings(row):
    """Run #58 failed at analyst_intelligence._first source traversal."""
    result = build_analyst_intelligence(row)
    assert result["wall_street_mean_target"] is None
    assert result["recent_actions"] == []


def test_home_research_session_and_ask_round_trip():
    state = {"authenticated": True, "role": "viewer", "user_role": "viewer", "v73_page": "Home", "nav": "Home"}
    state.update(research_navigation_state("CRM"))
    selected, pending = consume_navigation_handoff(state, PAGES, widget_key="nav")
    assert pending and selected == "Research Any Ticker"
    assert state["v73_research_ticker"] == state["selected_ticker"] == "CRM"
    assert stabilize_authenticated_session(state)
    state["v79_pending_page"] = "Ask AI"
    assert consume_navigation_handoff(state, PAGES, widget_key="nav")[0] == "Ask AI"
    report = build_atlas_research_v2(equity("CRM"))
    answer = ask_atlas("Why does ATLAS like this company?", report)
    assert answer["ticker"] == "CRM"
    state.update(research_navigation_state("CRM"))
    assert consume_navigation_handoff(state, PAGES, widget_key="nav")[0] == "Research Any Ticker"
    assert state["authenticated"] is True


@pytest.mark.parametrize("transaction", ("Purchase", "Sale"))
def test_political_evidence_render_preparation(transaction):
    result = normalize_political_transaction({
        "symbol": "CRM", "representative": "Example Member", "transaction": transaction,
        "transactionDate": "2026-08-01", "disclosureDate": "2026-08-20",
        "amountRange": "$1,001 - $15,000", "url": "https://example.test/disclosure",
        "chamber": None,
    })
    assert result and result["transaction_type"] in {"Buy", "Sell"}
    assert result["transaction_date"] != result["disclosure_date"]
    assert result["reported_amount_range"] == "$1,001 - $15,000"
    assert result["source_url"].startswith("https://")


@pytest.mark.parametrize("evidence_ids,limitations", (
    (["evidence-1"], ["partial"]), ([], []), (None, None),
    ({"malformed": "container"}, {"malformed": "container"}),
))
def test_ask_grounding_structural_variants(evidence_ids, limitations):
    report = build_atlas_research_v2(equity())
    report["research_context"] = {"evidence_families": {"analyst_actions": {
        "evidence_ids": evidence_ids, "limitations": limitations, "fetched_at": "2026-08-20",
    }}}
    result = ask_atlas("What do analysts think?", report)
    assert result["ticker"] == "NVDA"
    assert isinstance(result["evidence_ids_used"], list)
    assert isinstance(result["evidence_limitations"], list)
