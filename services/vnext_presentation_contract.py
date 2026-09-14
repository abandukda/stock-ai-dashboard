"""UX-0 preservation inventory for the ATLAS VNext presentation migration.

The canonical data/behavior inventory is immutable unless a separate product
decision approves a semantic change.  The V1 page, tab, journey, and screenshot
inventory is only a versioned migration baseline: later approved UX phases may
replace it when every migrated element has an approved destination and the
corresponding migration/crawler assertions are intentionally updated.

This module is governance metadata only. It neither reads providers nor
calculates, selects, or mutates investment outputs.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from engines.research_context import EVIDENCE_FAMILIES


VNEXT_PRESENTATION_CONTRACT_VERSION: Final = "ATLAS_VNEXT_PRESENTATION_CONTRACT_V1"
MIGRATION_BASELINE_VERSION: Final = "ATLAS_VNEXT_UX2_RESEARCH_MIGRATION_BASELINE"
MIGRATION_BASELINE_CLASSIFICATION: Final = "VERSIONED_REPLACEABLE_MIGRATION_BASELINE"

HOME_INDICATOR_CLASSIFICATION: Final = MappingProxyType({
    "customer_primary": (
        "atlas_action", "current_price", "atlas_fair_value", "potential_upside_downside",
        "why_atlas_likes_it", "why_now", "main_risk", "decision_evidence", "full_investment_case_cta",
    ),
    "secondary": (
        "discovery_rank", "market_context", "wall_street_context", "catalysts",
        "decision_confidence", "evidence_quality", "valuation_concentration",
    ),
    "developer_only": (
        "committee_ready", "universe_reviewed", "research_candidates", "average_opportunity",
        "average_confidence", "raw_opportunity", "raw_component_coverage", "reason_codes",
        "policy_version", "provider_errors", "certification_state",
    ),
    "redundant": (
        "atlas_investment_view_duplicate", "why_it_could_win_duplicate",
        "action_rationale_duplicate", "duplicate_metric_matrix",
    ),
})

HOME_CUSTOMER_PRIMARY_LABELS: Final = (
    "ATLAS Action", "Current Price", "ATLAS Fair Value", "Why ATLAS Likes It",
    "Why Now", "Main Risk", "Decision Evidence", "View Full Investment Case",
)

HOME_PROHIBITED_CUSTOMER_TERMS: Final = (
    "Committee Ready", "Universe Reviewed", "Research Candidates", "Average Opportunity",
    "Average Confidence", "BUY_NOW_VALUATION_EVIDENCE_INSUFFICIENT", "REVIEW_REQUIRED",
    "DATA_LIMITED", "reason_codes", "policy_version", "provider error",
)


def validate_home_indicator_slots(slots: tuple[str, ...] | list[str]) -> dict:
    """Fail closed when a customer Home slot violates the approved taxonomy."""
    active = tuple(dict.fromkeys(str(slot) for slot in slots))
    required = set(HOME_INDICATOR_CLASSIFICATION["customer_primary"])
    prohibited = set(HOME_INDICATOR_CLASSIFICATION["developer_only"])
    redundant = set(HOME_INDICATOR_CLASSIFICATION["redundant"])
    missing = sorted(required.difference(active))
    forbidden = sorted(set(active).intersection(prohibited | redundant))
    return {
        "valid": not missing and not forbidden,
        "active_slots": list(active),
        "missing_customer_primary": missing,
        "prohibited_customer_slots": forbidden,
    }

PROTECTED_INVESTMENT_OUTPUTS: Final = (
    "recommendation", "opportunity", "confidence", "buy_now", "ranking",
    "score", "atlas_fair_value", "decision_expected_return", "entry_low",
    "entry_high", "decision_target", "trade_target_1", "trade_target_2",
    "stop", "risk_reward", "position_sizing", "technical_state",
    "scanner_universe", "scanner_prescreen", "scanner_full_scan_population",
)

PROTECTED_INTELLIGENCE: Final = (
    "research_completeness", "price", "fundamentals", "earnings",
    "analyst_evidence", "news_catalysts", "institutional_ownership",
    "insider_evidence", "political_context", "charts", "technical_metrics",
    "evidence_ids", "provenance", "freshness", "limitations",
    "availability_semantics",
)

# The canonical context families plus render-only/contextual families that are
# already exposed by the active Research report.
PROTECTED_EVIDENCE_FAMILIES: Final = tuple(dict.fromkeys((
    *EVIDENCE_FAMILIES,
    "insider_activity", "political_context", "risk", "valuation_families",
    "price_history", "market_context_inputs",
)))

AVAILABILITY_SEMANTICS: Final = (
    "AVAILABLE", "NOT_APPLICABLE", "DATA_UNAVAILABLE",
    "TEMPORARILY_UNAVAILABLE", "STALE_FALLBACK", "INCOMPLETE_EVIDENCE",
)

CURRENT_RESEARCH_TABS: Final = (
    "Decision", "Fundamentals & Valuation", "Technical & Trade State",
    "Catalysts & Sentiment", "Risk & Evidence",
)

CURRENT_ACTIVE_PAGES: Final = (
    "Home", "Today's Opportunities", "Volume Intelligence",
    "Atlas Core Holdings", "Research Any Ticker", "Earnings Intelligence",
    "Full Ranked Scan", "Portfolio Intelligence", "Watchlist Intelligence",
    "Recovery", "ETFs", "Political Intelligence", "Ask AI",
    "Developer Center",
)

PRESENTATION_BASELINE: Final = MappingProxyType({
    "version": MIGRATION_BASELINE_VERSION,
    "classification": MIGRATION_BASELINE_CLASSIFICATION,
    "may_change_with_explicit_ux_approval": True,
    "replacement_requirements": (
        "approved_destination_for_every_migrated_element",
        "legitimate_intelligence_remains_accessible",
        "canonical_investment_outputs_remain_invariant_unless_separately_approved",
        "migration_assertions_intentionally_updated",
        "crawler_journeys_intentionally_updated",
    ),
    "viewports": ("desktop", "mobile"),
    "active_pages": CURRENT_ACTIVE_PAGES,
    "research_tabs": CURRENT_RESEARCH_TABS,
    "required_journeys": (
        "direct_research", "home_to_research", "research_vnext_sections",
        "high_evidence_research", "monitor_incomplete_research",
        "ask_contextual_cta", "ask_grounding", "etf_research",
        "invalid_ticker", "political_evidence",
    ),
    "crawler_contract": MappingProxyType({
        "page_count": 14,
        "screenshot_manifest_required": True,
        "visible_customer_evidence_primary": True,
        "hidden_markers_supplemental_only": True,
    }),
})


def contract_snapshot() -> dict:
    """Return a JSON-friendly copy; callers cannot mutate the contract."""
    return {
        "version": VNEXT_PRESENTATION_CONTRACT_VERSION,
        "contract_classification": "IMMUTABLE_CANONICAL_DATA_AND_BEHAVIOR",
        "protected_investment_outputs": list(PROTECTED_INVESTMENT_OUTPUTS),
        "protected_intelligence": list(PROTECTED_INTELLIGENCE),
        "protected_evidence_families": list(PROTECTED_EVIDENCE_FAMILIES),
        "availability_semantics": list(AVAILABILITY_SEMANTICS),
        "presentation": {
            "version": MIGRATION_BASELINE_VERSION,
            "classification": MIGRATION_BASELINE_CLASSIFICATION,
            "may_change_with_explicit_ux_approval": True,
            "replacement_requirements": list(PRESENTATION_BASELINE["replacement_requirements"]),
            "viewports": list(PRESENTATION_BASELINE["viewports"]),
            "active_pages": list(CURRENT_ACTIVE_PAGES),
            "research_tabs": list(CURRENT_RESEARCH_TABS),
            "required_journeys": list(PRESENTATION_BASELINE["required_journeys"]),
            "crawler_contract": dict(PRESENTATION_BASELINE["crawler_contract"]),
            "home_indicator_classification": {
                key: list(value) for key, value in HOME_INDICATOR_CLASSIFICATION.items()
            },
            "home_customer_primary_labels": list(HOME_CUSTOMER_PRIMARY_LABELS),
            "home_prohibited_customer_terms": list(HOME_PROHIBITED_CUSTOMER_TERMS),
        },
    }


__all__ = [
    "AVAILABILITY_SEMANTICS", "CURRENT_ACTIVE_PAGES", "CURRENT_RESEARCH_TABS",
    "HOME_CUSTOMER_PRIMARY_LABELS", "HOME_INDICATOR_CLASSIFICATION",
    "HOME_PROHIBITED_CUSTOMER_TERMS", "MIGRATION_BASELINE_CLASSIFICATION", "MIGRATION_BASELINE_VERSION",
    "PRESENTATION_BASELINE", "PROTECTED_EVIDENCE_FAMILIES",
    "PROTECTED_INTELLIGENCE", "PROTECTED_INVESTMENT_OUTPUTS",
    "VNEXT_PRESENTATION_CONTRACT_VERSION", "contract_snapshot", "validate_home_indicator_slots",
]
