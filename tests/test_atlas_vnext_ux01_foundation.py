from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engines.research_context import EVIDENCE_FAMILIES, build_production_decision
from services.vnext_presentation_contract import (
    AVAILABILITY_SEMANTICS, CURRENT_ACTIVE_PAGES, CURRENT_RESEARCH_TABS,
    MIGRATION_BASELINE_CLASSIFICATION, MIGRATION_BASELINE_VERSION,
    PROTECTED_EVIDENCE_FAMILIES, PROTECTED_INTELLIGENCE,
    PROTECTED_INVESTMENT_OUTPUTS, contract_snapshot,
)
from services.live_market.models import TechnicalState
from ui.vnext_presentation import (
    AvailabilityState, CanonicalNumberFormatter, change_since_last_scan,
    cross_signal_alignment, decision_header, evidence_drawer, evidence_health,
    monitor_technical_scenario,
    price_action_strip, primary_evidence_pair, technical_state_badge,
    ticker_opportunity_card, upside_risk_pair,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_JSON = (
    "etf_scan.json", "market_full_scan.json", "market_prescreen.json",
    "market_scan_state.json", "recovery_scan.json", "total_market_universe.json",
)


def test_ux0_inventory_protects_outputs_and_intelligence():
    assert {
        "recommendation", "opportunity", "confidence", "ranking", "score",
        "atlas_fair_value", "decision_expected_return", "entry_low", "entry_high",
        "trade_target_1", "trade_target_2", "stop", "risk_reward",
        "position_sizing", "technical_state", "scanner_universe",
        "scanner_prescreen", "scanner_full_scan_population",
    } <= set(PROTECTED_INVESTMENT_OUTPUTS)
    assert {
        "research_completeness", "fundamentals", "earnings", "analyst_evidence",
        "news_catalysts", "institutional_ownership", "insider_evidence",
        "political_context", "charts", "technical_metrics", "evidence_ids",
        "provenance", "freshness", "limitations", "availability_semantics",
    } <= set(PROTECTED_INTELLIGENCE)
    assert set(EVIDENCE_FAMILIES) <= set(PROTECTED_EVIDENCE_FAMILIES)
    assert {"insider_activity", "political_context", "risk", "price_history"} <= set(PROTECTED_EVIDENCE_FAMILIES)
    assert {"NOT_APPLICABLE", "DATA_UNAVAILABLE", "TEMPORARILY_UNAVAILABLE", "STALE_FALLBACK", "INCOMPLETE_EVIDENCE"} <= set(AVAILABILITY_SEMANTICS)


def test_desktop_mobile_and_current_surface_snapshot_contract():
    fixture = json.loads((ROOT / "tests/fixtures/atlas_vnext_ux0_presentation_contract.json").read_text())
    snapshot = contract_snapshot()
    assert fixture["version"] == snapshot["version"]
    assert fixture["contract_classification"] == snapshot["contract_classification"] == "IMMUTABLE_CANONICAL_DATA_AND_BEHAVIOR"
    assert fixture["presentation_baseline_version"] == snapshot["presentation"]["version"] == MIGRATION_BASELINE_VERSION
    assert fixture["presentation_classification"] == snapshot["presentation"]["classification"] == MIGRATION_BASELINE_CLASSIFICATION
    assert fixture["may_change_with_explicit_ux_approval"] is snapshot["presentation"]["may_change_with_explicit_ux_approval"] is True
    assert fixture["viewports"] == snapshot["presentation"]["viewports"]
    assert fixture["active_page_count"] == len(CURRENT_ACTIVE_PAGES) == 14
    assert fixture["research_tab_count"] == len(CURRENT_RESEARCH_TABS) == 12
    assert fixture["screenshot_manifest_required"] is snapshot["presentation"]["crawler_contract"]["screenshot_manifest_required"]


def test_current_pages_tabs_navigation_and_journeys_are_replaceable_migration_baseline():
    presentation = contract_snapshot()["presentation"]
    assert presentation["classification"] == "VERSIONED_REPLACEABLE_MIGRATION_BASELINE"
    assert presentation["may_change_with_explicit_ux_approval"] is True
    requirements = set(presentation["replacement_requirements"])
    assert {
        "approved_destination_for_every_migrated_element",
        "legitimate_intelligence_remains_accessible",
        "migration_assertions_intentionally_updated",
        "crawler_journeys_intentionally_updated",
    } <= requirements
    # These assertions record V1 coverage. They are intentionally replaceable
    # when an approved UX phase consolidates pages, tabs, or navigation.
    assert len(presentation["active_pages"]) == 14
    assert len(presentation["research_tabs"]) == 12


def test_contract_snapshot_is_detached_from_immutable_inventory():
    snapshot = contract_snapshot()
    snapshot["protected_evidence_families"].clear()
    assert EVIDENCE_FAMILIES[0] in PROTECTED_EVIDENCE_FAMILIES


@pytest.mark.parametrize("value,expected", [
    (41809874944, "$41.8B"), (250000, "$250.0K"), (0, "$0.00"), (-2500, "$-2.5K"),
])
def test_customer_currency_formatting_preserves_exact_value(value, expected):
    formatted = CanonicalNumberFormatter.currency(value)
    assert formatted.display == expected
    assert formatted.exact_value == value


def test_prices_ranges_percentages_ratios_and_counts_are_semantically_distinct():
    assert CanonicalNumberFormatter.price(52.94).display == "$52.94"
    assert CanonicalNumberFormatter.currency_range(250000, 1100000).display == "$250.0K–$1.1M"
    assert CanonicalNumberFormatter.percent(12.36, signed=True).display == "+12.4%"
    assert CanonicalNumberFormatter.percent(-8.06, signed=True).display == "−8.1%"
    assert CanonicalNumberFormatter.percent(0.12).display == "0.1%"
    assert CanonicalNumberFormatter.ratio(0.12).display == "0.12×"
    assert CanonicalNumberFormatter.count(2852).display == "2,852"


def test_decision_critical_exact_currency_and_null_handling():
    exact = CanonicalNumberFormatter.currency(41809874944, exact=True)
    assert exact.display == "$41,809,874,944.00"
    unavailable = CanonicalNumberFormatter.price(None)
    assert unavailable.display == "Unavailable"
    assert unavailable.exact_value is None
    assert unavailable.availability == AvailabilityState.UNAVAILABLE
    assert CanonicalNumberFormatter.price([]).display == "Unavailable"
    assert CanonicalNumberFormatter.price({}).display == "Unavailable"


def test_dates_and_timezone_aware_timestamps_preserve_sources():
    assert CanonicalNumberFormatter.customer_date("2026-08-29").display == "Aug 29, 2026"
    source = datetime(2026, 8, 29, 14, 30, tzinfo=timezone.utc)
    rendered = CanonicalNumberFormatter.timestamp(source)
    assert rendered.display == "Aug 29, 2026 · 14:30 UTC"
    assert rendered.exact_value is source
    assert CanonicalNumberFormatter.timestamp(datetime(2026, 8, 29, 14, 30)).display == "Unavailable"


def test_evidence_health_states_do_not_fabricate_or_conflate():
    stale = evidence_health(semantic_status="AVAILABLE", cache_status="STALE_FALLBACK", completeness_pct=40, limitations=("Missing fundamentals",))
    assert stale.availability == AvailabilityState.STALE_FALLBACK
    assert stale.completeness.display == "40.0%"
    assert stale.limitations == ("Missing fundamentals",)
    incomplete = evidence_health(semantic_status="AVAILABLE", cache_status="FRESH_CACHE", completeness_pct=40)
    assert incomplete.availability == AvailabilityState.INCOMPLETE_EVIDENCE
    assert evidence_health(semantic_status="NOT_APPLICABLE", cache_status=None, completeness_pct=None).availability == AvailabilityState.NOT_APPLICABLE
    assert evidence_health(semantic_status="DATA_UNAVAILABLE", cache_status=None, completeness_pct=None).availability == AvailabilityState.UNAVAILABLE


def test_confidence_and_research_completeness_remain_separate_exact_values():
    header = decision_header(recommendation="MONITOR", opportunity=None, confidence=None, research_completeness=40.0, actionability_label="Monitor — Not currently actionable")
    assert header.confidence is None
    assert header.research_completeness == 40.0
    assert header.actionability_label == "Monitor — Not currently actionable"


@pytest.mark.parametrize("state", list(TechnicalState))
def test_technical_badge_only_renders_deterministic_contract_state(state):
    badge = technical_state_badge(state)
    assert badge.canonical_value == state.value
    assert badge.label


def test_technical_badge_does_not_infer_unknown_state():
    badge = technical_state_badge("looks bullish")
    assert badge.canonical_value is None
    assert badge.label == "Unavailable"


def test_upside_and_risk_have_symmetric_display_contract():
    pair = upside_risk_pair(upside_pct=12.4, downside_or_invalidation_pct=-8.1)
    assert pair.upside.semantic_type == pair.downside_or_invalidation.semantic_type == "percent"
    assert pair.upside.display == "+12.4%"
    assert pair.downside_or_invalidation.display == "−8.1%"


def test_presentation_models_are_immutable_and_preserve_values():
    strip = price_action_strip(current_price=52.94, entry_low=52.15, entry_high=53.34, invalidation=50.73)
    assert [item.exact_value for item in (strip.current_price, strip.entry_low, strip.entry_high, strip.invalidation)] == [52.94, 52.15, 53.34, 50.73]
    with pytest.raises(FrozenInstanceError):
        strip.current_price = CanonicalNumberFormatter.price(1)


def test_evidence_change_and_political_alignment_are_context_only():
    evidence = primary_evidence_pair(support="Revenue growth", contradiction_or_risk="Valuation risk")
    assert evidence.support == "Revenue growth" and evidence.contradiction_or_risk == "Valuation risk"
    change = change_since_last_scan("recommendation", "MONITOR", "BUY_NOW")
    assert change.changed and change.previous == "MONITOR" and change.current == "BUY_NOW"
    alignment = cross_signal_alignment(political_context="Buying", atlas_context="Buying")
    assert alignment.relationship == "Aligned"
    assert "does not change ATLAS scoring" in alignment.disclaimer


def test_evidence_drawer_and_compact_ticker_card_preserve_support_and_risk():
    health = evidence_health(
        semantic_status="AVAILABLE", cache_status="FRESH_CACHE",
        completeness_pct=80, limitations=("One family is incomplete",),
    )
    drawer = evidence_drawer(
        title="Supporting evidence", evidence_ids=("ev_1",),
        provenance=("FMP",), limitations=health.limitations,
    )
    assert drawer.collapsed_by_default and drawer.evidence_ids == ("ev_1",)
    card = ticker_opportunity_card(
        ticker="nvda", company="NVIDIA", action_state="MONITOR",
        canonical_technical_state="NEAR_BREAKOUT", current_price=100,
        entry_low=98, entry_high=102, invalidation=94, upside_pct=12,
        downside_pct=-6, primary_support="Earnings", primary_risk="Valuation",
        health=health,
    )
    assert card.ticker == "NVDA"
    assert card.technical_state.canonical_value == "NEAR_BREAKOUT"
    assert card.evidence.support == "Earnings"
    assert card.evidence.contradiction_or_risk == "Valuation"


def test_approved_monitor_scenario_is_collapsed_and_non_actionable_language_only():
    scenario = monitor_technical_scenario(
        current_price=52.94, entry_low=52.15, entry_high=53.34,
        invalidation=50.73,
    )
    assert scenario.label == "Technical Scenario"
    assert scenario.collapsed_by_default
    assert "deterministic technical scenario" in scenario.explanation
    assert "do not represent a high-confidence ATLAS recommendation" in scenario.explanation
    assert scenario.levels.entry_low.exact_value == 52.15


def test_presentation_helpers_do_not_mutate_authoritative_decision_or_source_row():
    source = {
        "Recommendation": "BUY NOW", "Opportunity": 81.2, "Confidence": 77.4,
        "rank": 3, "atlas_fair_value": 125.0, "expected_return_pct": 12.4,
        "entry_low": 100.0, "entry_high": 103.0, "target_1": 115.0,
        "target_2": 125.0, "stop": 95.0, "position_sizing": "2–3%",
    }
    before = deepcopy(source)
    decision_before = dict(build_production_decision(source))
    decision_header(recommendation=source["Recommendation"], opportunity=source["Opportunity"], confidence=source["Confidence"], research_completeness=40)
    price_action_strip(current_price=101, entry_low=source["entry_low"], entry_high=source["entry_high"], invalidation=source["stop"])
    assert source == before
    assert dict(build_production_decision(source)) == decision_before


def test_ux01_sources_never_reference_production_json_or_scanner():
    sources = "\n".join((ROOT / path).read_text() for path in (
        "services/vnext_presentation_contract.py", "ui/vnext_presentation.py",
    ))
    assert "market_full_scan.json" not in sources
    assert "overnight_market_scan" not in sources
    assert "yfinance" not in sources


def test_production_json_exists_as_external_immutable_baseline():
    before = {name: (ROOT / name).read_bytes() for name in PRODUCTION_JSON}
    CanonicalNumberFormatter.currency(41809874944)
    technical_state_badge("NEAR_BREAKOUT")
    after = {name: (ROOT / name).read_bytes() for name in PRODUCTION_JSON}
    assert before == after
    assert all(len(hashlib.sha256(value).hexdigest()) == 64 for value in after.values())
