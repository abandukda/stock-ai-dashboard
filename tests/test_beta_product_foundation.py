from copy import deepcopy
from pathlib import Path

import pytest

from engines.home_guidance_story_v1 import build_home_guidance_story, select_home_featured_cards
from engines.morning_brief_engine import build_certified_morning_brief
from services.product_foundation import (
    MODEL_PORTFOLIO_CONTRACT, PERSONALIZED_ADVICE_CONTRACT,
    VOLUME_OPPORTUNITY_CONTEXT_CONTRACT, build_ai_tutor_evidence_package,
    validate_ai_tutor_response,
)
from services.report_card import append_signal, build_observation, build_signal_record, internal_report
from services.research_package_contract import build_research_package
from services.on_demand_evaluation_service import evaluate_on_demand
from services.vnext_presentation_contract import customer_action_presentation
from services.watchlist_events import derive_watchlist_events, suppress_duplicate_events
from services.transcript_provider import (
    ConfiguredTranscriptProvider, TranscriptLicenseState,
    build_internal_transcript_research_package, build_transcript_derived_insight,
)


def certified_row(ticker="AAA", action="BUY_NOW"):
    evaluation = {
        "guidance": {"state": action, "opportunity_thesis": "Certified cash-flow evidence.", "main_risk": "Demand may weaken."},
        "opportunity": 82, "decision_confidence": 77, "decision_digest": "digest-1",
        "positive_action_revalidation": {"status": "BUY_NOW_REVALIDATED", "source_decision_digest": "digest-1"},
        "atlas_valuation": {"professional_valuation_v2": {"atlas_base_fair_value": 125, "atlas_expected_return": 25}},
    }
    return {
        "ticker": ticker, "current_price": 100, "candidate_digest": "candidate-1", "evidence_ids": ["E1"],
        "canonical_investment_evaluation": evaluation,
        "publication_certification": {"customer_publication_allowed": True, "certified_action": action},
    }


def test_action_presentation_is_decoupled_and_report_card_keeps_canonical_action():
    assert customer_action_presentation("BUY_NOW", terminology="future") == {
        "canonical_action": "BUY_NOW", "label": "Strongest ATLAS Opportunity", "stars": 5, "presentation_only": True,
    }
    payload = signal_payload(); payload["presentation_label_at_issuance"] = "Strongest ATLAS Opportunity"
    signal = build_signal_record(payload, activation_authorized=True)
    assert signal.canonical_action == "BUY_NOW" and signal.presentation_label_at_issuance != signal.canonical_action


def test_home_never_fills_primary_opportunities_with_wait_and_has_honest_empty_state():
    assert select_home_featured_cards([
        {"ticker": "BUILD", "guidance": "ACCUMULATE", "homepage_promotion_eligibility": {"eligible": True}},
        {"ticker": "WAIT", "guidance": "WAIT_FOR_ENTRY", "homepage_promotion_eligibility": {"eligible": True}},
    ]) == []
    story = build_home_guidance_story([], [])
    assert story["home_featured_cards"] == []
    assert story["home_opportunity_empty_state"]["system_failure"] is False


def test_morning_brief_requires_certification_candidate_and_evidence_identity():
    valid = certified_row(); invalid = certified_row("BAD"); invalid["evidence_ids"] = []
    build = certified_row("BUILD", "ACCUMULATE")
    result = build_certified_morning_brief([valid, invalid, build], generated_at="2026-09-24T12:00:00Z")
    assert [item["ticker"] for item in result["strongest_daily_opportunities"]] == ["AAA"]
    assert result["delivery_enabled"] is False and result["financial_truth_source"] == "CERTIFIED_ATLAS_ONLY"
    ungoverned = build_certified_morning_brief([valid], market_context={"summary": "Bullish"}, major_events=[{"headline": "Claim"}])
    assert ungoverned["market_context"]["status"] == "DATA_UNAVAILABLE"
    assert ungoverned["major_context_events"] == []


def test_manual_research_cannot_create_buy_now_and_cannot_cross_ticker_identity():
    missing = {"ticker": "XYZ", "current_display_price": 10}
    assert build_research_package(missing, requested_ticker="XYZ")["canonical_action"] == "RATING_NOT_PUBLISHED"
    assert build_research_package(missing, requested_ticker="XYZ")["manual_search_may_create_buy_now"] is False
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        build_research_package(certified_row(), requested_ticker="OTHER")


def test_on_demand_service_cannot_mint_buy_now(monkeypatch):
    import services.on_demand_evaluation_service as service
    monkeypatch.setattr(service, "build_components", lambda _row: {"fundamentals": {}})
    monkeypatch.setattr(service, "build_canonical_evaluation", lambda *_a, **_k: {
        "evaluated_at": "2026-09-24T20:00:00Z", "guidance": {"state": "BUY_NOW"},
        "atlas_valuation": {}, "decision_digest": "d",
    })
    monkeypatch.setattr("services.canonical_data_validation.validate_valuation", lambda _row: {})
    monkeypatch.setattr("services.positive_action_revalidation.revalidate_buy_now", lambda _evaluation: {"status": "NOT_REVALIDATED"})
    monkeypatch.setattr("services.publication_governance.certify_record", lambda _row: {"customer_publication_allowed": False})
    monkeypatch.setattr("services.certified_customer_evaluation.build_certified_customer_evaluation", lambda _row: {})
    result = evaluate_on_demand({"ticker": "ABC"})
    assert result["guidance"]["state"] == "WAIT_FOR_CONFIRMATION"
    assert result["guidance"]["reason_codes"] == ("ON_DEMAND_BUY_NOW_REQUIRES_DAILY_SELECTION",)


def test_ai_tutor_is_copy_isolated_grounded_and_rejects_decision_or_advice_changes():
    facts = {"canonical_action": "BUILD_A_POSITION", "fair_value": 125, "evidence_ids": ["E1"]}
    before = deepcopy(facts)
    package = build_ai_tutor_evidence_package(ticker="AAA", certified_atlas=facts)
    package["evidence"]["CERTIFIED_ATLAS"]["fair_value"] = 1
    assert facts == before
    rejected = validate_ai_tutor_response(build_ai_tutor_evidence_package(ticker="AAA", certified_atlas=facts), {
        "canonical_action": "BUY_NOW", "fair_value": 150, "evidence_ids": ["FAKE"], "personalized_allocation": "$5,000",
    })
    assert set(rejected["failures"]) == {"CANONICAL_ACTION_CONTRADICTION", "FAIR_VALUE_CONTRADICTION", "UNGROUNDED_EVIDENCE_ID", "PERSONALIZED_ADVICE_PROHIBITED"}


def test_watchlist_events_ignore_price_noise_and_dedupe_deterministically():
    previous = {"canonical_action": "BUILD_A_POSITION", "fair_value": 100, "display_price": 80, "evidence_limited": False}
    current = {**previous, "display_price": 90}
    assert derive_watchlist_events(user_id="u", watchlist_id="w", ticker="AAA", previous=previous, current=current) == []
    current.update({"canonical_action": "BUY_NOW", "fair_value": 112, "candidate_digest": "c", "certification_timestamp": "t", "evidence_ids": ["E1"]})
    events = derive_watchlist_events(user_id="u", watchlist_id="w", ticker="AAA", previous=previous, current=current)
    assert {event["event_type"] for event in events} == {"ACTION_UPGRADE", "FAIR_VALUE_MATERIAL_CHANGE"}
    assert suppress_duplicate_events([*events, *events], []) == events


def signal_payload():
    return {
        "ticker": "AAA", "canonical_action": "BUY_NOW", "presentation_label_at_issuance": "BUY NOW",
        "publication_timestamp": "2026-09-24T20:00:00Z", "executable_reference_timestamp": "2026-09-24T20:00:00Z",
        "certified_reference_price": 100, "fair_value": 110, "expected_potential": 10, "opportunity": 80,
        "decision_confidence": 75, "six_pillars": {"valuation": 80}, "evidence_completeness": 1.0,
        "valuation_methods": ["P_FCF"], "market_regime": "NORMAL", "sector": "Tech", "industry": "Software",
        "methodology_version": "M1", "provider_authority_version": "P1", "candidate_digest": "C1",
        "evidence_ids": ["E1"], "eligibility_state": "LIVE_PROSPECTIVE_SIGNAL",
    }


def test_report_card_requires_activation_is_append_only_and_rejects_hindsight(tmp_path: Path):
    with pytest.raises(PermissionError): build_signal_record(signal_payload())
    signal = build_signal_record(signal_payload(), activation_authorized=True)
    path = tmp_path / "signals.jsonl"
    assert append_signal(path, signal) is True and append_signal(path, signal) is False
    changed = build_signal_record({**signal_payload(), "signal_id": signal.signal_id, "fair_value": 999}, activation_authorized=True)
    with pytest.raises(ValueError, match="IMMUTABLE_SIGNAL_CONFLICT"): append_signal(path, changed)
    bars = [
        {"timestamp": "2026-09-24T19:59:00Z", "close": 500},
        {"timestamp": "2026-09-24T20:00:00Z", "close": 500},
        {"timestamp": "2026-09-25T20:00:00Z", "close": 105},
    ]
    benchmark = [
        {"timestamp": "2026-09-24T20:00:00Z", "close": 100},
        {"timestamp": "2026-09-25T20:00:00Z", "close": 101},
    ]
    observation = build_observation(signal, horizon=1, stock_bars=bars, benchmark_bars=benchmark,
                                    current_canonical_action="BUY_NOW", evidence_provenance={"stock": "S", "benchmark": "B"})
    assert observation.stock_return == pytest.approx(.05) and observation.benchmark_return == pytest.approx(.01)
    assert observation.benchmark == "SPY"
    assert internal_report([observation], [signal])["customer_visible"] is False


def test_model_portfolio_volume_and_personalization_contracts_do_not_invent_methodology():
    assert MODEL_PORTFOLIO_CONTRACT["exit_methodology"] == "NOT_DEFINED"
    assert MODEL_PORTFOLIO_CONTRACT["repeat_consecutive_purchase"] is False
    assert VOLUME_OPPORTUNITY_CONTEXT_CONTRACT["may_create_core_buy_now"] is False
    assert PERSONALIZED_ADVICE_CONTRACT["v1_status"] == "PROHIBITED"


def test_internal_transcript_package_is_rich_but_precommercial_non_scoring_and_prohibited():
    class Response:
        status_code = 200
        def json(self):
            return {"id": "call-1", "content": "Grounded transcript", "prepared_remarks": ["Prepared"], "qa": ["Q&A"]}
    evidence = ConfiguredTranscriptProvider(
        api_key="secret", base_url="https://transcripts.invalid", provider_name="earningscall",
        license_state=TranscriptLicenseState.DEVELOPMENT_PRECOMMERCIAL.value,
        get=lambda *_args, **_kwargs: Response(),
    ).transcript("AAPL", year=2026, quarter=2)
    insight = build_transcript_derived_insight(
        evidence, {"management_summary": "Grounded summary", "key_positives": ["Demand"], "material_risks": ["Margins"]},
        model_provider="TEST", model_version="v1", prompt_version="p1",
    )
    package = build_internal_transcript_research_package(evidence, insight)
    assert package["status"] == "AVAILABLE"
    assert package["license_state"] == "DEVELOPMENT_PRECOMMERCIAL"
    assert package["non_scoring"] is True and package["customer_publication_prohibited"] is True
    assert package["transcript_evidence_id"] == evidence.provenance.raw_evidence_id
