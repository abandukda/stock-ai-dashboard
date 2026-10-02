from pathlib import Path

from services.exact_candidate_research import (
    CERTIFIED_IMMEDIATE,
    CERTIFIED_RECORD_MISSING,
    LIVE_RESEARCH,
    PUBLISHED_RESEARCH_COMPLETE,
    clear_persisted_certified_research,
    persist_certified_research,
    persisted_certified_research,
    research_submission_plan,
)


NVDA = {
    "ticker": "NVDA",
    "canonical_investment_evaluation": {
        "guidance": {"state": "BUY_NOW"},
        "atlas_valuation": {"fair_value": 338.82},
        "certified_customer_evaluation": {
            "decision": {"action": "BUY_NOW", "opportunity": 86.68, "decision_confidence": 88.54}
        },
    },
}
REGN = {
    "ticker": "REGN",
    "canonical_investment_evaluation": {
        "guidance": {"state": "WAIT_FOR_CONFIRMATION"},
        "atlas_valuation": {"fair_value": 1514.36},
        "certified_customer_evaluation": {
            "decision": {"action": "WAIT_FOR_CONFIRMATION", "opportunity": 72.98, "decision_confidence": 80.63}
        },
    },
}


def test_exact_candidate_nvda_and_regn_bind_certified_values_without_provider_calls():
    for record in (NVDA, REGN):
        plan = research_submission_plan(record, environ={"ATLAS_EXACT_CANDIDATE_QA": "true"})
        assert plan.mode == CERTIFIED_IMMEDIATE
        assert plan.provider_calls_allowed is False
        assert plan.certified_record == record
    nvda = NVDA["canonical_investment_evaluation"]
    regn = REGN["canonical_investment_evaluation"]
    assert (nvda["guidance"]["state"], nvda["atlas_valuation"]["fair_value"]) == ("BUY_NOW", 338.82)
    assert nvda["certified_customer_evaluation"]["decision"] == {
        "action": "BUY_NOW", "opportunity": 86.68, "decision_confidence": 88.54,
    }
    assert (regn["guidance"]["state"], regn["atlas_valuation"]["fair_value"]) == ("WAIT_FOR_CONFIRMATION", 1514.36)
    assert regn["certified_customer_evaluation"]["decision"] == {
        "action": "WAIT_FOR_CONFIRMATION", "opportunity": 72.98, "decision_confidence": 80.63,
    }


def test_exact_candidate_plan_is_independent_of_slow_or_failed_enrichment():
    calls = []
    plan = research_submission_plan(NVDA, environ={"ATLAS_EXACT_CANDIDATE_QA": "true"})
    if plan.provider_calls_allowed:
        calls.append("live-enrichment")
        raise RuntimeError("optional enrichment failed")
    assert calls == []
    assert plan.certified_record["canonical_investment_evaluation"]["guidance"]["state"] == "BUY_NOW"


def test_exact_candidate_missing_record_fails_closed_without_provider_calls():
    plan = research_submission_plan(None, environ={"ATLAS_EXACT_CANDIDATE_QA": "true"})
    assert plan.mode == CERTIFIED_RECORD_MISSING
    assert plan.certified_record is None
    assert plan.provider_calls_allowed is False


def test_normal_research_remains_live():
    plan = research_submission_plan(NVDA, environ={})
    assert plan.mode == LIVE_RESEARCH
    assert plan.provider_calls_allowed is True
    assert plan.certified_record is None


def test_app_guards_both_optional_enrichment_paths_in_exact_candidate_mode():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "if (submitted or auto_live) and _exact_candidate_bound:" in source
    assert "elif submitted or auto_live:" in source
    assert "if (submitted or auto_live) and not _exact_candidate_bound:" in source
    assert '_research_twelve = {} if _exact_candidate_bound else' in source
    assert '"provider_calls": 0' in source


def test_nvda_and_regn_survive_rerun_with_terminal_action_state():
    for record in (NVDA, REGN):
        session = {}
        ticker = record["ticker"]
        bound = persist_certified_research(session, ticker, record)
        rerun = persisted_certified_research(session, ticker)
        assert bound["lifecycle"] == PUBLISHED_RESEARCH_COMPLETE
        assert rerun["lifecycle"] == PUBLISHED_RESEARCH_COMPLETE
        assert rerun["provider_calls"] == 0
        assert rerun["certified_record"]["canonical_investment_evaluation"]["guidance"]["state"] == (
            record["canonical_investment_evaluation"]["guidance"]["state"]
        )
        assert session["research_status"] == "complete"


def test_switching_exact_candidate_ticker_replaces_persisted_state():
    session = {}
    persist_certified_research(session, "NVDA", NVDA)
    clear_persisted_certified_research(session)
    persist_certified_research(session, "REGN", REGN)
    assert persisted_certified_research(session, "NVDA") is None
    regn = persisted_certified_research(session, "REGN")
    assert regn["ticker"] == "REGN"
    assert regn["certified_record"]["canonical_investment_evaluation"]["guidance"]["state"] == "WAIT_FOR_CONFIRMATION"


def test_missing_or_nonterminal_persisted_state_fails_closed():
    assert persisted_certified_research({}, "NVDA") is None
    session = {"atlas_exact_candidate_research": {"ticker": "NVDA", "certified_record": NVDA, "lifecycle": "loading"}}
    assert persisted_certified_research(session, "NVDA") is None


def test_app_restores_persisted_exact_candidate_before_render():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'persisted_certified_research(st.session_state, ticker)' in source
    assert 'persist_certified_research(' in source
    assert 'data-atlas-lifecycle="PUBLISHED_RESEARCH_COMPLETE"' in source
