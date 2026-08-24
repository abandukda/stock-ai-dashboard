from __future__ import annotations

from pathlib import Path

from agents.ai_content_integrity_v3 import summary_similarity
from agents.runtime_qa_user_journeys_v40 import (
    ERROR_RE,
    ask_grounding_complete,
    navigation_contract_satisfied,
    research_context_complete,
)
from engines.ask_atlas_engine import ask_atlas
from engines.guidance_summary import build_guidance_summary, guidance_summary_text


def _summary(row):
    return guidance_summary_text(build_guidance_summary(row))


def test_navigation_contract_accepts_real_settlement_and_rejects_partial_state():
    assert navigation_contract_satisfied(selected=True, page_ready=True, rendered_exception=False)
    assert not navigation_contract_satisfied(selected=False, page_ready=True, rendered_exception=False)
    assert not navigation_contract_satisfied(selected=True, page_ready=False, rendered_exception=False)
    assert not navigation_contract_satisfied(selected=True, page_ready=True, rendered_exception=True)


def test_research_and_ask_contexts_are_ticker_isolated():
    research = {
        "ticker": "NVDA",
        "company": "NVIDIA Corporation",
        "security-type": "Equity",
        "generated-at": "2026-08-18T12:00:00Z",
        "context-version": "RESEARCH_CONTEXT_V1",
        "decision-digest": "digest",
    }
    ask = {
        "ticker": "NVDA",
        "section": "overview",
        "generated-at": "2026-08-18T12:00:00Z",
        "framework": "ASK_ATLAS_GROUNDED_V1",
        "context-version": "RESEARCH_CONTEXT_V1",
        "context-digest": "digest",
        "decision-status": "AVAILABLE",
        "decision-digest": "decision-digest",
    }
    assert research_context_complete(research, "NVDA")
    assert ask_grounding_complete(ask, "NVDA")
    assert not research_context_complete(research, "CRM")
    assert not ask_grounding_complete(ask, "AVGO")


def test_app_emits_nonempty_page_research_and_ask_contracts():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'data-atlas-page="home"' in source
    assert 'data-atlas-page="research-any-ticker"' in source
    assert 'data-atlas-page="ask-ai"' in source
    assert "research-complete</span>" in source
    assert "ask-ai-complete</span>" in source
    assert 'data-atlas-company=' in source
    assert 'data-atlas-security-type=' in source
    assert 'data-atlas-generated-at=' in source
    assert "except ImportError:" in source
    assert "token in allowed" in source
    assert ERROR_RE.search("ImportError: partially initialized module")


def test_ask_atlas_returns_verifiable_grounding_metadata():
    report = {
        "ticker": "NVDA",
        "company": "NVIDIA Corporation",
        "committee_verdict": "MONITOR",
        "generated_at": "2026-08-18T12:00:00Z",
        "sections": {"risk": {"status": "available", "interpretation": "Execution risk is monitored."}},
        "evidence_registry": {"risk": {"status": "AVAILABLE"}},
        "intelligence": {"key_risks": ["Valuation requires execution."], "executive_summary": "NVDA evidence is under review."},
    }
    result = ask_atlas("What are the risks for NVDA?", report)
    assert result["ticker"] == "NVDA"
    assert result["section"] == "risk"
    assert result["evidence_used"] == ["risk"]
    assert result["evidence_missing"] == []
    assert result["generated_at"] == report["generated_at"]
    assert result["framework_version"] == "ASK_ATLAS_GROUNDED_V1"
    assert "NVDA" in result["answer"]


def test_company_specific_evidence_materially_differentiates_summaries():
    wbs = {
        "ticker": "WBS", "company": "Webster Financial", "sector": "Financial Services",
        "industry": "Banks - Regional", "committee_verdict": "MONITOR",
        "revenue_growth": -0.08, "earnings_growth": -0.12,
        "total_debt": 8_200_000_000, "total_cash": 1_100_000_000,
        "current_price": 48, "sma200": 54,
    }
    trgp = {
        "ticker": "TRGP", "company": "Targa Resources", "sector": "Energy",
        "industry": "Oil & Gas Midstream", "committee_verdict": "MONITOR",
        "revenue_growth": 0.17, "operating_margin": 0.22,
        "free_cash_flow": 2_400_000_000, "roic": 0.14,
        "current_price": 170, "sma200": 151,
    }
    wbs_guidance = build_guidance_summary(wbs)
    left, right = guidance_summary_text(wbs_guidance), _summary(trgp)
    assert "Banks - Regional" in left and "Oil & Gas Midstream" in right
    assert any("Debt of $8.2B" in item["risk"] for item in wbs_guidance["key_risks"])
    assert "free cash flow of $2.4B" in right
    assert summary_similarity(left, right, left_ticker="WBS", right_ticker="TRGP", left_company="Webster Financial", right_company="Targa Resources") < 82


def test_primary_risk_prioritizes_verified_leverage_over_generic_fallback():
    guidance = build_guidance_summary({
        "ticker": "DEBT", "total_debt": 10_000_000_000, "total_cash": 1_000_000_000,
        "primary_risk": "RSI is warm and a normal pullback is possible.",
    })
    assert guidance["key_risks"][0]["domain"] == "leverage"
    assert "more than twice cash" in guidance["key_risks"][0]["risk"]


def test_multi_quarter_earnings_history_is_used_without_losing_zero_or_misses():
    guidance = build_guidance_summary({
        "ticker": "HIST",
        "earnings_history": [
            {"date": "2026-06-30", "eps_surprise_pct": 0.0},
            {"date": "2026-03-31", "eps_surprise_pct": -3.0},
            {"date": "2025-12-31", "eps_surprise_pct": -1.0},
            {"date": "2025-09-30", "eps_surprise_pct": 2.0},
        ],
    })
    facts = " ".join(item["fact"] for item in guidance["supporting_facts"])
    risks = " ".join(item["risk"] for item in guidance["key_risks"])
    assert "4 quarters" in facts
    assert "1 EPS beat and 2 misses" in facts
    assert "2 EPS misses versus 1 beats" in risks


def test_evidence_limited_summary_fails_closed_without_inventing_specifics():
    guidance = build_guidance_summary({"ticker": "LIMITED", "company": "Limited Evidence Co", "committee_verdict": "MONITOR"})
    text = guidance_summary_text(guidance)
    assert guidance["evidence_limited"] is True
    assert guidance["supporting_facts"] == []
    assert guidance["key_risks"] == []
    assert "evidence-limited" in text
    assert "No verified next catalyst is available" in text
