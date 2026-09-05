from __future__ import annotations

from datetime import datetime, timezone
from streamlit.testing.v1 import AppTest

from engines.atlas_guidance_v1 import founder_guidance_v1_enabled, evaluate_guidance
from engines.canonical_investment_evaluation_v1 import build_canonical_evaluation
from engines.volume_intelligence_v1 import NORMAL, STRONG_CONFIRMATION, build_volume_intelligence
from services.canonical_market_snapshot import build_market_snapshot
from services.llm_output_integrity import enforce_llm_integrity
from services.on_demand_evaluation_service import apply_guidance_hysteresis, evaluate_on_demand


NOW = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)


def market(*, fresh=True, price=100.0):
    stamp = "2026-09-02T15:00:00+00:00"
    return build_market_snapshot("TEST", {
        "price": price, "provider": "TEST", "provider_timestamp": stamp,
        "received_timestamp": stamp, "market_session": "REGULAR",
        "source_type": "CURRENT_QUOTE" if fresh else "LAST_KNOWN",
        "stale": not fresh, "feed_health": "HEALTHY" if fresh else "DEGRADED",
    }, now=NOW)


def technical(state="BREAKOUT_CONFIRMED", score=70, relative_volume=2.0, completed=True):
    return {
        "status": "AVAILABLE", "state": state, "score": score,
        "as_of": "2026-09-02T15:00:00+00:00", "feed_health": "HEALTHY",
        "completed_bar": completed,
        "evidence": {
            "relative_volume": relative_volume,
            "confirmation_relative_volume": relative_volume,
            "average_dollar_volume": 10_000_000,
        },
    }


def valuation_inputs(forward_eps=6.0, **extra):
    return {
        "forward_eps": forward_eps, "forward_eps_source": "CANONICAL_ESTIMATE",
        "revenue_growth": 10, "revenue_growth_source": "CANONICAL_FINANCIALS",
        "revenue_growth_horizon": "TTM", "operating_margin": 20, **extra,
    }


def evaluation(**overrides):
    args = {
        "evaluation_mode": "ON_DEMAND", "market_snapshot": market(),
        "technical": technical(), "fundamentals": {"status": "AVAILABLE", "score": 70, "as_of": "2026-09-01"},
        "risk": {"status": "AVAILABLE", "as_of": "2026-09-01"},
        "trade_plan": {"entry_low": 95, "entry_high": 105, "stop": 90, "target_1": 120},
        "opportunity": 75, "decision_confidence": 72, "coverage": 80,
        "valuation_inputs": valuation_inputs(), "valuation_component_score": 65,
    }
    args.update(overrides)
    return build_canonical_evaluation("TEST", **args)


def test_buy_now_requires_every_affirmative_gate():
    result = evaluation()
    assert result["guidance"]["state"] == "BUY_NOW"
    assert result["actionability"]["status"] == "ACTIONABLE"


def test_accumulate_is_affirmative_and_uses_approved_technical_states():
    result = evaluation(
        technical=technical("SETUP_FORMING", 60, 1.0), opportunity=64,
        decision_confidence=58, coverage=60,
    )
    assert result["guidance"]["state"] == "ACCUMULATE"
    extended = evaluation(technical=technical("EXTENDED", 70, 2.0))
    assert extended["guidance"]["state"] == "WAIT_FOR_ENTRY"


def test_missing_or_rejected_valuation_preserves_nonbuy_guidance():
    result = evaluation(
        technical=technical("NEAR_BREAKOUT", 62, .8),
        valuation_inputs={"forward_pe": None, "forward_eps": None},
    )
    assert result["atlas_valuation"]["status"] == "INSUFFICIENT_INPUTS"
    assert result["guidance"]["state"] == "WAIT_FOR_CONFIRMATION"
    assert "VALUATION_CONFIRMATION_UNAVAILABLE" in result["guidance"]["reason_codes"]


def test_minimum_evidence_failure_is_data_limited():
    result = evaluation(technical={"status": "DATA_UNAVAILABLE", "state": "UNAVAILABLE"})
    assert result["guidance"]["state"] == "DATA_LIMITED"
    assert result["actionability"]["status"] == "UNAVAILABLE"


def test_avoid_requires_two_authoritative_negative_confirmations():
    one = evaluation(
        fundamentals={"status": "AVAILABLE", "score": 30},
        technical=technical("SETUP_FORMING", 60, 1.0),
    )
    assert one["guidance"]["state"] != "AVOID"
    two = evaluation(
        fundamentals={"status": "AVAILABLE", "score": 30},
        technical=technical("FAILED_BREAKOUT", 30, 1.0),
    )
    assert two["guidance"]["state"] == "AVOID"


def test_trade_plan_incomplete_prevents_positive_guidance():
    result = evaluation(trade_plan={"entry_low": 95, "entry_high": 105, "stop": 90})
    assert result["guidance"]["state"] == "WAIT_FOR_CONFIRMATION"
    assert "TRADE_PLAN_INCOMPLETE" in result["guidance"]["reason_codes"]


def test_volume_states_publish_only_approved_taxonomy_and_partial_bar_cannot_confirm():
    strong = build_volume_intelligence({
        "relative_volume": 1.4, "average_dollar_volume": 2_000_000,
        "breakout_candidate": True, "completed_bar": True, "feed_health": "HEALTHY",
    })
    partial = build_volume_intelligence({
        "relative_volume": 2.0, "average_dollar_volume": 10_000_000,
        "breakout_candidate": True, "completed_bar": False, "feed_health": "HEALTHY",
    })
    low = build_volume_intelligence({
        "relative_volume": .2, "breakout_candidate": False,
        "completed_bar": True, "feed_health": "HEALTHY",
    })
    assert strong["state"] == STRONG_CONFIRMATION
    assert partial["state"] != STRONG_CONFIRMATION
    assert low["state"] == NORMAL
    assert "WEAK_CONFIRMATION" not in {strong["state"], partial["state"], low["state"]}


def test_market_snapshot_never_labels_last_known_as_current():
    snapshot = market(fresh=False)
    assert snapshot["stale"] is True
    assert snapshot["fresh_current_price"] is False
    assert snapshot["customer_label"] == "Last known price"


def test_hysteresis_blocks_transient_positive_upgrade_but_allows_immediate_downgrade():
    prior = evaluation(technical=technical("NEAR_BREAKOUT", 60, 1.0))
    candidate = evaluation()
    held = apply_guidance_hysteresis(prior, candidate)
    assert held["guidance"]["state"] == prior["guidance"]["state"]
    assert held["guidance"]["reason_codes"] == ("POSITIVE_UPGRADE_CONFIRMATION_PENDING",)
    repeated = apply_guidance_hysteresis(held, {**candidate, "candidate_upgrade_digest": candidate["input_digest"]})
    # The service requires the prior record to carry the same candidate digest.
    held["candidate_upgrade_digest"] = candidate["input_digest"]
    assert apply_guidance_hysteresis(held, candidate)["guidance"]["state"] == "BUY_NOW"
    downgrade = evaluation(technical=technical("EXTENDED", 70, 2.0))
    assert apply_guidance_hysteresis(candidate, downgrade)["guidance"]["state"] == "WAIT_FOR_ENTRY"


def test_wall_street_context_does_not_change_guidance_or_atlas_value():
    base = evaluation()
    with_street = evaluation(valuation_inputs=valuation_inputs(
        analyst_target_mean=999, analyst_target_low=900, analyst_target_high=1100,
    ))
    assert base["guidance"] == with_street["guidance"]
    assert base["atlas_valuation"]["fair_value"] == with_street["atlas_valuation"]["fair_value"]


def test_llm_integrity_rejects_changed_guidance_and_invented_value():
    canonical = evaluation()
    bad = enforce_llm_integrity("ATLAS Guidance: HOLD. Atlas Fair Value is 999.", canonical)
    assert bad["accepted"] is False
    assert "BUY NOW" in bad["text"]
    good = enforce_llm_integrity("ATLAS Guidance: BUY NOW. The deterministic gates passed.", canonical)
    assert good["accepted"] is True
    monitoring = enforce_llm_integrity("What ATLAS is monitoring: completed-bar confirmation.", canonical)
    assert monitoring["accepted"] is True


def test_llm_integrity_mechanically_protects_every_current_decision_field():
    canonical = evaluation()
    opportunity = canonical["opportunity"]
    confidence = canonical["decision_confidence"]
    exact = enforce_llm_integrity(
        f"ATLAS Guidance: BUY NOW. Actionability: ACTIONABLE. Opportunity {opportunity}. "
        f"Decision confidence {confidence}. Atlas fair value 123. Expected return 23. "
        "Technical state BREAKOUT_CONFIRMED. Volume state STRONG_CONFIRMATION. "
        "Entry 95. Stop 90. Target 120.", canonical,
    )
    assert exact["accepted"] is True
    attempts = (
        "ATLAS Guidance: WAIT FOR CONFIRMATION. Actionability: NOT ACTIONABLE.",
        "ATLAS Guidance: BUY NOW. Atlas fair value 999.",
        "ATLAS Guidance: BUY NOW. Volume state NORMAL.",
        "ATLAS Guidance: BUY NOW. Technical state FAILED BREAKOUT.",
        "ATLAS Guidance: BUY NOW. Target 150.",
    )
    for attempt in attempts:
        guarded = enforce_llm_integrity(attempt, canonical)
        assert guarded["accepted"] is False
        assert guarded["text"].startswith("ATLAS Guidance: BUY NOW")


def test_activation_flag_defaults_off_and_has_one_explicit_boundary(monkeypatch):
    monkeypatch.delenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", raising=False)
    assert founder_guidance_v1_enabled() is False
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    assert founder_guidance_v1_enabled() is True


def test_research_context_attachment_is_dormant_off_and_evaluates_on(monkeypatch):
    import engines.live_research_engine as live
    import services.on_demand_evaluation_service as service

    context = {
        "production_decision": {"semantic_status": "DATA_UNAVAILABLE", "recommendation": None},
        "evidence_families": {}, "evidence_registry": {},
    }
    monkeypatch.setattr(live, "load_production_row", lambda symbol: {})
    monkeypatch.setattr(live, "build_research_context", lambda *args, **kwargs: context)
    calls = []
    monkeypatch.setattr(service, "evaluate_on_demand", lambda *args, **kwargs: calls.append(args) or evaluation())

    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "false")
    dormant = live._attach_canonical_research_context({"ticker": "MU"}, "MU")
    assert calls == []
    assert "current_evaluation" not in dormant["research_context"]
    assert "current_canonical_evaluation" not in dormant

    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    active = live._attach_canonical_research_context({"ticker": "MU"}, "MU")
    assert len(calls) == 1
    assert active["current_canonical_evaluation"]["guidance"]["state"] == "BUY_NOW"


def test_research_reuses_scheduled_canonical_evaluation_before_post_shell_refresh(monkeypatch):
    import engines.live_research_engine as live
    import services.on_demand_evaluation_service as service

    published = evaluation()
    context = {"production_decision": {"semantic_status": "DATA_UNAVAILABLE"},
               "evidence_families": {}, "evidence_registry": {}}
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    monkeypatch.setattr(live, "load_production_row", lambda symbol: {"ticker": symbol, "canonical_investment_evaluation": published})
    monkeypatch.setattr(live, "build_research_context", lambda *args, **kwargs: context)
    monkeypatch.setattr(service, "evaluate_on_demand", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must reuse published record")))
    result = live._attach_canonical_research_context({"ticker": "TEST"}, "TEST")
    assert result["current_canonical_evaluation"] == published
    assert result["research_context"]["current_evaluation"] == published


def test_ui_and_ask_ignore_current_evaluation_while_flag_is_off(monkeypatch):
    from ui.research_vnext import _current_evaluation
    from engines.ask_atlas_engine import _compact_context

    report = {
        "research_context": {
            "current_evaluation": evaluation(),
            "production_decision": {"semantic_status": "DATA_UNAVAILABLE", "recommendation": None},
        }
    }
    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "false")
    assert _current_evaluation(report) == {}
    compact = _compact_context(report)
    assert compact["current_canonical_evaluation"] == {}
    assert compact["atlas_guidance"] == {}

    monkeypatch.setenv("ATLAS_FOUNDER_GUIDANCE_V1_ENABLED", "true")
    assert _current_evaluation(report)["guidance"]["state"] == "BUY_NOW"
    assert _compact_context(report)["atlas_guidance"]["state"] == "BUY_NOW"


def test_final_research_renderer_flag_on_exposes_guidance_and_actionability():
    current = repr(evaluation())
    source = f'''\
import os
os.environ["ATLAS_FOUNDER_GUIDANCE_V1_ENABLED"] = "true"
import engines.atlas_research_builder_v2 as builder
import ui.research_report_v2 as legacy
from tests.test_atlas_vnext_ux2_research import report_fixture
report = report_fixture(ticker="MU")
report["research_context"]["current_evaluation"] = {current}
builder.build_atlas_research_v2 = lambda row: report
legacy._load_policy_enrichment = lambda symbol, row: {{"metrics": {{}}}}
legacy._load_ai_valuation = lambda symbol, row: {{}}
import app
app.render_detail({{"ticker": "MU", "research_context": report["research_context"]}})
'''
    rendered = AppTest.from_string(source, default_timeout=30).run()
    assert not rendered.exception
    markdown = "\n".join(str(item.value) for item in rendered.markdown)
    assert "ATLAS Rating:" in markdown
    assert "Data Limited" not in markdown
    assert "Actionability:" in markdown
    assert "Buy Now" in markdown


def test_governed_mu_transition_fixtures_do_not_use_wall_street_authority():
    waiting = evaluation(
        technical=technical("NEAR_BREAKOUT", 60, .8),
        opportunity=61, decision_confidence=55,
    )
    buying = evaluation(valuation_inputs=valuation_inputs(analyst_target_mean=9999))
    accumulating = evaluation(
        technical=technical("SETUP_FORMING", 60, 1.0),
        opportunity=64, decision_confidence=58, coverage=60,
        valuation_inputs=valuation_inputs(analyst_target_mean=1),
    )
    extended = evaluation(technical=technical("EXTENDED", 70, 2.0))
    # Explicit legacy opportunity/confidence overrides are ignored; Wall Street
    # inputs likewise cannot alter the deterministic six-pillar result.
    assert waiting["guidance"]["state"] == "ACCUMULATE"
    assert buying["guidance"]["state"] == "BUY_NOW"
    assert accumulating["guidance"]["state"] == "ACCUMULATE"
    assert extended["guidance"]["state"] == "WAIT_FOR_ENTRY"


def test_mu_snapshot_replay_is_data_limited_without_current_technical_authority():
    result = evaluate_on_demand({
        "ticker": "MU", "price": 956.41,
        "scan_time": "2026-09-01T15:34:20+00:00",
        "rsi": 56.7, "sma20": 930.52, "sma50": 946.37,
        "volume_ratio": .38, "revenue_growth": .1, "risk_reward": 1.8,
        "recommendation_key": "strong_buy", "analyst_target_mean": 1513.41,
        "confidence": 97, "conviction": 97,
    })
    assert result["guidance"]["state"] == "DATA_LIMITED"
    assert "CURRENT_MARKET_EVIDENCE_UNAVAILABLE" in result["guidance"]["reason_codes"]
    assert "TECHNICAL_STRUCTURE_UNAVAILABLE" in result["guidance"]["reason_codes"]
    assert result["opportunity"] is None
    assert result["decision_confidence"] is None
    assert result["market_snapshot"]["source_type"] == "LAST_KNOWN"


def test_snapshot_and_on_demand_share_methodology_without_rank_output():
    current = evaluation()
    snapshot = evaluation(evaluation_mode="SNAPSHOT")
    assert current["methodology_version"] == snapshot["methodology_version"]
    assert current["technical_threshold_version"] == snapshot["technical_threshold_version"]
    assert "production_rank" not in current
    assert "relative_rank_score" not in current
    assert "scan_conviction" not in current
