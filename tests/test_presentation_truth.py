"""Synthetic NOT PRODUCTION fixtures for provider-free presentation truth."""

from services.presentation_truth import (
    market_view_disclosure, research_field_disclosure, summary_disclosure,
)


def test_summary_distinguishes_generated_deterministic_and_unavailable():
    generated = summary_disclosure({"text": "Synthetic explanation.", "source": "LLM_VALIDATED", "accepted": True})
    fallback = summary_disclosure({"text": "Synthetic fallback.", "source": "DETERMINISTIC_FALLBACK", "accepted": False})
    unknown = summary_disclosure({"text": "Fixture text.", "source": "TEST_FIXTURE"})
    assert generated["state"] == "GENERATED_VALIDATED"
    assert fallback["state"] == "DETERMINISTIC" and "External AI was not used" in fallback["detail"]
    assert unknown["state"] == "UNAVAILABLE"


def test_market_view_never_upgrades_empty_stale_or_partial_evidence():
    assert market_view_disclosure({})["state"] == "UNAVAILABLE"
    stale = market_view_disclosure({"status": "LAST_KNOWN", "instruments": [{"symbol": "TEST"}]})
    partial = market_view_disclosure({"status": "UNKNOWN", "major_market_news": [{"headline": "Synthetic"}]})
    valid = market_view_disclosure({"status": "AVAILABLE", "instruments": [{"symbol": "TEST"}], "source": "SYNTHETIC_NOT_PRODUCTION"})
    assert stale["state"] == "STALE"
    assert partial["state"] == "PARTIAL"
    assert valid == {"state": "AVAILABLE", "label": "Verified market context", "source": "SYNTHETIC_NOT_PRODUCTION", "as_of": "Timestamp unavailable"}


def test_research_field_preserves_provenance_and_staleness():
    stale = research_field_disclosure({"status": "AVAILABLE", "provenance": {"source": "SYNTHETIC_NOT_PRODUCTION", "as_of": "2020-01-01", "freshness": "STALE"}})
    missing = research_field_disclosure({"status": "UNAVAILABLE"})
    partial = research_field_disclosure({"semantic_status": "PARTIAL", "provenance": {"provider": "SYNTHETIC_NOT_PRODUCTION"}})
    assert stale == {"availability": "STALE", "label": "Stale evidence", "source": "SYNTHETIC_NOT_PRODUCTION", "as_of": "2020-01-01"}
    assert missing["availability"] == "UNAVAILABLE"
    assert partial["availability"] == "PARTIAL"


def test_contracts_are_pure_across_repeated_no_network_calls():
    fixture = {"status": "AVAILABLE", "instruments": [{"symbol": "TEST"}], "source": "SYNTHETIC_NOT_PRODUCTION"}
    assert market_view_disclosure(fixture) == market_view_disclosure(fixture)
