from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from engines.market_today import build_market_today, normalize_major_market_news
from services.home_market_news import fetch_major_market_news
from engines.home_guidance_story_v1 import (
    build_home_action_count_contract,
    build_homepage_promotion_metrics,
    select_home_featured_cards,
)
from engines.home_guidance_story_v1 import build_home_guidance_story
from services.home_promotion_policy import VERSION, classify_homepage_promotion
from pathlib import Path
from streamlit.testing.v1 import AppTest


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


def _canonical_row(ticker, state):
    return {"ticker": ticker, "canonical_investment_evaluation": {"guidance": {"state": state}}}


def _published_card(ticker, state, *, eligible=True):
    return {"ticker": ticker, "guidance": state, "homepage_promotion_eligibility": {"eligible": eligible}}


def test_action_count_contract_uses_exact_rendered_collection_and_keeps_real_zeroes():
    rows = [_canonical_row("A", "BUY_NOW"), _canonical_row("B", "ACCUMULATE"),
            _canonical_row("C", "WAIT_FOR_ENTRY"), _canonical_row("D", "WAIT_FOR_CONFIRMATION")]
    published = [_published_card("A", "BUY_NOW"), _published_card("B", "ACCUMULATE"),
                 _published_card("C", "WAIT_FOR_ENTRY")]
    featured = select_home_featured_cards(published, limit=2)
    contract = build_home_action_count_contract(
        rows, published, featured, manifest={"customer_publication_count": 3},
    )
    assert contract["customer_published_action_counts"]["WAIT_FOR_CONFIRMATION"] == 0
    assert contract["home_featured_action_counts"] == {
        "BUY_NOW": 1, "ACCUMULATE": 1, "WAIT_FOR_ENTRY": 0,
        "WAIT_FOR_CONFIRMATION": 0, "DATA_LIMITED": 0, "AVOID": 0,
    }
    assert contract["withheld_action_counts"]["WAIT_FOR_CONFIRMATION"] == 1
    assert contract["home_surface_deferred_action_counts"]["WAIT_FOR_ENTRY"] == 1
    assert contract["counter_sum"] == contract["rendered_card_count"] == 2
    assert contract["reconciled"] is True


def test_action_count_contract_separates_withheld_and_promotion_filtered_records():
    rows = [_canonical_row("A", "BUY_NOW"), _canonical_row("B", "BUY_NOW"), _canonical_row("C", "DATA_LIMITED")]
    published = [_published_card("A", "BUY_NOW", eligible=False)]
    contract = build_home_action_count_contract(rows, published, select_home_featured_cards(published))
    assert contract["withheld_action_counts"]["BUY_NOW"] == 1
    assert contract["promotion_filtered_action_counts"]["BUY_NOW"] == 1
    assert contract["home_featured_action_counts"]["BUY_NOW"] == 0
    assert contract["home_featured_action_counts"]["DATA_LIMITED"] == 0
    assert contract["zero_reasons"]["BUY_NOW"] == "PUBLISHED_CANDIDATES_PROMOTION_FILTERED"
    assert contract["zero_reasons"]["DATA_LIMITED"] == "CANONICAL_CANDIDATES_ALL_WITHHELD"


def test_action_count_contract_fails_stale_generation_and_manifest_count():
    rows = [_canonical_row("A", "ACCUMULATE")]
    cards = [_published_card("A", "ACCUMULATE")]
    contract = build_home_action_count_contract(
        rows, cards, cards,
        manifest={"customer_publication_count": 2, "home_counter_artifact_sha256": "expected"},
        artifact_sha256="actual",
    )
    assert contract["reconciled"] is False
    assert "CUSTOMER_PUBLICATION_COUNT_MISMATCH" in contract["failure_reason"]
    assert "PRODUCTION_GENERATION_MISMATCH" in contract["failure_reason"]


def test_current_production_home_counters_reconcile_to_rendered_cards():
    scan_path = Path("market_full_scan.json")
    rows = json.loads(scan_path.read_text())
    manifest = json.loads(Path("publication_manifest.json").read_text())
    story = build_home_guidance_story(
        rows, json.loads(Path("recovery_scan.json").read_text()),
        production_manifest=manifest,
        production_artifact_sha256=hashlib.sha256(scan_path.read_bytes()).hexdigest(),
    )
    contract = story["home_action_count_contract"]
    assert contract["customer_publication_count"] == manifest["customer_publication_count"] == 31
    assert contract["customer_published_action_counts"]["ACCUMULATE"] == 29
    assert contract["customer_published_action_counts"]["WAIT_FOR_ENTRY"] == 2
    assert contract["home_featured_action_counts"]["ACCUMULATE"] == 10
    assert contract["counter_sum"] == len(story["home_featured_cards"]) == 10
    assert contract["reconciled"] is True


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


def test_market_today_preserves_partial_availability():
    tape={"market_data_as_of":"2026-09-10T18:31:00Z","rows":[
        {"symbol":"SPY","label":"S&P 500 · SPY","status":"available","price":674.2,
         "point_change":1.2,"change_pct":.18,"direction":"UP","as_of":"2026-09-10T18:31:00Z","evidence_id":"TD-SPY"},
        {"symbol":"QQQ","label":"Nasdaq 100 · QQQ","status":"unavailable"},
    ]}
    result=build_market_today(tape,now=datetime(2026,9,10,14,31,tzinfo=timezone.utc))
    assert [item["symbol"] for item in result["instruments"]]==["SPY"]
    assert result["status"]=="AVAILABLE"


def test_major_market_news_acquisition_requires_explicit_commercial_entitlement():
    blocked = fetch_major_market_news(
        secrets={"NEWSAPI_KEY": "secret"}, environ={}, now=datetime(2026, 9, 12, tzinfo=timezone.utc),
    )
    assert blocked["records"] == []
    assert blocked["runtime_health"]["failure_reason"] == "COMMERCIAL_DISPLAY_RIGHTS_UNCONFIRMED"


def test_major_market_news_acquisition_persists_safe_lineage_without_secret():
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"articles": [{"title": "Fed holds interest rates steady", "publishedAt": "2026-09-11T18:00:00Z",
                    "source": {"name": "Licensed Wire"}, "url": "https://example.com/fed"}]}
    result = fetch_major_market_news(
        get=lambda *args, **kwargs: Response(), now=datetime(2026, 9, 12, tzinfo=timezone.utc),
        secrets={"NEWSAPI_KEY": "secret", "NEWSAPI_COMMERCIAL_DISPLAY_ALLOWED": "true"}, environ={},
    )
    assert result["runtime_health"]["records_available"] == 1
    assert result["records"][0]["evidence_id"].startswith("NEWSAPI-MARKET-")
    assert result["records"][0]["commercial_display_allowed"] is True
    assert "secret" not in repr(result)


def test_market_today_contract_is_independent_of_stock_certification():
    context=build_market_today({"market_data_as_of":"2026-09-10T18:31:00Z","rows":[
        {"symbol":"SPY","label":"S&P 500 · SPY","status":"available","price":674.2,
         "point_change":1.2,"change_pct":.18,"direction":"UP","as_of":"2026-09-10T18:31:00Z","evidence_id":"TD-SPY"},
    ]})
    withheld={"ticker":"BLOCKED","publication_certification":{"customer_publication_allowed":False}}
    story=build_home_guidance_story([withheld],[],market_today=context)
    assert story["cards"]==[]
    assert story["market_today"]==context
    assert story["market_today"]["non_scoring"] is True


def test_home_acquires_market_today_before_story_and_renderer_has_safe_empty_states():
    app_source=Path("app.py").read_text()
    active=app_source[app_source.rfind("def v810_render_dynamic_home"):]
    assert active.index("fetch_home_market_tape()") < active.index("build_home_guidance_story(")
    renderer=Path("ui/home_guidance_vnext.py").read_text()
    assert "Current market data is temporarily unavailable." in renderer
    assert "No major governed market-moving headlines are available right now." in renderer
    assert 'data-atlas-non-scoring="true"' in renderer


def test_market_today_renderer_has_mobile_overflow_guard():
    renderer=Path("ui/home_guidance_vnext.py").read_text()
    assert "@media(max-width:700px)" in renderer
    assert ".atlas-market-today-grid{grid-template-columns:repeat(2,minmax(0,1fr))}" in renderer


def _render_market_today_app(context):
    source = (
        "from ui.home_guidance_vnext import _render_market_today\n"
        f"_render_market_today({context!r})\n"
    )
    return AppTest.from_string(source, default_timeout=15).run()


def test_streamlit_market_today_renders_available_cards_and_governed_news():
    context={"market_today":{"status":"AVAILABLE","market_session":"OPEN","as_of":"2026-09-10T18:31:00Z",
        "instruments":[{"symbol":"SPY","label":"S&P 500 · SPY","price":674.2,"point_change":1.2,"change_pct":.18}],
        "interpretation":"Supportive context; ratings remain company-specific.","non_scoring":True,
        "major_market_news":[{"headline":"Fed holds rates steady","source":"Wire","published_at":"2026-09-10T18:00:00Z",
            "evidence_id":"NEWS-1","why_it_matters":"Discount rates remain important.","relevance":"FED","non_scoring":True}]}}
    app=_render_market_today_app(context)
    values="\n".join(str(item.value) for item in [*app.markdown,*app.caption])
    assert not app.exception
    assert "Market Today" in values and "SPY" in values and "674.20" in values
    assert "What ATLAS Thinks This Means" in values and "Major Market News" in values
    assert "Fed holds rates steady" in values


def test_streamlit_market_today_renders_explicit_unavailable_and_no_news_states():
    app=_render_market_today_app({"market_today":{"status":"DATA_UNAVAILABLE","market_session":"CLOSED",
        "instruments":[],"major_market_news":[],"non_scoring":True}})
    values="\n".join(str(item.value) for item in [*app.markdown,*app.caption])
    assert not app.exception
    assert "Current market data is temporarily unavailable." in values
    assert "No major governed market-moving headlines are available right now." in values


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
