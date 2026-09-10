from copy import deepcopy

from engines.home_guidance_story_v1 import build_home_guidance_story
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from services.context_evidence import (
    DISPLAY_ALLOWED, DISPLAY_ALLOWED_INTERNAL_TRIAL, context_coverage, enrich_published_context, materialize_context_evidence,
    normalize_insiders, normalize_institutions, normalize_news, unavailable_congressional,
    normalize_wall_street,
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


def test_research_renderer_attributes_internal_trial_wall_street_source(monkeypatch):
    from ui import research_report_v2

    calls = []
    class Column:
        def metric(self, label, value): calls.append(("metric", label, value))
    class StreamlitStub:
        def markdown(self, value, **kwargs): calls.append(("markdown", value))
        def caption(self, value): calls.append(("caption", value))
        def write(self, value): calls.append(("write", value))
        def columns(self, count): return [Column() for _ in range(count)]
    monkeypatch.setattr(research_report_v2, "st", StreamlitStub())
    research_report_v2._render_analyst_intelligence({
        "wall_street_mean_target": 125, "wall_street_implied_upside_pct": 25,
        "analyst_coverage": 12, "source_attribution": "Source: Twelve Data",
        "forward_eps": 7.5, "forward_revenue": 1200,
        "atlas_street_relationship": "BROADLY ALIGNED",
    })
    assert ("caption", "Source: Twelve Data") in calls
    assert any(call[:2] == ("metric", "Wall Street Consensus") for call in calls)
    assert any(call[0] == "markdown" and "Forward Revenue" in call[1] for call in calls)


def test_wall_street_contract_is_shared_non_scoring_and_commercially_gated(monkeypatch):
    families = {
        "price_target": family({"price_target": {"average": 25, "median": 24, "low": 18, "high": 30}}),
        "recommendations": family({"rating": 7, "trends": {"current_month": {"strong_buy": 1, "buy": 2, "hold": 1, "sell": 0, "strong_sell": 0}}}),
        "eps_trend": family({"eps_trend": [{"period": "next_year", "current_estimate": 4, "7_days_ago": 3.8, "30_days_ago": 3.5, "90_days_ago": 3.0}]}),
        "analyst_ratings/light": family({"ratings": [{"date": "2026-09-09", "firm": "Firm", "rating_change": "Upgrade", "rating_current": "Buy", "rating_prior": "Hold"}]}),
    }
    allowed = normalize_wall_street({**canonical_row(), "current_price": 10, "analyst_targets_commercial_display_allowed": True}, families)
    assert allowed["status"] == "WALL_STREET_AVAILABLE"
    assert allowed["consensus"]["target_mean"] == 25
    assert allowed["rating_distribution"]["response_count"] == 4
    assert allowed["estimate_context"]["eps_revision_30d"] is not None
    assert allowed["recent_actions"] and allowed["non_scoring"] is True
    monkeypatch.setenv("ATLAS_DATA_MODE", "COMMERCIAL_CUSTOMER")
    restricted = normalize_wall_street({**canonical_row(), "current_price": 10}, families)
    assert restricted["status"] == "WALL_STREET_DISPLAY_RESTRICTED"
    assert restricted["consensus"] == {}


def test_internal_trial_allows_certified_twelve_wall_street_context(monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_MODE", "INTERNAL_TRIAL")
    families = {
        "price_target": family({"price_target": {"average": 25, "median": 24, "low": 18, "high": 30, "number_of_analysts": 4}}, allowed=False),
        "recommendations": family({"rating": 7, "trends": {"current_month": {"strong_buy": 1, "buy": 2, "hold": 1, "sell": 0, "strong_sell": 0}}}, allowed=False),
        "earnings_estimate": family({"earnings_estimate": [{"period": "next_year", "date": "2027", "avg_estimate": 5.25}]}, allowed=False),
        "revenue_estimate": family({"revenue_estimate": [{"period": "next_year", "date": "2027", "avg_estimate": 1200}]}, allowed=False),
        "eps_trend": family({"eps_trend": [{"period": "next_year", "current_estimate": 4, "30_days_ago": 3.5}]}, allowed=False),
    }
    result = normalize_wall_street({**canonical_row(), "current_price": 10}, families)
    assert result["status"] == "WALL_STREET_AVAILABLE"
    assert result["commercial_display_status"] == DISPLAY_ALLOWED_INTERNAL_TRIAL
    assert result["display_scope"] == "INTERNAL_TRIAL"
    assert result["consensus"]["target_mean"] == 25
    assert result["consensus"]["analyst_count"] == 4
    assert result["estimate_context"]["forward_eps"] == 5.25
    assert result["estimate_context"]["forward_revenue"] == 1200
    assert result["attribution"] == "Source: Twelve Data"
    assert result["non_scoring"] is True


def test_internal_trial_partial_and_unavailable_are_semantically_exact(monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_MODE", "INTERNAL_TRIAL")
    source = canonical_row()
    source.pop("forward_eps")
    partial = normalize_wall_street(
        {**source, "current_price": 10},
        {"price_target": family({"price_target": {"average": 25}}, allowed=False)},
    )
    assert partial["status"] == "WALL_STREET_PARTIAL"
    assert partial["consensus"]["target_mean"] == 25
    assert partial["consensus"]["analyst_count"] is None
    unavailable = normalize_wall_street(source, {})
    assert unavailable["status"] == "WALL_STREET_DATA_UNAVAILABLE"
    assert unavailable["commercial_display_status"] != DISPLAY_ALLOWED_INTERNAL_TRIAL
    assert unavailable["attribution"] is None


def test_internal_trial_wall_street_context_cannot_change_canonical_outputs(monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_MODE", "INTERNAL_TRIAL")
    row = canonical_row()
    before = deepcopy(row["canonical_investment_evaluation"])
    normalize_wall_street(
        {**row, "current_price": 10},
        {"price_target": family({"price_target": {"average": 25}}, allowed=False)},
    )
    assert row["canonical_investment_evaluation"] == before


def test_internal_trial_does_not_authorize_non_twelve_context(monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_MODE", "INTERNAL_TRIAL")
    other = family({"price_target": {"average": 25}}, allowed=False)
    other["provider"] = "OTHER_PROVIDER"
    result = normalize_wall_street(
        {**canonical_row(), "current_price": 10}, {"price_target": other},
    )
    assert result["status"] == "WALL_STREET_DISPLAY_RESTRICTED"
    assert result["commercial_display_status"] != DISPLAY_ALLOWED_INTERNAL_TRIAL
    assert result["consensus"] == {}
