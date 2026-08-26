from __future__ import annotations

import ast
from pathlib import Path

from agents.product_hardening_certification import (
    ACTIVE_PAGES, DEEP_CERTIFICATION_PAGES, EVIDENCE_CLAIM_CONTRACTS,
    MOBILE_CRITICAL_JOURNEYS, certification_matrix_contract,
)
from agents.runtime_qa_interactions import CORE_INTERACTION_PAGES, interaction_registry
from engines.ask_atlas_engine import ask_atlas
from engines.political_evidence import normalize_political_transaction
from services.session_stability import consume_navigation_handoff, stabilize_authenticated_session


def test_authenticated_session_survives_complete_research_journey():
    state = {"authenticated": True, "role": "viewer", "v73_page": "Home"}
    pages = list(ACTIVE_PAGES)
    for destination in (
        "Research Any Ticker", "Research Any Ticker", "Ask AI",
        "Research Any Ticker", "Home",
    ):
        state["v79_pending_page"] = destination
        selected, pending = consume_navigation_handoff(state, pages, widget_key="nav")
        assert pending and selected == destination
        assert stabilize_authenticated_session(state)
        assert state["authenticated"] is True
        assert state["role"] == state["user_role"] == "viewer"


def test_navigation_handoff_overrides_stale_widget_page():
    state = {"authenticated": True, "v73_page": "Home", "nav": "Home", "v79_pending_page": "Research Any Ticker"}
    selected, pending = consume_navigation_handoff(state, ACTIVE_PAGES, widget_key="nav")
    assert pending is True
    assert selected == "Research Any Ticker"
    assert state["nav"] == "Research Any Ticker"
    assert "v79_pending_page" not in state


def test_active_final_navigation_definition_consumes_pending_handoff():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_v73_top_nav"]
    active = ast.unparse(definitions[-1])
    assert "consume_navigation_handoff" in active
    assert "v79_pending_page" not in active  # centralized in the pure helper


def test_political_transaction_preserves_auditable_dates_and_provenance():
    row = {
        "symbol": "NVDA", "representative": "Example Member", "chamber": "House",
        "transaction": "Purchase", "transactionDate": "2026-01-02",
        "disclosureDate": "2026-01-20", "amountRange": "$1,001 - $15,000",
        "source": "FMP", "url": "https://example.test/disclosure/1",
        "assetDescription": "NVIDIA Corporation",
    }
    result = normalize_political_transaction(row)
    assert result
    assert result["evidence_type"] == "CONGRESSIONAL_TRANSACTION"
    assert result["transaction_date"] == "2026-01-02"
    assert result["disclosure_date"] == "2026-01-20"
    assert result["reported_amount_range"] == "$1,001 - $15,000"
    assert result["evidence_id"].startswith("political-")
    assert result["source_url"].startswith("https://")
    assert "value" not in result  # ranges are never converted into invented dollars


def test_political_and_other_ownership_evidence_remain_separate():
    result = normalize_political_transaction({"symbol": "AAPL", "transaction": "Sale"})
    assert result and result["evidence_type"] == "CONGRESSIONAL_TRANSACTION"
    assert "institutional" not in result
    assert "insider" not in result


def test_ask_grounding_exposes_canonical_evidence_ids_and_dates():
    report = {
        "ticker": "NVDA", "generated_at": "2026-08-26T00:00:00Z",
        "research_context": {"evidence_families": {
            "company_news": {
                "evidence_ids": ["news-1"], "observation_date": "2026-08-25",
                "limitations": ["ONE_PROVIDER"],
            }
        }},
        "evidence_registry": {"company_news": {"status": "AVAILABLE"}},
        "sections": {"news": {"status": "available", "data": []}},
    }
    result = ask_atlas("What news matters?", report)
    assert result["ticker"] == "NVDA"
    assert result["evidence_ids_used"] == ["news-1"]
    assert result["as_of_date"] == "2026-08-25"
    assert result["evidence_limitations"] == ["ONE_PROVIDER"]


def test_complete_page_interaction_and_evidence_contract_inventory():
    matrix = certification_matrix_contract()
    assert len(ACTIVE_PAGES) == 14
    assert len(DEEP_CERTIFICATION_PAGES) == 9
    assert set(DEEP_CERTIFICATION_PAGES).issubset(CORE_INTERACTION_PAGES)
    assert "Political Intelligence" in EVIDENCE_CLAIM_CONTRACTS
    assert "Ask AI" in EVIDENCE_CLAIM_CONTRACTS
    assert len(MOBILE_CRITICAL_JOURNEYS) == 9
    assert matrix["columns"] == (
        "page", "interaction", "expected", "observed", "evidence_source",
        "desktop", "mobile", "status", "severity",
    )
    registry = interaction_registry()
    ids = {item["stable_id"] for item in registry["interactions"]}
    assert {"political-transaction-details", "political-research-link"}.issubset(ids)


def test_major_ticker_drilldowns_emit_machine_checkable_contracts():
    opportunities = Path("ui/daily_opportunities.py").read_text(encoding="utf-8")
    app = Path("app.py").read_text(encoding="utf-8")
    assert "opportunities-research-" in opportunities
    assert 'data-atlas-expected-page="research-any-ticker"' in opportunities
    assert "earnings-research-" in app
    assert "political-research-" in app
    assert app.count('data-atlas-expected-page="research-any-ticker"') >= 2


def test_render2_instrumentation_is_preserved():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="research-render-exception"' in source
    assert "sanitized_exception_location" in source
    assert "raise\n" in source
