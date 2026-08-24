from __future__ import annotations

import ast
import inspect
from pathlib import Path

from agents.runtime_qa_architecture import certify_etf_context
from agents.runtime_qa_user_journeys_v40 import (
    ERROR_RE, ask_grounding_complete,
    cross_page_digest_result,
    research_content_sections,
    research_lifecycle_complete,
)
from engines.live_research_engine import _attach_canonical_research_context
from engines import live_research_engine
from engines.research_context import AVAILABLE, DATA_UNAVAILABLE, build_research_context, evidence_envelope


ROOT = Path(__file__).resolve().parents[1]


def _available(ticker: str, family: str, provider: str, data: dict):
    return evidence_envelope(
        ticker=ticker,
        family=family,
        semantic_status=AVAILABLE,
        cache_status="FETCHED",
        provider=provider,
        endpoint_family=family,
        fetched_at="2026-08-23T12:00:00+00:00",
        data=data,
    )


def test_canonical_family_wins_and_unavailable_family_falls_back_explicitly(monkeypatch):
    monkeypatch.setattr("engines.live_research_engine.load_production_row", lambda _ticker: None)
    canonical = build_research_context(
        "NVDA",
        production_row=None,
        evidence_families={
            "analyst_actions": _available("NVDA", "analyst_actions", "FMP", {"actions": [{"firm": "Canonical"}]}),
        },
    )
    row = {
        "ticker": "NVDA",
        "analyst_actions": [{"firm": "Legacy"}],
        "latest_news_headline": "Verified legacy fallback",
        "latest_news_source": "NEWSAPI",
        "latest_news_date": "2026-08-22",
        "research_refreshed_at": "2026-08-23T12:00:00+00:00",
    }

    result = _attach_canonical_research_context(row, "NVDA", canonical_context=canonical)
    families = result["research_context"]["evidence_families"]
    assert families["analyst_actions"]["provider"] == "FMP"
    assert families["analyst_actions"]["data"]["actions"] == [{"firm": "Canonical"}]
    assert families["company_news"]["provider"] == "NEWSAPI"
    assert families["company_news"]["fallback_reason"] == "CANONICAL_FMP_FAMILY_UNAVAILABLE"
    assert "fallback_freshness" in families["company_news"]
    assert families["company_news"]["limitations"]


def test_streamlit_loaded_fmp_secret_is_passed_to_explicit_research(monkeypatch):
    captured = {}

    def fake_acquire(symbol, *, production_row, api_key, force_refresh):
        captured.update(symbol=symbol, api_key=api_key, force_refresh=force_refresh)
        return {"research_context": build_research_context(symbol, production_row=production_row), "diagnostics": {}}

    monkeypatch.setattr("services.fmp_research_acquisition.acquire_explicit_fmp_research", fake_acquire)
    live_research_engine._explicit_fmp_research_context("NVDA", None, api_key="configured-secret")
    assert captured == {"symbol": "NVDA", "api_key": "configured-secret", "force_refresh": False}
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "fmp_api_key=FMP_API_KEY" in app_source
    assert "fmp_api_key" in inspect.signature(live_research_engine.build_live_research).parameters


def test_research_requires_both_canonical_and_render_readiness():
    assert not research_lifecycle_complete(canonical_context_ready=True, render_complete=False, rendered_exception=False)
    assert not research_lifecycle_complete(canonical_context_ready=False, render_complete=True, rendered_exception=False)
    assert not research_lifecycle_complete(canonical_context_ready=True, render_complete=True, rendered_exception=True)
    assert research_lifecycle_complete(canonical_context_ready=True, render_complete=True, rendered_exception=False)


def test_earnings_intelligence_is_content_not_an_error_marker():
    text = "Earnings Intelligence\nReported quarterly evidence"
    assert "Earnings Intelligence" in research_content_sections(text)
    assert ERROR_RE.search(text) is None


def test_ask_grounding_fails_without_context_version_and_digest():
    incomplete = {
        "ticker": "NVDA",
        "context-version": "",
        "decision-status": "",
        "decision-digest": "",
        "context-digest": "",
    }
    assert not ask_grounding_complete(incomplete, "NVDA")


def test_missing_production_ticker_has_no_synthetic_decision():
    context = build_research_context(
        "AAPL",
        production_row=None,
        evidence_families={"profile": _available("AAPL", "profile", "FMP", {"company_name": "Apple"})},
    )
    assert context["production_decision"]["semantic_status"] == DATA_UNAVAILABLE
    assert set(context["production_decision"]) == {"semantic_status"}
    assert context["evidence_families"]["profile"]["semantic_status"] == AVAILABLE


def test_spy_corporate_families_are_not_applicable():
    context = build_research_context("SPY", production_row=None, security_type="ETF")
    result = certify_etf_context(context)
    assert result["classification"] == "PASS_WITH_EVIDENCE_LIMITATIONS"
    for family in ("earnings_history", "analyst_estimates", "management_guidance", "transcript_index", "transcript_intelligence"):
        assert context["evidence_families"][family]["semantic_status"] == "NOT_APPLICABLE"


def test_invalid_ticker_is_rejected_before_research_acquisition():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 're.fullmatch(r"[A-Z]{1,10}(?:[.-][A-Z]{1,3})?", ticker)' in source
    assert "Ticker not recognized. Atlas could not retrieve a valid security" in source
    assert not __import__("re").fullmatch(r"[A-Z]{1,10}(?:[.-][A-Z]{1,3})?", "INVALID123")


def test_home_global_ready_marker_is_not_conditional_on_nonempty_data():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_emit_page_certification_marker")
    source = ast.get_source_segment((ROOT / "app.py").read_text(encoding="utf-8"), function) or ""
    assert 'data-atlas-qa="page-ready"' in source
    assert "if source_df is None" not in source
    assert "return" not in source.split("except Exception:", 1)[0]
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    main_start = app_source.index("def main():")
    main_end = app_source.index("# V82 DECISION INTELLIGENCE", main_start)
    main_source = app_source[main_start:main_end]
    assert main_source.rindex("_emit_page_certification_marker") > main_source.rindex("render_developer_center")


def test_research_ready_marker_is_guarded_by_finalized_context():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '_qa_summary.get("context_version") == "RESEARCH_CONTEXT_V1"' in source
    assert '"ready" if _qa_context_ready else "unavailable"' in source


def test_cross_page_digest_requires_nonempty_consistent_capture():
    assert cross_page_digest_result("INSM", {})["status"] == "NOT_EXECUTED"
    assert cross_page_digest_result("INSM", {"Home": "a", "Research": "b"})["status"] == "FAIL"
    result = cross_page_digest_result("INSM", {"Home": "same", "Research": "same"})
    assert result["status"] == "PASS" and result["consistent"]


def test_research_renderer_does_not_reacquire_legacy_yahoo_actions():
    source = (ROOT / "ui" / "research_report_v2.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_atlas_research_v2")
    rendered = ast.get_source_segment(source, function) or ""
    assert "fetch_analyst_action_history" not in rendered
    assert 'canonical_families.get("analyst_actions")' in rendered


def test_supported_architecture_drift_is_not_flattened_to_product_defect():
    source = (ROOT / "agents" / "atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert 'supported_classification = reconciliation.get("classification")' in source
    assert "classification=supported_classification" in source
