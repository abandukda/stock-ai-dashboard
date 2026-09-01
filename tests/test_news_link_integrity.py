from engines.market_moving_news import build_market_moving_news
from engines.news_link_integrity import (
    EXACT_ARTICLE, INVALID, MISSING, PUBLISHER_ONLY,
    news_source_presentation, normalize_news_link,
)
from engines.research_enrichment_v105 import accepted_company_news


def test_exact_article_url_is_preserved_and_gets_verified_cta():
    result = normalize_news_link({"url": "https://publisher.test/markets/nvda-quarter"}, publisher_name="Publisher")
    assert result["article_url_status"] == EXACT_ARTICLE
    assert result["article_url"] == "https://publisher.test/markets/nvda-quarter"
    assert news_source_presentation(result)["label"] == "Open verified source"


def test_direct_source_url_is_validated_as_article_not_collapsed_into_publisher():
    result = normalize_news_link({"source_url": "https://wire.test/company/nvda-results"}, publisher_name="Wire")
    assert result["article_url_status"] == EXACT_ARTICLE
    assert result["article_url"] == "https://wire.test/company/nvda-results"


def test_publisher_homepage_is_not_an_article_cta():
    result = normalize_news_link({"url": "https://publisher.test/"}, publisher_name="Publisher")
    assert result["article_url_status"] == PUBLISHER_ONLY
    assert result["article_url"] is None
    assert news_source_presentation({**result, "publisher": "Publisher"})["href"] is None


def test_biztoc_redirect_landing_is_not_verified_article():
    result = normalize_news_link({"url": "https://biztoc.com/x/3339b19a9100848c"}, publisher_name="Biztoc")
    assert result["article_url_status"] == PUBLISHER_ONLY
    assert result["article_url"] is None


def test_finnhub_api_and_generic_search_or_category_are_not_exact_articles():
    for url in (
        "https://finnhub.io/api/news?id=abc123",
        "https://publisher.test/search?q=nvda",
        "https://publisher.test/category/markets",
    ):
        result = normalize_news_link({"url": url}, publisher_name="Publisher")
        assert result["article_url_status"] == PUBLISHER_ONLY
        assert result["article_url"] is None


def test_explicit_exact_aggregator_article_url_is_accepted():
    result = normalize_news_link({"article_url": "https://biztoc.com/articles/nvidia-september-history"}, publisher_name="Biztoc")
    assert result["article_url_status"] == EXACT_ARTICLE


def test_missing_and_invalid_urls_fail_closed():
    assert normalize_news_link({}, publisher_name="Wire")["article_url_status"] == MISSING
    assert normalize_news_link({"url": "javascript:alert(1)"}, publisher_name="Wire")["article_url_status"] == INVALID


def test_article_and_publisher_identity_survive_research_normalization():
    item = accepted_company_news(
        {"ticker": "NVDA", "company": "Nvidia Corporation"},
        [{
            "headline": "Nvidia reports a verified company update",
            "publisher": "Reuters",
            "date": "2026-08-31T12:00:00Z",
            "article_url": "https://reuters.test/technology/nvidia-update",
            "evidence_id": "news:nvda:1",
            "sentiment": "Positive",
        }],
    )[0]
    assert item["publisher_name"] == "Reuters"
    assert item["publisher_domain"] == "reuters.test"
    assert item["article_url_status"] == EXACT_ARTICLE
    assert item["article_url"] == item["url"]
    assert item["evidence_id"] == "news:nvda:1"
    assert item["sentiment"] == "Positive"


def test_no_url_is_fabricated_from_headline():
    result = normalize_news_link({"headline": "Publisher reports an update"}, publisher_name="Publisher")
    assert result["article_url"] is None


def test_market_news_keeps_story_and_scoring_when_link_is_publisher_only():
    result = build_market_moving_news([{
        "headline": "Fed rate decision shifts risk pricing",
        "source": "Wire",
        "timestamp": "2026-08-31T14:00:00Z",
        "url": "https://wire.test/",
        "affected_markets": ["US equities"],
    }])
    story = result["stories"][0]
    assert story["impact"] == "HIGH"
    assert story["article_url_status"] == PUBLISHER_ONLY
    assert story["url"] is None
