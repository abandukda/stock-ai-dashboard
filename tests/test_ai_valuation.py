from __future__ import annotations

import copy
import inspect
import json

import pytest

from core.pipeline_v104 import build_v104_pipeline
from engines.ai_valuation import (
    FRAMEWORK_VERSION, INSUFFICIENT_EVIDENCE, MODEL_NOT_APPLICABLE,
    INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE, JUSTIFIED_MULTIPLE_DATA_CONTRACT,
    PROHIBITED_TARGET_FIELDS, RELATIVE_MULTIPLE_DIAGNOSTIC, UNDER_REVIEW, VALIDATION_FAILED,
    assumption_bounds, attach_valuation_comparison, build_ai_valuation,
    build_relative_multiple_diagnostic, determine_eligibility, input_fingerprint,
    initial_synthesis_context, normalize_ai_valuation_inputs, refresh_price_metrics,
)
from engines.ask_atlas_engine import ask_atlas
from services.ai_valuation_synthesis import (
    _prompt, get_ai_valuation_for_research,
)
from ui import home_v104, research_report_v2
import overnight_market_scan


def complete_row(**updates):
    row = {
        "ticker": "TEST", "company": "Test Company", "quote_type": "EQUITY",
        "sector": "Technology", "industry": "Software - Application",
        "price": 100.0, "forward_eps": 5.0, "forward_eps_source": "YAHOO_INFO",
        "forward_pe": 20.0, "revenue_growth": 0.20,
        "revenue_growth_source": "YAHOO_INFO", "revenue_growth_horizon": "PROVIDER_DEFINED",
        "earnings_growth": 0.25, "operating_profit_margin": 0.30,
        "free_cash_flow": 1_000_000_000, "roic": 0.18,
        "total_debt": 2_000_000_000, "cash_and_equivalents": 2_500_000_000,
        "market_cap": 50_000_000_000, "eps_surprise_pct": 5.0,
        "revenue_surprise_pct": 3.0, "latest_earnings_date": "2026-08-01",
    }
    row.update(updates)
    return row


def bounded_synthesis(context):
    bounds = context["assumption_bounds"]
    midpoint = lambda key: (bounds[key]["min"] + bounds[key]["max"]) / 2
    return {
        "bear_pe": midpoint("bear_pe"), "base_pe": midpoint("base_pe"),
        "bull_pe": midpoint("bull_pe"),
        "method_rationale": "Forward earnings are directly supplied and profitability is verified.",
        "supporting_factors": ["Positive FCF", "Positive ROIC"],
        "risks": ["Multiple compression"],
    }


def test_normalizer_is_semantically_isolated_from_every_target_family():
    base = complete_row()
    isolated = normalize_ai_valuation_inputs(base)
    fingerprint = input_fingerprint(isolated)
    for index, field in enumerate(PROHIBITED_TARGET_FIELDS, start=1):
        changed = dict(base); changed[field] = 10_000 + index
        assert normalize_ai_valuation_inputs(changed) == isolated
        assert input_fingerprint(normalize_ai_valuation_inputs(changed)) == fingerprint
    assert not PROHIBITED_TARGET_FIELDS.intersection(isolated)


def test_initial_prompt_is_quant_street_scenario_decision_and_trade_blind():
    inputs = normalize_ai_valuation_inputs(complete_row())
    context = initial_synthesis_context(inputs, assumption_bounds(inputs), {"score": 80, "band": "MODERATE"})
    user_payload = _prompt(context)[1]["content"]
    for field in PROHIBITED_TARGET_FIELDS:
        assert field not in user_payload
    assert "current_price" not in user_payload


def test_rejected_raw_quant_value_never_appears_in_ai_object():
    row = complete_row(atlas_valuation_status="REJECTED_EXTREME_UPSIDE", raw_atlas_fv=9999, raw_fair_value=9999)
    result = build_ai_valuation(row, synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE
    assert "raw_atlas_fv" not in json.dumps(result)
    assert "raw_fair_value" not in json.dumps(result)


def test_deterministic_forward_earnings_method_selection():
    result = determine_eligibility(normalize_ai_valuation_inputs(complete_row()))
    assert result["methods"] == ["FORWARD_EARNINGS_PE"]


@pytest.mark.parametrize("field", [
    "forward_eps", "forward_pe", "revenue_growth", "earnings_growth",
    "operating_profit_margin", "free_cash_flow", "roic", "total_debt",
    "cash_and_equivalents", "market_cap",
])
def test_method_specific_required_inputs_fail_closed(field):
    result = build_ai_valuation(complete_row(**{field: None}), synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == INSUFFICIENT_EVIDENCE
    assert result["ai_base_value"] is None


def test_derived_forward_eps_is_not_eligible():
    result = build_ai_valuation(complete_row(forward_eps_source="DERIVED"), synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == INSUFFICIENT_EVIDENCE


def test_negative_operating_margin_is_not_eligible_for_forward_earnings_pilot():
    result = build_ai_valuation(complete_row(operating_profit_margin=-0.05), synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(("sector", "industry"), [
    ("Energy", "Oil & Gas E&P"), ("Basic Materials", "Gold"),
    ("Industrials", "Copper Mining"),
])
def test_cyclicals_fail_closed_without_normalized_history(sector, industry):
    result = build_ai_valuation(complete_row(sector=sector, industry=industry), synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == INSUFFICIENT_EVIDENCE
    assert any("cyclical" in gap.lower() for gap in result["ai_evidence_gaps"])


def test_extreme_cycle_observation_fails_closed_without_history():
    result = build_ai_valuation(complete_row(revenue_growth=3.5, earnings_growth=13.0), synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == INSUFFICIENT_EVIDENCE


def test_etf_is_model_not_applicable():
    result = build_ai_valuation(complete_row(quote_type="ETF"), synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == MODEL_NOT_APPLICABLE


def test_structured_customer_result_is_hard_gated_without_numbers():
    result = build_ai_valuation(complete_row(), synthesizer=bounded_synthesis)
    assert result["ai_valuation_status"] == INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE
    assert result["ai_validation_status"] == "NOT_PUBLISHED"
    assert result["ai_evidence_completeness_pct"] == 100.0
    assert result["ai_provenance"]["existing_target_families_excluded"] is True
    for key in ("ai_bear_value", "ai_base_value", "ai_bull_value", "ai_valuation_low", "ai_valuation_high", "ai_base_upside_pct"):
        assert result[key] is None


def test_relative_multiple_diagnostic_is_internal_and_recomputed():
    result = build_relative_multiple_diagnostic(complete_row(), synthesizer=bounded_synthesis)
    assert result["diagnostic_type"] == RELATIVE_MULTIPLE_DIAGNOSTIC
    assert result["diagnostic_status"] == "VALID"
    assert 0 < result["bear_value"] <= result["base_value"] <= result["bull_value"]
    assert result["base_value"] == 100.0
    assert not any(key.startswith("ai_") for key in result)


def test_out_of_bounds_or_inverted_output_fails_validation():
    def invalid(context):
        return {"bear_pe": 1000, "base_pe": 1, "bull_pe": 0.5}
    result = build_relative_multiple_diagnostic(complete_row(), synthesizer=invalid)
    assert result["diagnostic_status"] == VALIDATION_FAILED


def test_incomplete_structured_output_fails_closed():
    result = build_relative_multiple_diagnostic(complete_row(), synthesizer=lambda context: {"base_pe": 20})
    assert result["diagnostic_status"] == VALIDATION_FAILED


def test_llm_failure_means_under_review_without_fabricated_value():
    result = build_relative_multiple_diagnostic(complete_row(), synthesizer=lambda context: None)
    assert result["diagnostic_status"] == UNDER_REVIEW
    customer = build_ai_valuation(complete_row(), synthesizer=lambda context: None)
    assert customer["ai_valuation_status"] == INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE
    assert customer["ai_base_value"] is None


def test_publication_gate_prevents_synthesizer_call():
    calls = []
    result = build_ai_valuation(complete_row(), synthesizer=lambda context: calls.append(context))
    assert result["ai_valuation_status"] == INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE
    assert calls == []


def test_future_independent_value_price_refresh_changes_only_upside():
    future = {"ai_bear_value": 80.0, "ai_base_value": 100.0, "ai_bull_value": 120.0}
    low = refresh_price_metrics(future, 80.0)
    high = refresh_price_metrics(future, 125.0)
    assert (low["ai_bear_value"], low["ai_base_value"], low["ai_bull_value"]) == (80.0, 100.0, 120.0)
    assert (high["ai_bear_value"], high["ai_base_value"], high["ai_bull_value"]) == (80.0, 100.0, 120.0)
    assert low["ai_base_upside_pct"] != high["ai_base_upside_pct"]


def test_justified_multiple_contract_is_point_in_time_and_complete():
    assert JUSTIFIED_MULTIPLE_DATA_CONTRACT["point_in_time_required"] is True
    domains = JUSTIFIED_MULTIPLE_DATA_CONTRACT["required_domains"]
    assert "historical_forward_pe" in domains["market"]
    assert "forward_eps_vintage" in domains["estimates"]
    assert "comparable_company_forward_pe" in domains["relative_value"]
    assert "current fundamentals may not be backfilled" in JUSTIFIED_MULTIPLE_DATA_CONTRACT["lookahead_policy"]


def test_deterministic_confidence_cannot_be_supplied_by_synthesizer():
    def malicious(context):
        output = bounded_synthesis(context); output["confidence"] = 100
        return output
    normal = build_relative_multiple_diagnostic(complete_row(), synthesizer=bounded_synthesis)
    malicious_result = build_relative_multiple_diagnostic(complete_row(), synthesizer=malicious)
    assert malicious_result["confidence"] == normal["confidence"]


def test_publication_gate_bypasses_provider_and_cache(tmp_path):
    calls = []
    def synth(context):
        calls.append(context); return bounded_synthesis(context)
    first = get_ai_valuation_for_research("TEST", complete_row(price=100), cache_dir=tmp_path, synthesizer=synth)
    second = get_ai_valuation_for_research("TEST", complete_row(price=120), cache_dir=tmp_path, synthesizer=synth)
    assert first["ai_base_value"] is None and second["ai_base_value"] is None
    assert first["ai_cache_status"] == "BYPASSED_PUBLICATION_GATE"
    assert first["ai_provider_call_count"] == 0 and second["ai_provider_call_count"] == 0
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_publication_gate_writes_no_framework_cache_file(tmp_path):
    get_ai_valuation_for_research("TEST", complete_row(), cache_dir=tmp_path, synthesizer=bounded_synthesis)
    assert list(tmp_path.iterdir()) == []


def test_model_snapshot_change_invalidates_cache(monkeypatch, tmp_path):
    calls = []
    def synth(context): calls.append(context); return bounded_synthesis(context)
    monkeypatch.setenv("ATLAS_AI_VALUATION_MODEL", "model-a")
    get_ai_valuation_for_research("TEST", complete_row(), cache_dir=tmp_path, synthesizer=synth)
    monkeypatch.setenv("ATLAS_AI_VALUATION_MODEL", "model-b")
    get_ai_valuation_for_research("TEST", complete_row(), cache_dir=tmp_path, synthesizer=synth)
    assert len(calls) == 0


def test_three_way_comparison_occurs_only_after_publication():
    row = complete_row(atlas_fair_value=102, analyst_target_mean=104)
    unpublished = attach_valuation_comparison(build_ai_valuation(row), row)
    assert unpublished["valuation_relationship"] == "AI_UNAVAILABLE_QUANT_STREET_AVAILABLE"
    gated = attach_valuation_comparison(build_ai_valuation(row, synthesizer=bounded_synthesis), row)
    assert gated["valuation_relationship"] == "AI_UNAVAILABLE_QUANT_STREET_AVAILABLE"


def test_nvda_and_avgo_style_fixtures_are_eligible_without_hardcoding_tickers():
    for ticker in ("NVDA", "AVGO"):
        result = build_ai_valuation(complete_row(ticker=ticker, industry="Semiconductors"), synthesizer=bounded_synthesis)
        assert result["ai_valuation_status"] == INSUFFICIENT_JUSTIFIED_MULTIPLE_EVIDENCE


@pytest.mark.parametrize("row", [
    complete_row(ticker="CIEN", operating_profit_margin=None, free_cash_flow=None),
    complete_row(ticker="BABA", operating_profit_margin=None, roic=None),
    complete_row(ticker="MU", revenue_growth=3.457, earnings_growth=13.685, industry="Semiconductors"),
    complete_row(ticker="WPM", sector="Basic Materials", industry="Gold"),
])
def test_partial_and_cyclical_examples_do_not_publish(row):
    assert build_ai_valuation(row, synthesizer=bounded_synthesis)["ai_valuation_status"] == INSUFFICIENT_EVIDENCE


def test_ask_atlas_explains_ai_valuation_without_declaring_one_model_correct():
    ai = attach_valuation_comparison(build_ai_valuation(complete_row(), synthesizer=bounded_synthesis), complete_row())
    report = {"ticker": "TEST", "ai_valuation": ai, "sections": {}}
    answer = ask_atlas("How was the AI valuation calculated?", report)
    assert answer["mode"] == "deterministic_ai_valuation_grounding"
    assert "will not use today's market multiple" in answer["answer"]
    assert "$100" not in answer["answer"]


def test_ask_atlas_does_not_quote_midpoint_artifact_as_nvda_value():
    report = {"ticker": "NVDA", "ai_valuation": build_ai_valuation(complete_row(ticker="NVDA")), "sections": {}}
    answer = ask_atlas("Does the AI think NVDA is worth $225?", report)
    assert answer["mode"] == "deterministic_ai_valuation_grounding"
    assert "$225" not in answer["answer"]
    assert "not yet sufficiently calibrated" in answer["answer"]


def test_full_research_only_with_zero_scanner_and_home_calls():
    assert "get_ai_valuation_for_research" in inspect.getsource(research_report_v2._load_ai_valuation)
    assert "_load_ai_valuation" in inspect.getsource(research_report_v2.render_atlas_research_v2)
    assert "ai_valuation_synthesis" not in inspect.getsource(overnight_market_scan)
    assert "ai_valuation_synthesis" not in inspect.getsource(home_v104)
    renderer = inspect.getsource(research_report_v2._render_hybrid_valuation)
    assert "Atlas Quant Fair Value" in renderer
    assert "ATLAS AI Valuation" in renderer
    assert "AI Base Value" in renderer
    assert "Valuation Agreement" in renderer


def test_ai_valuation_failure_cannot_break_full_research(monkeypatch):
    monkeypatch.setattr(research_report_v2, "get_ai_valuation_for_research", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    result = research_report_v2._load_ai_valuation("TEST", complete_row())
    assert result["ai_valuation_status"] == UNDER_REVIEW
    assert result["ai_base_value"] is None


def test_current_150_rows_preserve_all_investment_outputs():
    rows = json.loads(open("market_full_scan.json", encoding="utf-8").read())
    before_rows = copy.deepcopy(rows)
    before = build_v104_pipeline(copy.deepcopy(rows))
    for row in rows:
        build_ai_valuation(row)
    after = build_v104_pipeline(copy.deepcopy(rows))
    assert rows == before_rows
    protected = (
        "ticker", "overall_rank", "opportunity_score", "confidence_pct",
        "committee_verdict", "validated_fair_value", "decision_valuation_target",
        "decision_expected_return_pct", "position_size_range",
    )
    project = lambda model: [{key: item.get(key) for key in protected} for item in model["ranked_candidates"]]
    assert project(before) == project(after)
    for old, new in zip(before["ranked_candidates"], after["ranked_candidates"]):
        for key in ("trade_target_1", "trade_target_2", "stop_loss", "preferred_entry_low", "preferred_entry_high"):
            assert (old.get("raw") or {}).get(key) == (new.get("raw") or {}).get(key)
