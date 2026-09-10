from copy import deepcopy

from engines.home_guidance_story_v1 import build_home_guidance_story
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from services.context_evidence import (
    DISPLAY_ALLOWED, context_coverage, enrich_published_context, materialize_context_evidence,
    normalize_insiders, normalize_institutions, normalize_news, unavailable_congressional,
)


def family(payload, evidence="E-1", allowed=True):
    return {"status": "AVAILABLE", "provider": "TWELVE_DATA", "payload": payload,
            "evidence_id": evidence, "observed_at": "2026-09-10T12:00:00Z",
            "commercial_display_allowed": allowed}


def canonical_row():
    return {"ticker": "ABC", "latest_revenue": 100, "forward_eps": 4,
            "professional_evidence_as_of": "2026-09-10T12:00:00Z",
            "professional_evidence_lineage": {"fields": {"latest_revenue": {"evidence_id": "FIN-1"}}},
            "canonical_investment_evaluation": {"guidance": {"state": "BUY_NOW"},
                "atlas_valuation": {"professional_valuation_v2": {"atlas_base_fair_value": 25}},
                "technical_quality": {"score": 80}, "fundamental_quality": {"score": 80},
                "valuation_quality": {"score": 80}, "risk_quality": {"score": 80},
                "entry_quality": {"score": 80}, "volume_quality": {"score": 80}}}


def test_context_never_mutates_decision_valuation_or_pillars():
    row = canonical_row()
    before = deepcopy(row["canonical_investment_evaluation"])
    result = materialize_context_evidence(row, {"press_releases": family({"press_releases": []})})
    assert result["canonical_investment_evaluation"] == before


def test_post_selection_context_acquisition_preserves_canonical_evaluation(monkeypatch):
    row = canonical_row()
    before = deepcopy(row["canonical_investment_evaluation"])
    def acquire(symbols, **kwargs):
        return {"status": "AVAILABLE", "provider_calls": 3, "dossiers": {"ABC": {"families": {
            "press_releases": family({"press_releases": []}),
            "insider_transactions": family({"insider_transactions": []}),
            "institutional_holders": family({"institutional_holders": []}),
        }}}}
    monkeypatch.setattr("services.twelve_data_trial_intelligence.acquire_twelve_trial_dossiers", acquire)
    rows, telemetry = enrich_published_context([row])
    assert telemetry["provider_calls"] == 3
    assert rows[0]["canonical_investment_evaluation"] == before


def test_missing_context_is_explicit_not_neutral():
    result = materialize_context_evidence(canonical_row(), {})
    assert result["news_context"]["status"] == "NEWS_DATA_UNAVAILABLE"
    assert result["insider_context"]["status"] == "INSIDER_DATA_UNAVAILABLE"
    assert result["congressional_context"]["status"] == "CONGRESSIONAL_DATA_UNAVAILABLE"


def test_news_requires_source_date_relevance_dedupes_spam_and_respects_rights():
    rows = [
        {"ticker": "ABC", "headline": "ABC wins contract", "source": "Wire", "date": "2026-09-09"},
        {"ticker": "ABC", "headline": "ABC wins contract", "source": "Wire", "date": "2026-09-09"},
        {"ticker": "XYZ", "headline": "Other", "source": "Wire", "date": "2026-09-09"},
        {"ticker": "ABC", "headline": "Shareholder class action alert", "source": "Law", "date": "2026-09-09"},
        {"ticker": "ABC", "headline": "Missing date", "source": "Wire"},
    ]
    result = normalize_news("ABC", family({"press_releases": rows}))
    assert result["status"] == "NEWS_PARTIAL" and len(result["records"]) == 1
    restricted = normalize_news("ABC", family({"press_releases": rows}, allowed=False))
    assert restricted["records"] == () and restricted["commercial_display_status"] != DISPLAY_ALLOWED


def test_insider_direction_and_institutional_period_are_preserved():
    insiders = normalize_insiders("ABC", family({"insider_transactions": [
        {"name": "A", "transaction_type": "Purchase", "transaction_date": "2026-09-01"},
        {"name": "B", "transaction_type": "Sale", "transaction_date": "2026-09-02"},
    ]}))
    assert [x["direction"] for x in insiders["records"]] == ["BUY", "SELL"]
    holders = normalize_institutions("ABC", family({"institutional_holders": [{"name": "Fund", "shares": 10, "report_date": "2026-Q2"}]}))
    assert holders["records"][0]["filing_period"] == "2026-Q2"


def test_congressional_is_delayed_context_only_and_never_fakes_amount():
    result = unavailable_congressional()
    assert result["delayed_disclosure"] is True and result["non_scoring"] is True
    assert result["records"] == ()


def test_financial_detail_references_canonical_and_coverage_is_machine_readable():
    enriched = materialize_context_evidence(canonical_row(), {})
    detail = enriched["financial_detail_context"]
    assert detail["fields"]["revenue"]["value"] == 100
    assert detail["fields"]["revenue"]["canonical_field"] == "latest_revenue"
    coverage = context_coverage([enriched])
    assert coverage["population"] == 1
    assert coverage["financial_detail_coverage_pct"]["forward_eps"] == 100


def test_home_uses_same_normalized_news_facts(monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_MODE", "INTERNAL_TRIAL")
    row = canonical_row()
    row.update({"rank": 1, "company": "ABC Inc", "current_price": 10,
                "news_context": normalize_news("ABC", family({"press_releases": [{"ticker": "ABC", "headline": "ABC wins contract", "source": "Wire", "date": "2026-09-09"}]}))})
    card = build_home_guidance_story([row], {})["cards"][0]
    assert card["recent_catalysts"][0]["headline"] == row["news_context"]["records"][0]["headline"]
    assert card["context_evidence"]["normalized"]["news_context"] == row["news_context"]


def test_research_passes_same_context_contract_through():
    row = materialize_context_evidence(canonical_row(), {})
    report = build_atlas_research_v2(row)
    assert report["context_evidence"]["insider_context"] == row["insider_context"]
    assert report["context_evidence"]["financial_detail_context"] == row["financial_detail_context"]
