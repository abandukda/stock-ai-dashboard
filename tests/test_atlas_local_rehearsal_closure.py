"""Regressions found by the continuous local targeted-preflight rehearsal."""
from __future__ import annotations

import ast
from pathlib import Path

from services.fmp_research_acquisition import acquire_explicit_fmp_research
from engines.live_research_engine import build_live_research


ROOT = Path(__file__).resolve().parents[1]


def _final_function(source: str, name: str) -> ast.FunctionDef:
    return [
        node for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ][-1]


def test_providerless_etf_context_is_fail_closed_before_any_corporate_request(tmp_path):
    result = acquire_explicit_fmp_research(
        "SPY",
        production_row=None,
        security_type="ETF",
        api_key="",
        cache_root=tmp_path,
    )

    context = result["research_context"]
    assert context["security_type"] == "ETF"
    assert result["diagnostics"]["requests"] == 0
    for family in (
        "financial_statements",
        "earnings_history",
        "analyst_estimates",
        "management_guidance",
        "transcript_intelligence",
    ):
        assert context["evidence_families"][family]["semantic_status"] == "NOT_APPLICABLE"


def test_providerless_etf_never_falls_through_to_legacy_corporate_acquisition(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy Yahoo acquisition must not run for an ETF")

    monkeypatch.setattr("engines.live_research_engine.yf.Ticker", forbidden)
    monkeypatch.setattr("engines.live_research_engine._download_history", forbidden)

    row = build_live_research("SPY", fmp_api_key="", security_type_hint="ETF")

    assert row["security_type"] == "ETF"
    assert row["research_context"]["security_type"] == "ETF"
    assert row["research_context"]["production_decision"]["semantic_status"] == "DATA_UNAVAILABLE"


def test_active_research_route_passes_etf_identity_before_acquisition():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    research = ast.unparse(_final_function(source, "render_research_any_ticker"))

    assert "security_type_hint=_security_hint" in research
    assert "quote_type" in research
    assert "ticker == 'SPY'" in research


def test_ask_prefers_exact_canonical_row_rendered_by_research():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    ask = ast.unparse(_final_function(source, "render_chat_helper"))
    research = ast.unparse(_final_function(source, "render_research_any_ticker"))

    assert "atlas_canonical_research_row_" in ask
    assert "atlas_canonical_research_row_" in research
    assert ask.index("atlas_canonical_research_row_") < ask.index("v8054_live_row_")
