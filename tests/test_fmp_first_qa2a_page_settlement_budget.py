from __future__ import annotations

import asyncio
from pathlib import Path

from agents.atlas_runtime_qa_v3 import (
    _classify_failed_request,
    preserve_partial_journey_progress,
    settlement_failure_classification,
)
from agents.runtime_qa_user_journeys_v40 import (
    ASK_STEP_BUDGET_SECONDS,
    GENERIC_NAVIGATION_BUDGET_SECONDS,
    PER_ROUTE_SETTLEMENT_SECONDS,
    REQUIRED_PHASE_MAX_SECONDS,
    RESEARCH_STEP_BUDGET_SECONDS,
    _page_contract_ready,
    _page_identity_matches,
    navigation_phase_upper_bound,
    wait_for_page_settlement,
)


ROOT = Path(__file__).resolve().parents[1]


class _MarkerLocator:
    def __init__(self, selector: str, page_id: str):
        self.selector = selector
        self.page_id = page_id

    async def count(self):
        if self.selector == "body":
            return 1
        if self.selector == '[data-testid="stException"]':
            return 0
        return int(self.page_id in self.selector and "atlas-qa-" in self.selector)

    async def inner_text(self, timeout=0):
        return "Visibly rendered customer page"

    async def is_visible(self):
        raise AssertionError("Hidden QA markers must not require visible semantics")


class _MarkerPage:
    def __init__(self, page_id: str):
        self.page_id = page_id
        self.frames = []

    def locator(self, selector: str):
        return _MarkerLocator(selector, self.page_id)


def test_hidden_home_marker_is_dom_readable_and_settles_without_heading_text():
    page = _MarkerPage("home")
    assert asyncio.run(_page_identity_matches(page, "Home"))
    assert asyncio.run(_page_contract_ready(page, "Home"))
    settled, _, _ = asyncio.run(wait_for_page_settlement(page, "Home"))
    assert settled


def test_hidden_etf_marker_is_dom_readable_and_settles_without_visibility():
    page = _MarkerPage("etfs")
    settled, _, _ = asyncio.run(wait_for_page_settlement(page, "ETFs"))
    assert settled


def test_route_and_required_phase_budgets_are_bounded():
    assert 10 <= PER_ROUTE_SETTLEMENT_SECONDS <= 15
    assert GENERIC_NAVIGATION_BUDGET_SECONDS <= 180
    assert RESEARCH_STEP_BUDGET_SECONDS * 6 + ASK_STEP_BUDGET_SECONDS * 6 < 600
    assert REQUIRED_PHASE_MAX_SECONDS < 600
    assert navigation_phase_upper_bound(14) == GENERIC_NAVIGATION_BUDGET_SECONDS
    assert navigation_phase_upper_bound(14) <= 180


def test_prevalidated_navigation_prevents_second_fourteen_page_traversal():
    source = (ROOT / "agents" / "atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert "prevalidated_navigation=page_results" in source
    journeys = (ROOT / "agents" / "runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")
    assert "if prevalidated:" in journeys
    assert "Reused bounded architecture inventory result." in journeys


def test_partial_progress_survives_wrapper_timeout():
    partial = {
        "steps": [{"journey": "Research NVDA", "status": "PASS"}],
        "family_completed": {"research": {"attempted": 1, "completed": 1, "failed": 0}},
    }
    result = preserve_partial_journey_progress(
        {"steps": []}, partial,
        {"navigation": 14, "research": 6, "ask": 6, "responsive": 6, "cross_page": 1},
        "TimeoutError",
    )
    assert result["steps"] == partial["steps"]
    assert result["required_journey_completeness"]["families"]["research"]["completed"] == 1
    assert result["status"] == "ENGINE_EXCEPTION"


def test_marker_settlement_failures_are_qa_defects_unless_exception_rendered():
    assert settlement_failure_classification("identity=false; rendered_exception=False") == "QA_DEFECT"
    assert settlement_failure_classification("rendered_exception=True") == "PRODUCT_DEFECT"


def test_streamlit_open_event_403_is_platform_telemetry_noise():
    result = _classify_failed_request("https://example.test/api/v1/app/event/open?secret=no", 403)
    assert result == {
        "path": "/api/v1/app/event/open",
        "classification": "PLATFORM_TELEMETRY_NOISE",
        "relevance": "NOT_ATLAS_FUNCTIONALITY",
    }
    assert "secret" not in str(result)


def test_missing_v66_money_short_helper_is_repaired_before_active_call():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert source.index("def v66_money_short") < source.index("v66_money_short(fcf)")
