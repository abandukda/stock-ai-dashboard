import json

from engines.deep_research_evidence import normalize_governed_news_article, normalize_news_articles
from services import deep_research_cache as cache
from services.evidence_lineage_governance import disallowed_lineage_paths


def _article(**overrides):
    value = {
        "title": "Acme reports a material contract",
        "source": "Licensed Wire",
        "published_at": "2026-09-15T12:00:00Z",
        "url": "https://wire.example/acme-contract",
    }
    value.update(overrides)
    return value


def test_newsapi_transport_with_yahoo_publisher_is_omitted():
    assert normalize_governed_news_article(
        _article(source="Yahoo Entertainment"), symbol="ACME", transport_provider="NEWSAPI",
    ) is None


def test_finnhub_transport_with_yahoo_publisher_is_omitted():
    assert normalize_governed_news_article(
        _article(source="Yahoo"), symbol="ACME", transport_provider="FINNHUB",
    ) is None


def test_prohibited_direct_and_referral_urls_are_omitted():
    assert normalize_governed_news_article(
        _article(url="https://finance.yahoo.com/story"), symbol="ACME", transport_provider="NEWSAPI",
    ) is None
    assert normalize_governed_news_article(
        _article(url="https://wire.example/out?url=https%3A%2F%2Fconsent.yahoo.com%2Fv2"),
        symbol="ACME", transport_provider="FINNHUB",
    ) is None
    assert normalize_governed_news_article(
        _article(url="https://marketbeat.example/story?utm_source=yahoofinance"),
        symbol="ACME", transport_provider="NEWSAPI",
    ) is None


def test_provider_publisher_and_evidence_lineage_remain_distinct():
    item = normalize_governed_news_article(
        _article(), symbol="ACME", transport_provider="Finnhub company news",
        captured_at="2026-09-15T12:05:00Z",
    )
    assert item is not None
    assert item["transport_provider"] == item["provider"] == "FINNHUB"
    assert item["article_publisher"] == "Licensed Wire"
    assert item["article_timestamp"] == "2026-09-15T12:00:00Z"
    assert item["capture_timestamp"] == "2026-09-15T12:05:00Z"
    assert item["evidence_id"].startswith("NEWS-")
    assert disallowed_lineage_paths(item) == []


def test_post_filter_empty_news_is_clean_optional_unavailability():
    decision = {"guidance": {"state": "BUY_NOW"}, "decision_digest": "fixed"}
    result = normalize_news_articles(
        [_article(source="Yahoo")], symbol="ACME", transport_provider="NEWSAPI",
    )
    assert result == []
    assert decision == {"guidance": {"state": "BUY_NOW"}, "decision_digest": "fixed"}


def test_legacy_news_cache_schema_is_not_reused(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    legacy = {
        "schema_version": cache.CACHE_SCHEMA_VERSION,
        "symbol": "ACME", "family": "NEWS", "fetched_epoch": 1,
        "fetched_at": "1970-01-01T00:00:01+00:00", "source_version": "legacy",
        "payload": {"recent_headlines": [_article(source="Yahoo")]},
    }
    (tmp_path / "ACME__NEWS.json").write_text(json.dumps(legacy), encoding="utf-8")
    payload, freshness = cache.cached_evidence(
        "ACME", "news", 3600, lambda: {}, now_epoch=2, source_version="v2",
    )
    assert payload == {}
    assert freshness["status"] == "TEMPORARILY_UNAVAILABLE"


def test_projected_pool_contains_zero_prohibited_contextual_lineage():
    rows = [
        normalize_governed_news_article(_article(title=f"Story {index}"), symbol=f"T{index}", transport_provider="NEWSAPI")
        for index in range(3)
    ]
    assert all(row is not None and disallowed_lineage_paths(row) == [] for row in rows)
