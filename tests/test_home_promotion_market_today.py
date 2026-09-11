from copy import deepcopy
from datetime import datetime, timezone

from engines.market_today import build_market_today, normalize_major_market_news
from engines.home_guidance_story_v1 import build_homepage_promotion_metrics
from engines.home_guidance_story_v1 import build_home_guidance_story
from services.home_promotion_policy import VERSION, classify_homepage_promotion


def test_promotion_categories_are_explicit_and_narrow():
    assert classify_homepage_promotion({"industry":"Music"})["eligible"] is False
    assert classify_homepage_promotion({"industry":"Casinos & Gaming"})["eligible"] is False
    assert classify_homepage_promotion({"industry":"Brewers"})["eligible"] is False
    assert classify_homepage_promotion({"industry":"Restaurants","description":"Restaurant technology provider"})["eligible"] is True
    assert classify_homepage_promotion({"industry":"Software","description":"Technology provider serving entertainment companies"})["eligible"] is True


def test_promotion_classification_cannot_mutate_canonical_analysis():
    row={"ticker":"WMG","industry":"Music","canonical_investment_evaluation":{"guidance":{"state":"BUY_NOW"},"opportunity":82,"decision_confidence":91},"atlas_fair_value":40}
    before=deepcopy(row)
    policy=classify_homepage_promotion(row)
    assert policy=={"eligible":False,"reason_codes":("HOME_PROMOTION_EXCLUDED_ENTERTAINMENT",),"categories":("ENTERTAINMENT",),"policy_version":VERSION,"non_scoring":True}
    assert row==before


def test_homepage_counts_distinguish_canonical_actions_from_featured_actions():
    cards = [
        {"guidance":"BUY_NOW","homepage_promotion_eligibility":{"eligible":False}},
        {"guidance":"BUY_NOW","homepage_promotion_eligibility":{"eligible":True}},
        {"guidance":"ACCUMULATE","homepage_promotion_eligibility":{"eligible":False}},
        {"guidance":"ACCUMULATE","homepage_promotion_eligibility":{"eligible":True}},
    ]
    before = deepcopy(cards)
    metrics = build_homepage_promotion_metrics(cards)
    assert metrics == {
        "canonical_buy_now_count":2,
        "homepage_featured_buy_now_count":1,
        "promotion_filtered_buy_now_count":1,
        "canonical_build_count":2,
        "homepage_featured_build_count":1,
        "promotion_filtered_build_count":1,
        "non_scoring":True,
    }
    assert cards == before


def test_market_today_renders_complete_governed_change_contract():
    tape={"market_data_as_of":"2026-09-10T18:31:00Z","rows":[{"symbol":"SPY","label":"S&P 500 · SPY","status":"available","price":674.2,"point_change":-3.84,"change_pct":-.57,"direction":"DOWN","as_of":"2026-09-10T18:31:00Z","evidence_id":"TD-1"}]}
    result=build_market_today(tape,now=datetime(2026,9,10,14,31,tzinfo=timezone.utc))
    assert result["status"]=="AVAILABLE"
    assert result["market_session"]=="OPEN"
    assert result["instruments"][0]["point_change"]==-3.84
    assert result["non_scoring"] is True


def test_market_today_omits_missing_instruments_without_null_tiles():
    result=build_market_today({"rows":[{"symbol":"SPY","status":"unavailable"}]},now=datetime(2026,9,12,tzinfo=timezone.utc))
    assert result["instruments"]==()
    assert result["status"]=="DATA_UNAVAILABLE"
    assert result["market_session"]=="CLOSED"


def test_major_news_requires_lineage_rights_and_relevance_and_deduplicates():
    valid={"headline":"Fed holds interest rates steady","source":"Wire","published_at":"2026-09-10T18:00:00Z","evidence_id":"NEWS-1","commercial_display_allowed":True,"url":"https://example.com/fed"}
    records=[valid,dict(valid),{"headline":"Law firm shareholder alert","source":"Wire","published_at":"2026-09-10T18:00:00Z","evidence_id":"NEWS-2","commercial_display_allowed":True},
             {"headline":"Fed statement","source":"Wire","published_at":"2026-09-10T18:00:00Z","evidence_id":"NEWS-3","commercial_display_allowed":False},
             {"headline":"Minor company update","source":"Wire","published_at":"2026-09-10T18:00:00Z","evidence_id":"NEWS-4","commercial_display_allowed":True}]
    output=normalize_major_market_news(records)
    assert len(output)==1 and output[0]["relevance"]=="FED"
    assert "Federal Reserve policy" in output[0]["why_it_matters"]


def test_research_path_does_not_import_home_promotion_policy():
    from pathlib import Path
    assert "home_promotion_policy" not in Path("ui/research_report_v2.py").read_text()
    assert "home_promotion_policy" not in Path("engines/atlas_research_builder_v2.py").read_text()


def test_certified_buy_now_reads_revalidation_from_canonical_evaluation():
    row = {
        "ticker": "CXT",
        "company": "Crane NXT",
        "publication_certification": {
            "customer_publication_allowed": True,
            "certified_action": "BUY_NOW",
        },
        "canonical_investment_evaluation": {
            "guidance": {"state": "BUY_NOW"},
            "decision_digest": "decision-1",
            "positive_action_revalidation": {
                "status": "BUY_NOW_REVALIDATED",
                "source_decision_digest": "decision-1",
            },
        },
    }

    story = build_home_guidance_story([row], [])

    assert [card["ticker"] for card in story["cards"]] == ["CXT"]
