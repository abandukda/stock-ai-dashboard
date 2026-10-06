"""Versioned product-hardening inventory and evidence certification contracts."""

from __future__ import annotations

from typing import Any, Final, Mapping, Sequence


PRODUCT_HARDENING_VERSION: Final = "ATLAS_PRODUCT_HARDENING_V1"
ACTIVE_PAGES: Final = (
    "Home", "Today's Opportunities", "Volume Intelligence", "Atlas Core Holdings",
    "Research Any Ticker", "Earnings Intelligence", "Full Ranked Scan",
    "Portfolio Intelligence", "Watchlist Intelligence", "Recovery", "ETFs",
    "Political Intelligence", "Ask AI", "Developer Center",
)
DEEP_CERTIFICATION_PAGES: Final = (
    "Home", "Today's Opportunities", "Research Any Ticker", "Earnings Intelligence",
    "ETFs", "Portfolio Intelligence", "Watchlist Intelligence",
    "Political Intelligence", "Ask AI",
)
REPRESENTATIVE_JOURNEYS: Final = (
    ("Home", "Research Any Ticker", "Ask AI", "Research Any Ticker", "Home"),
    ("Today's Opportunities", "Research Any Ticker"),
    ("Earnings Intelligence", "Research Any Ticker"),
    ("Political Intelligence", "Research Any Ticker"),
    ("ETFs", "Research Any Ticker"),
    ("Watchlist Intelligence", "Research Any Ticker"),
)
EVIDENCE_CLAIM_CONTRACTS: Final = {
    "Research Any Ticker": ("provider", "observation_or_report_date", "freshness", "evidence_id"),
    "Earnings Intelligence": ("reported_period", "report_date", "provider", "evidence_id"),
    "Political Intelligence": ("transaction_date", "disclosure_date", "provider", "evidence_id"),
    "Today's Opportunities": ("production_scan_timestamp", "production_decision_digest"),
    "ETFs": ("security_type", "provider", "observation_date"),
    "Ask AI": ("ticker", "evidence_ids_used", "evidence_missing", "as_of_date"),
}
MOBILE_CRITICAL_JOURNEYS: Final = (
    "Home", "home-card-to-research", "Today's Opportunities",
    "opportunities-to-research", "Research Any Ticker", "research-all-tabs-mobile",
    "Ask AI", "ask-question-mobile",
    "Political Intelligence",
)
SESSION_STABILITY_JOURNEY: Final = (
    "authenticated", "Home", "Research Any Ticker", "Research tabs",
    "Ask AI", "Research Any Ticker", "Home",
)
VISUAL_CERTIFICATION_COLUMNS: Final = (
    "source_sha", "page", "ticker_context", "interaction_id", "tab_name",
    "viewport", "state", "screenshot_path", "expected_state",
    "observed_state", "status",
)


def certification_matrix_contract() -> dict[str, object]:
    return {
        "version": PRODUCT_HARDENING_VERSION,
        "columns": (
            "page", "interaction", "expected", "observed", "evidence_source",
            "desktop", "mobile", "status", "severity",
        ),
        "active_pages": ACTIVE_PAGES,
        "deep_pages": DEEP_CERTIFICATION_PAGES,
        "journeys": REPRESENTATIVE_JOURNEYS,
        "evidence_claims": EVIDENCE_CLAIM_CONTRACTS,
        "mobile_journeys": MOBILE_CRITICAL_JOURNEYS,
        "session_journey": SESSION_STABILITY_JOURNEY,
        "screenshot_manifest_columns": VISUAL_CERTIFICATION_COLUMNS,
    }


def screenshot_manifest_entry(
    *, source_sha: str, page: str, screenshot_path: str, status: str,
    ticker_context: str = "", interaction_id: str = "", tab_name: str = "",
    viewport: str = "desktop", state: str = "state",
    expected_state: str = "", observed_state: str = "",
) -> dict[str, str]:
    return {
        "source_sha": str(source_sha), "page": str(page),
        "ticker_context": str(ticker_context), "interaction_id": str(interaction_id),
        "tab_name": str(tab_name), "viewport": str(viewport), "state": str(state),
        "screenshot_path": str(screenshot_path), "expected_state": str(expected_state),
        "observed_state": str(observed_state), "status": str(status),
    }


def visual_certification_completeness(
    *, source_sha: str, architecture_versions: Mapping[str, Any],
    page_results: Sequence[Mapping[str, Any]], interaction_certification: Mapping[str, Any],
    screenshot_manifest: Sequence[Mapping[str, Any]], evidence_reconciliations: Mapping[str, Any],
    mobile_results: Mapping[str, Any], session_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed when any required visual/evidence contract is incomplete."""
    pages_tested = {str(item.get("page") or "") for item in page_results if item.get("status")}
    page_screenshots = {
        str(item.get("page") or "") for item in screenshot_manifest
        if item.get("viewport") == "desktop" and item.get("state") == "page"
        and item.get("screenshot_path") and item.get("status") == "PASS"
    }
    results = list(interaction_certification.get("results") or [])
    deep_tab_results = {
        str(item.get("source_page") or ""): item for item in results
        if item.get("interaction_type") == "TAB"
    }
    tab_requirements_met = all(
        page in deep_tab_results
        and deep_tab_results[page].get("status") == "PASS"
        and all(tab.get("screenshot_path") for tab in deep_tab_results[page].get("tabs") or [])
        for page in DEEP_CERTIFICATION_PAGES
        if any(str(item.get("source_page") or "") == page and item.get("interaction_type") == "TAB" for item in results)
    )
    # A deep page with rendered tabs must have a passing tab result; a page
    # with zero rendered tabs is represented by its page result tab count.
    for page in DEEP_CERTIFICATION_PAGES:
        page_result = next((item for item in page_results if item.get("page") == page), {})
        if int(page_result.get("tabs") or 0) > 0 and page not in deep_tab_results:
            tab_requirements_met = False
    interaction_coverage = interaction_certification.get("coverage") or {}
    evidence_complete = all(
        (evidence_reconciliations.get(page) or {}).get("status") == "PASS"
        for page in ("Research Any Ticker", "Earnings Intelligence", "Political Intelligence", "Ask AI")
    )
    mobile_complete = all((mobile_results.get(name) or {}).get("status") == "PASS" for name in MOBILE_CRITICAL_JOURNEYS)
    required_manifest = [item for item in screenshot_manifest if item.get("expected_state")]
    screenshots_missing = sum(not bool(item.get("screenshot_path")) for item in required_manifest)
    traceability_complete = all(architecture_versions.get(key) for key in (
        "source_commit", "provider_registry_version", "yahoo_registry_version",
        "research_context_version", "interaction_registry_version",
        "product_hardening_version",
    )) and str(architecture_versions.get("source_commit")) == str(source_sha)
    checks = {
        "pages": set(ACTIVE_PAGES).issubset(pages_tested),
        "page_screenshots": set(ACTIVE_PAGES).issubset(page_screenshots),
        "tabs": bool(tab_requirements_met),
        "interactions": bool(interaction_coverage.get("full_certification_allowed")),
        "evidence_reconciliations": bool(evidence_complete),
        "mobile": bool(mobile_complete),
        "session": session_result.get("status") == "PASS",
        "screenshots": screenshots_missing == 0 and bool(required_manifest),
        "traceability": bool(traceability_complete),
    }
    return {
        "version": PRODUCT_HARDENING_VERSION,
        "status": "PASS" if all(checks.values()) else "INCOMPLETE",
        "full_certification_allowed": all(checks.values()),
        "checks": checks,
        "pages_expected": len(ACTIVE_PAGES), "pages_tested": len(set(ACTIVE_PAGES).intersection(pages_tested)),
        "tabs_discovered": sum(len(item.get("tabs") or []) for item in deep_tab_results.values()),
        "tabs_tested": sum(sum(bool(tab.get("selected")) for tab in item.get("tabs") or []) for item in deep_tab_results.values()),
        "interactions_discovered": int(interaction_coverage.get("discovered") or 0),
        "interactions_required": int(interaction_coverage.get("required") or 0),
        "interactions_attempted": int(interaction_coverage.get("attempted") or 0),
        "interactions_passed": int(interaction_coverage.get("passed") or 0),
        "interactions_failed": int(interaction_coverage.get("failed") or 0),
        "interactions_skipped": int(interaction_coverage.get("skipped") or 0),
        "screenshots_expected": len(required_manifest),
        "screenshots_generated": len(required_manifest) - screenshots_missing,
        "screenshots_missing": screenshots_missing,
        "evidence_reconciliations_required": 4,
        "evidence_reconciliations_completed": sum(
            (evidence_reconciliations.get(page) or {}).get("status") == "PASS"
            for page in ("Research Any Ticker", "Earnings Intelligence", "Political Intelligence", "Ask AI")
        ),
        "mobile_journeys_required": len(MOBILE_CRITICAL_JOURNEYS),
        "mobile_journeys_completed": sum((mobile_results.get(name) or {}).get("status") == "PASS" for name in MOBILE_CRITICAL_JOURNEYS),
    }


__all__ = [
    "ACTIVE_PAGES", "DEEP_CERTIFICATION_PAGES", "EVIDENCE_CLAIM_CONTRACTS",
    "MOBILE_CRITICAL_JOURNEYS", "PRODUCT_HARDENING_VERSION",
    "REPRESENTATIVE_JOURNEYS", "SESSION_STABILITY_JOURNEY",
    "VISUAL_CERTIFICATION_COLUMNS", "certification_matrix_contract",
    "screenshot_manifest_entry", "visual_certification_completeness",
]
