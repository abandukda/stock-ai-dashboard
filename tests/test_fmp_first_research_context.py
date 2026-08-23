from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import pytest

import engines.live_research_engine as live
from engines.research_context import (
    CORPORATE_ONLY_FAMILIES,
    EVIDENCE_FAMILIES,
    RESEARCH_CONTEXT_VERSION,
    RESEARCH_SYNTHESIS_VERSION,
    SYNTHESIS_SECTIONS,
    TOP_ANALYST_ACTIONS_VERSION,
    build_research_context,
    customer_freshness_label,
    evidence_envelope,
    load_production_row,
    stable_evidence_id,
    top_analyst_actions_contract,
)
from services.research_family_cache import (
    FAMILY_TTLS_SECONDS,
    RESEARCH_FAMILY_CACHE_VERSION,
    load_family_envelope,
    save_family_envelope,
)
from services.yahoo_dependency_registry import EXPECTED_YAHOO_DEPENDENCY_COUNT_V1, YAHOO_DEPENDENCIES


def _production(**updates):
    row = {
        "ticker": "NVDA",
        "security_type": "EQUITY",
        "committee_verdict": "BUY_NOW",
        "opportunity_score": 91.25,
        "confidence": 78.9,
        "relative_rank_score": 123.4,
        "atlas_fair_value": 250.0,
        "decision_expected_return_pct": -3.5,
        "entry_low": 0.0,
        "entry_high": 220.0,
        "target": 240.0,
        "trade_target_1": 230.0,
        "trade_target_2": 240.0,
        "stop_loss": 205.0,
        "position_size_range": "2–4%",
        "scan_time": "2026-08-23T03:00:00+00:00",
    }
    row.update(updates)
    return row


def _envelope(family="profile", data=None):
    return evidence_envelope(
        ticker="NVDA",
        family=family,
        semantic_status="AVAILABLE",
        cache_status="FETCHED",
        provider="FMP",
        endpoint_family="stable/profile",
        fetched_at="2026-08-23T03:10:00+00:00",
        observation_date="2026-08-23",
        data={"zero": 0, "negative": -2.5, "missing": None} if data is None else data,
        evidence_ids=("ev_123",),
    )


def test_research_context_v1_top_level_and_reserved_families() -> None:
    context = build_research_context("nvda", production_row=_production())
    assert context["version"] == RESEARCH_CONTEXT_VERSION == "RESEARCH_CONTEXT_V1"
    assert set(context) == {
        "version", "ticker", "security_type", "generated_at", "production_decision",
        "market_snapshot", "evidence_families", "evidence_registry", "synthesis", "limitations",
    }
    assert tuple(context["evidence_families"]) == EVIDENCE_FAMILIES


def test_production_decision_is_immutable_and_extracted_only() -> None:
    source = _production()
    context = build_research_context("NVDA", production_row=source)
    decision = context["production_decision"]
    assert decision["recommendation"] == "BUY_NOW"
    assert decision["opportunity"] == 91.25
    assert decision["confidence"] == 78.9
    assert decision["buy_now"] is True
    assert decision["atlas_fair_value"] == 250.0
    assert decision["decision_expected_return"] == -3.5
    assert decision["entry_low"] == 0.0
    assert decision["production_scan_timestamp"] == source["scan_time"]
    with pytest.raises(TypeError):
        decision["confidence"] = 100
    assert json.loads(json.dumps(context))["production_decision"]["confidence"] == 78.9


def test_missing_production_row_never_manufactures_decision(tmp_path) -> None:
    path = tmp_path / "scan.json"
    path.write_text(json.dumps([_production()]), encoding="utf-8")
    assert load_production_row("CRM", path) is None
    context = build_research_context("CRM", production_row=None)
    assert context["production_decision"] == {"semantic_status": "DATA_UNAVAILABLE"}
    assert context["limitations"]


def test_active_explicit_research_does_not_call_decision_or_recalculate_fv() -> None:
    source = inspect.getsource(live.build_live_research)
    assert "decision(row)" not in source
    assert "_fair_value_complete(" not in source
    assert "calculate_atlas_fair_value(" not in source


def test_enrichment_is_stripped_from_scoring_namespaces(monkeypatch) -> None:
    monkeypatch.setattr(live, "load_production_row", lambda _ticker: _production())
    enriched = {
        "ticker": "NVDA",
        "price": 219.0,
        "research_refreshed_at": "2026-08-23T03:10:00+00:00",
        "Recommendation": "RECALCULATED",
        "opportunity_score": 1,
        "confidence": 1,
        "atlas_fair_value": 999,
        "expected_return_pct": 999,
        "entry_low": 999,
        "target": 999,
        "stop_loss": 999,
        "Revenue Growth": 0.0,
    }
    result = live._attach_canonical_research_context(enriched, "NVDA")
    assert result["Recommendation"] == "BUY_NOW"
    assert result["opportunity_score"] == 91.25
    assert result["confidence"] == 78.9
    assert result["atlas_fair_value"] == 250.0
    assert result["expected_return_pct"] == -3.5
    assert result["entry_low"] == 0.0
    assert result["target"] == 240.0
    assert result["stop_loss"] == 205.0
    assert result["research_context"]["evidence_families"]["growth_segments"]["data"]["revenue_growth"] == 0.0


def test_family_envelope_schema_provenance_and_missing_semantics() -> None:
    envelope = _envelope()
    assert set(envelope) == {
        "semantic_status", "cache_status", "provider", "endpoint_family", "fetched_at",
        "observation_date", "reporting_date", "filing_date", "age_seconds", "data",
        "evidence_ids", "limitations",
    }
    assert envelope["provider"] == "FMP"
    assert envelope["data"] == {"zero": 0, "negative": -2.5, "missing": None}
    assert envelope["data"]["missing"] is None


@pytest.mark.parametrize("forbidden", ["raw_payload", "provider_payload", "response_body", "api_key", "authenticated_url"])
def test_raw_provider_material_is_rejected(forbidden) -> None:
    with pytest.raises(ValueError):
        _envelope(data={forbidden: "secret or raw content"})


def test_evidence_id_is_stable_and_provenance_sensitive() -> None:
    kwargs = dict(
        ticker="NVDA", family="profile", provider="FMP", semantic_identity="stable/profile",
        observation_date="2026-08-23", provenance="stable/profile",
    )
    assert stable_evidence_id(**kwargs) == stable_evidence_id(**kwargs)
    assert stable_evidence_id(**kwargs) != stable_evidence_id(**{**kwargs, "provider": "YAHOO"})


def test_live_normalized_evidence_id_does_not_change_on_cache_refresh_time() -> None:
    values = {"market_cap": 0, "sector": "Technology"}
    first = live._family_from_values("NVDA", "profile", "YAHOO", "get_info", "2026-08-23T03:00:00+00:00", values)
    second = live._family_from_values("NVDA", "profile", "YAHOO", "get_info", "2026-08-23T04:00:00+00:00", values)
    assert first["evidence_ids"] == second["evidence_ids"]
    assert first["fetched_at"] != second["fetched_at"]
    assert first["observation_date"] is None


def test_family_ttl_registry_matches_approved_policy() -> None:
    assert FAMILY_TTLS_SECONDS["profile"] == 7 * 86400
    assert FAMILY_TTLS_SECONDS["financial_statements"] == 8 * 3600
    assert FAMILY_TTLS_SECONDS["earnings_history"] == 8 * 3600
    assert FAMILY_TTLS_SECONDS["analyst_actions"] == 4 * 3600
    assert FAMILY_TTLS_SECONDS["institutional_ownership"] == 12 * 3600
    assert FAMILY_TTLS_SECONDS["holders_13f"] == 24 * 3600
    assert FAMILY_TTLS_SECONDS["company_news"] == 3600
    assert 6 * 3600 <= FAMILY_TTLS_SECONDS["sec_filings"] <= 12 * 3600
    assert FAMILY_TTLS_SECONDS["transcript_index"] == 24 * 3600
    assert FAMILY_TTLS_SECONDS["transcript_intelligence"] is None
    assert FAMILY_TTLS_SECONDS["etf_research"] == 24 * 3600


def test_stale_cache_preserves_original_provider_timestamp(tmp_path) -> None:
    original = _envelope()
    save_family_envelope("NVDA", "profile", original, root=tmp_path)
    fetched_epoch = datetime.fromisoformat(original["fetched_at"]).timestamp()
    loaded = load_family_envelope("NVDA", "profile", root=tmp_path, now_epoch=fetched_epoch + 8 * 86400)
    assert loaded["cache_version"] == RESEARCH_FAMILY_CACHE_VERSION
    assert loaded["cache_status"] == "STALE_FALLBACK"
    assert loaded["fetched_at"] == original["fetched_at"]
    assert loaded["age_seconds"] == 8 * 86400


def test_transcript_content_cache_is_immutable(tmp_path) -> None:
    envelope = _envelope(family="transcript_intelligence")
    save_family_envelope("NVDA", "transcript_intelligence", envelope, root=tmp_path, period_key="2026-Q2")
    with pytest.raises(FileExistsError):
        save_family_envelope("NVDA", "transcript_intelligence", envelope, root=tmp_path, period_key="2026-Q2")
    save_family_envelope("NVDA", "transcript_intelligence", envelope, root=tmp_path, period_key="2026-Q1")
    with pytest.raises(ValueError):
        save_family_envelope("NVDA", "transcript_intelligence", envelope, root=tmp_path)


def test_customer_freshness_mapping_is_deterministic() -> None:
    assert customer_freshness_label(_envelope(), production=True) == "Latest Production Scan"
    assert customer_freshness_label(_envelope()) == "Fresh"
    cached = {**_envelope(), "cache_status": "FRESH_CACHE"}
    assert customer_freshness_label(cached) == "Cached"
    unavailable = {**_envelope(), "semantic_status": "DATA_UNAVAILABLE"}
    assert customer_freshness_label(unavailable) == "Data Unavailable"


def test_etf_corporate_families_are_not_applicable() -> None:
    context = build_research_context("SPY", production_row=_production(ticker="SPY", security_type="ETF"))
    assert context["security_type"] == "ETF"
    for family in CORPORATE_ONLY_FAMILIES:
        assert context["evidence_families"][family]["semantic_status"] == "NOT_APPLICABLE"
    assert context["evidence_families"]["technicals"]["semantic_status"] == "DATA_UNAVAILABLE"


def test_top_analyst_actions_contract_is_bounded_and_not_distinct_selected() -> None:
    actions = [{
        "firm": f"Firm {index}", "action": "Upgrade", "current_rating": "Buy",
        "previous_rating": "Hold", "date": f"2026-08-{index + 1:02d}", "provider": "FMP",
        "source_family": "grades", "evidence_id": f"ev_{index}",
    } for index in range(7)]
    result = top_analyst_actions_contract(actions)
    assert result["version"] == TOP_ANALYST_ACTIONS_VERSION
    assert len(result["actions"]) == 5
    assert set(result["actions"][0]) == {"firm", "action", "current_rating", "previous_rating", "date", "provider", "source_family", "evidence_id"}


def test_synthesis_v2_is_schema_only() -> None:
    synthesis = build_research_context("NVDA", production_row=_production())["synthesis"]
    assert synthesis["version"] == RESEARCH_SYNTHESIS_VERSION
    assert synthesis["semantic_status"] == "DATA_UNAVAILABLE"
    assert tuple(synthesis["sections"]) == SYNTHESIS_SECTIONS
    assert all(value == [] for value in synthesis["sections"].values())
    assert set(synthesis["assertion_schema"]) == {"text", "evidence_ids", "as_of", "confidence"}


def test_yahoo_dependency_registry_did_not_increase() -> None:
    assert EXPECTED_YAHOO_DEPENDENCY_COUNT_V1 == 31
    assert len(YAHOO_DEPENDENCIES) == 31
