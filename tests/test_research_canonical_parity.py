from copy import deepcopy

from engines.atlas_research_builder_v2 import build_atlas_research_v2
import engines.live_research_engine as live_research
from ui.research_vnext import _reconcile_canonical_context


def canonical(action="WAIT_FOR_CONFIRMATION", price=101.0):
    return {
        "version": "CANONICAL_INVESTMENT_EVALUATION_V1",
        "evaluation_mode": "ON_DEMAND",
        "evaluated_at": "2026-09-09T20:00:00+00:00",
        "market_snapshot": {"price": price, "provider_timestamp": "2026-09-09T19:59:00+00:00"},
        "technical_confirmation": {"status": "AVAILABLE", "state": "BASE_FORMING", "score": 70},
        "fundamentals": {"status": "AVAILABLE", "score": 72},
        "risk": {"status": "AVAILABLE", "score": 68},
        "technical_quality": {"score": 70}, "fundamental_quality": {"score": 72},
        "valuation_quality": {"score": 75}, "risk_quality": {"score": 68},
        "entry_quality": {"score": 65}, "volume_quality": {"score": 60},
        "opportunity": 74, "decision_confidence": 71, "component_coverage": 96,
        "atlas_valuation": {"status": "PUBLISHED", "fair_value": 140.0, "expected_return": 38.6},
        "trade_plan": {"entry_low": 98, "entry_high": 104, "stop": 90, "target": 140},
        "guidance": {"state": action, "actionability": "NOT_ACTIONABLE", "reason_codes": ()},
        "actionability": {"status": "NOT_ACTIONABLE"},
        "positive_action_revalidation": {"status": "NOT_REQUIRED"},
        "publication_certification": {"action_publication_eligible": True},
    }


def test_same_snapshot_research_preserves_exact_canonical_authority(monkeypatch):
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    evaluation = canonical()
    production = {"ticker": "PAR", "canonical_investment_evaluation": deepcopy(evaluation)}
    context = _reconcile_canonical_context({"current_evaluation": deepcopy(evaluation)}, production)
    assert context["current_evaluation"] == evaluation
    assert context["production_evaluation"] == evaluation
    for field in (
        "market_snapshot", "technical_confirmation", "fundamentals", "risk",
        "technical_quality", "fundamental_quality", "valuation_quality", "risk_quality",
        "entry_quality", "volume_quality", "opportunity", "decision_confidence",
        "component_coverage", "atlas_valuation", "trade_plan", "guidance",
        "positive_action_revalidation", "publication_certification",
    ):
        assert context["current_evaluation"][field] == production["canonical_investment_evaluation"][field]


def test_fresh_current_evaluation_is_not_overridden_by_legacy_decisions(monkeypatch):
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    current = canonical("WAIT_FOR_ENTRY", 105)
    production = {"ticker": "PAR", "canonical_investment_evaluation": canonical("BUY_NOW", 100)}
    context = _reconcile_canonical_context({"current_evaluation": current}, production)
    report = build_atlas_research_v2({
        "ticker": "PAR", "current_price": 105, "committee_verdict": "AVOID",
        "validated_fair_value": 999, "atlas_fair_value": 999,
        "research_context": context,
    })
    assert context["current_evaluation"] == current
    assert context["production_evaluation"]["guidance"]["state"] == "BUY_NOW"
    assert report["committee_verdict"] == "WAIT_FOR_ENTRY"
    assert report["atlas_fair_value"] == 140
    assert report["validated_fair_value"] == 140
    assert report["atlas_expected_return_pct"] == 38.6
    assert report["trade_plan"]["entry_low"] == 98
    assert report["opportunity_score"] == 74
    assert report["confidence_pct"] == 71
    assert report["publication_certification"] == {"action_publication_eligible": True}


def test_ticker_outside_top150_retains_on_demand_evaluation_without_production_row():
    current = canonical()
    context = _reconcile_canonical_context({"current_evaluation": current}, None)
    assert context["current_evaluation"] == current
    assert "production_evaluation" not in context


def test_etf_current_evaluation_remains_on_etf_route(monkeypatch):
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    current = canonical()
    current["atlas_valuation"] = {"status": "NOT_APPLICABLE", "fair_value": None}
    report = build_atlas_research_v2({
        "ticker": "SPY", "security_type": "ETF", "is_etf": True,
        "research_context": {"current_evaluation": current},
    })
    assert report["security_type"] == "ETF"
    assert report["atlas_valuation_status"] == "NOT_APPLICABLE"
    assert report["atlas_fair_value"] is None


def test_active_research_shell_does_not_invoke_legacy_quantitative_history(monkeypatch):
    monkeypatch.setattr(live_research, "load_production_row", lambda _symbol: None)
    monkeypatch.setattr(live_research, "load_cached_research", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live_research, "_explicit_fmp_research_context", lambda *_args, **_kwargs: (None, {}))
    monkeypatch.setattr(
        live_research, "_download_history",
        lambda _symbol: (_ for _ in ()).throw(AssertionError("legacy quantitative history invoked")),
    )
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "false")
    result = live_research.build_live_research("OUTSIDE", force_refresh=True, fmp_api_key="")
    assert result["ticker"] == "OUTSIDE"
    assert result["research_source"] == "canonical_research_shell"
    assert result["research_context"]["production_decision"]["semantic_status"] == "DATA_UNAVAILABLE"
