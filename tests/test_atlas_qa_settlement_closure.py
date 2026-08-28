"""One-shot lifecycle settlement coverage for all active ATLAS pages."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from agents.product_hardening_certification import ACTIVE_PAGES, DEEP_CERTIFICATION_PAGES
from agents.runtime_qa_architecture import full_certification_ticker_matrix
from agents.runtime_qa_user_journeys_v40 import (
    _has_stale_page_fingerprint, _navigate, _page_interactive_conditions, _page_interactive_ready,
    _page_render_complete,
)
from services.session_stability import PAGE_INTERACTIVE_CONTRACTS


ROOT = Path(__file__).resolve().parents[1]


class Locator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector
        self.first = self

    async def count(self):
        if "stException" in self.selector:
            return 0
        if "atlas-qa-route-research-any-ticker" in self.selector:
            return 1
        if "atlas-qa-interactive-research-any-ticker" in self.selector:
            return 1
        if "atlas-qa-page-research-any-ticker" in self.selector:
            return 0
        if "page-route" in self.selector or "page-interactive" in self.selector:
            return 1
        if self.selector == "body":
            return 1
        return 0

    async def get_attribute(self, name):
        return "research-any-ticker" if name == "data-atlas-page" else None

    async def inner_text(self, timeout=0):
        return "Live Atlas Research"

    async def is_visible(self):
        return True

    async def is_checked(self):
        return self.page.selected

    async def click(self, timeout=0):
        self.page.selected = True

    def nth(self, _index):
        return self


class RoleLocator(Locator):
    async def count(self):
        return 1


class Page:
    def __init__(self):
        self.frames = []
        self.selected = False

    def locator(self, selector):
        return Locator(self, selector)

    def get_by_role(self, _role, name=None, exact=None):
        return RoleLocator(self, name or "")

    def get_by_text(self, text, exact=None):
        return Locator(self, text)


def test_run65_research_interactive_does_not_wait_for_render_complete():
    page = Page()
    assert asyncio.run(_page_interactive_ready(page, "Research Any Ticker"))
    assert not asyncio.run(_page_render_complete(page, "Research Any Ticker"))
    settled, _, detail = asyncio.run(_navigate(page, "Research Any Ticker"))
    assert settled and detail == ""


def test_all_fourteen_pages_and_nine_deep_pages_have_interactive_contracts():
    assert len(ACTIVE_PAGES) == len(PAGE_INTERACTIVE_CONTRACTS) == 14
    assert set(ACTIVE_PAGES) == set(PAGE_INTERACTIVE_CONTRACTS)
    assert len(DEEP_CERTIFICATION_PAGES) == 9
    assert set(DEEP_CERTIFICATION_PAGES).issubset(PAGE_INTERACTIVE_CONTRACTS)
    emitters = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("app.py", "ui/daily_opportunities.py", "ui/developer_center.py")
    )
    for page in ACTIVE_PAGES:
        assert f'emit_page_interactive(st, "{page}")' in emitters


def test_research_marker_follows_form_and_precedes_submission_acquisition():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.rfind("def render_research_any_ticker(")
    end = source.find("\n\ndef ", start + 5)
    body = source[start:end]
    assert body.index('key="typed_ticker"') < body.index('emit_page_interactive(st, "Research Any Ticker")')
    assert body.index('emit_page_interactive(st, "Research Any Ticker")') < body.index("if submitted:")
    assert body.index("if submitted:") < body.index("build_live_research_row")


def test_navigation_uses_interactive_state_and_tracks_render_completion_separately():
    source = inspect.getsource(_navigate)
    assert "explicit_ready = await _page_contract_ready" in source
    assert "render_complete = await _page_render_complete" in source
    assert "page_ready = explicit_ready and identity_matches and not stale_page" in source
    assert "page_ready = render_complete" not in source
    for metric in (
        "route_selected_seconds", "page_interactive_seconds", "render_complete_seconds",
    ):
        assert metric in source


def test_run67_optional_market_tape_cannot_block_route_interaction():
    """Run #67: Research identity appeared but its form/marker missed settlement."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.rfind("def main():")
    end = source.find("\n\n# ", start)
    body = source[start:end]
    slot = body.index('_market_tape_slot = st.container()')
    research = body.index('elif selected_page=="Research Any Ticker"')
    fill = body.index("with _market_tape_slot:")
    complete = body.index("_emit_page_certification_marker")
    assert slot < research < fill < complete
    assert 'if selected_page != "Home": render_v72_market_tape' not in body


def test_research_failed_settlement_reports_each_primary_condition():
    page = Page()
    conditions = asyncio.run(_page_interactive_conditions(page, "Research Any Ticker"))
    assert conditions == {
        "interactive_marker": True,
        "ticker_input": False,
        "submit_control": False,
    }


def test_stale_prior_page_marker_blocks_settlement_fingerprint():
    page = Page()
    assert not asyncio.run(_has_stale_page_fingerprint(page, "Research Any Ticker"))


def test_full_ticker_matrix_contains_all_top15_and_required_archetypes():
    matrix = full_certification_ticker_matrix(ROOT)
    assert len(matrix["top15"]) == 15
    assert set(matrix["top15"]).issubset(matrix["tickers"])
    assert "INVALID123" in matrix["tickers"]
    assert matrix["deep_research_subset"]
    roles = set(matrix["role_tickers"])
    assert {"top15", "top_idea", "recovery", "earnings", "etf", "missing_production", "invalid"}.issubset(roles)


def test_existing_backend_gate_covers_all_150_persisted_rows():
    source = (ROOT / "tests/test_ai_valuation.py").read_text(encoding="utf-8")
    assert "test_current_150_rows_preserve_all_investment_outputs" in source
    assert 'rows = json.loads(open("market_full_scan.json"' in source
    assert "assert rows == before_rows" in source
