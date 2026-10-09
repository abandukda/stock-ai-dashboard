"""Governed contracts for autonomous customer-experience certification.

This module intentionally contains policy, not product logic.  It is safe to
import in offline QA because it neither imports providers nor mutates runtime
state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

VERSION = "atlas-customer-experience-qa/v1"
MODES = ("certify_only", "certify_and_repair")
DEFAULT_MAX_REPAIR_ATTEMPTS = 2
MAX_REPAIR_ATTEMPTS = 2

VIEWPORTS = {
    "desktop_1440": (1440, 1100),
    "desktop_1280": (1280, 960),
    "tablet_1024": (1024, 900),
    "tablet_768": (768, 1024),
    "mobile_430": (430, 932),
    "mobile_390": (390, 844),
}

SURFACES = (
    "home",
    "research_nvda",
    "research_msft",
    "research_avt",
    "earnings",
    "watchlist",
    "ask_grounded",
    "internal_report_card",
    "report_card_signal_detail",
    "customer_report_card_off",
)

SURFACE_FIELD_INVENTORY = {
    "home": ("ticker", "company_name", "action", "current_price", "atlas_fair_value", "potential", "opportunity", "confidence", "entry_status", "primary_risk", "certification_timestamp", "evaluation_snapshot"),
    "research": ("ticker", "company_name", "action", "current_price", "atlas_fair_value", "potential", "opportunity", "confidence", "entry", "risk", "earnings_state", "evaluation_snapshot"),
    "earnings": ("ticker", "quarter", "event_date", "transcript_date", "provider", "availability", "contextual_non_scoring", "certified_action"),
    "watchlist": ("ticker", "company_name", "action", "current_price", "atlas_fair_value", "distance_to_fair_value", "opportunity", "confidence", "entry_status", "earnings_state", "evaluation_snapshot"),
    "ask": ("ticker", "question_digest", "lifecycle", "action", "atlas_fair_value", "opportunity", "confidence", "evaluation_snapshot", "grounding_sources"),
    "report_card_overview": ("signal_count", "observation_count", "open_signal_count", "spy_coverage", "activation_timestamp", "next_eligible_observation", "ledger_integrity", "backup_status"),
    "report_card_signal": ("signal_id", "ticker", "action", "issuance_timestamp", "reference_price", "provenance", "candidate_digest", "publication_digest", "evaluation_snapshot", "horizons", "observation_count", "next_eligible_horizon", "corporate_action_state"),
}

PAGE_SCORE_CRITERIA = (
    "Data Accuracy", "Data Completeness", "Grounding", "Content Quality",
    "Visual Hierarchy", "Layout", "Typography", "Mobile UX",
    "Accessibility", "Interaction Reliability",
)

DESKTOP_SURFACES = SURFACES
MOBILE_SURFACES = tuple(
    item for item in SURFACES if item not in {"research_msft", "research_avt"}
)

PROTECTED_FIELDS = {
    "decision",
    "action",
    "atlas_fair_value",
    "opportunity",
    "confidence",
    "publication_allowed",
    "entry_thresholds",
}

PROTECTED_PATH_FRAGMENTS = (
    "valuation",
    "methodology",
    "provider",
    "scanner",
    "publication_policy",
    "report_card_ledger",
    "prospective",
)

AUTO_REPAIR_CATEGORIES = {
    "duplicate_display",
    "cta_sizing",
    "spacing",
    "mobile_overflow",
    "empty_state_copy",
    "number_formatting",
    "label_copy",
    "missing_governed_display",
    "stale_visual_key",
    "safe_navigation",
    "qa_selector",
    "qa_timing",
    "artifact_collection",
    "fixture_expectation",
}

HUMAN_REVIEW_CATEGORIES = {
    "action_logic",
    "fair_value_calculation",
    "opportunity_calculation",
    "confidence_calculation",
    "methodology",
    "recommendation_threshold",
    "publication_eligibility",
    "provider_authority",
    "new_financial_metric",
    "report_card_methodology",
    "prospective_ledger_mutation",
    "compliance_policy",
}

CUSTOMER_INTERNAL_TERMS = (
    "canonical",
    "artifact envelope",
    "deterministic replay",
    "publication gate",
    "candidate digest",
    "raw json",
)

REQUIRED_NAVIGATION = ("Home", "Research", "Earnings", "Watchlist", "Ask ATLAS")


@dataclass(frozen=True)
class FieldExpectation:
    page: str
    component: str
    field_name: str
    displayed_label: str
    source_object: str
    source_path: str
    authority_type: str
    expected_value: object
    expected_unit: str | None
    expected_format: str | None
    required: bool
    publication_eligible: bool
    customer_visible: bool
    snapshot_identity: str


@dataclass(frozen=True)
class Finding:
    finding_id: str
    page: str
    viewport: str
    component: str
    defect: str
    expected: object
    observed: object
    evidence: str
    severity: str
    category: str
    repair_class: str
    status: str = "OPEN"
    repair_commit: str | None = None

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def repair_class(category: str) -> str:
    if category in AUTO_REPAIR_CATEGORIES:
        return "AUTO_REPAIR_ALLOWED"
    return "HUMAN_REVIEW_REQUIRED"


def protected_path(path: str | Path) -> bool:
    normalized = str(path).lower().replace("-", "_")
    return any(fragment in normalized for fragment in PROTECTED_PATH_FRAGMENTS)
