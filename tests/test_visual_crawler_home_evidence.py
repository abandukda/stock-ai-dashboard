import asyncio
from pathlib import Path

import pytest

import agents.atlas_visual_crawler_v1 as crawler_module
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler


class _Collection:
    def __init__(self, items):
        self.items = list(items)

    async def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class _Tab:
    def __init__(self, selected=True):
        self.selected = selected

    async def get_attribute(self, name):
        return "true" if name == "aria-selected" and self.selected else "false"


class _Panel:
    def __init__(self, text="Certified content", html="<p>Certified content</p>"):
        self.text = text
        self.html = html

    async def is_visible(self):
        return True

    async def inner_text(self):
        return self.text

    async def inner_html(self):
        return self.html


class _Scope:
    def __init__(self, panels):
        self.panels = panels

    def get_by_role(self, role):
        assert role == "tabpanel"
        return _Collection(self.panels)


class _Page:
    def locator(self, _selector):
        return _Collection([])

    async def wait_for_timeout(self, _milliseconds):
        return None


def test_home_tab_panel_requires_two_stable_semantic_checks(monkeypatch):
    crawler = object.__new__(AtlasVisualCrawler)
    page = _Page()
    panel = _Panel()
    checks = 0

    async def tab(_page, _name):
        nonlocal checks
        checks += 1
        return _Tab()

    crawler._fresh_visible_tab = tab
    monkeypatch.setattr(crawler_module, "_scopes", lambda _page: [_Scope([panel])])

    assert asyncio.run(crawler._settled_selected_tab_panel(page, "Decision")) is panel
    assert checks == 2


def test_home_tab_panel_reacquires_after_rerender(monkeypatch):
    crawler = object.__new__(AtlasVisualCrawler)
    page = _Page()
    panels = [_Panel(), _Panel()]
    calls = 0

    async def tab(_page, _name):
        return _Tab()

    def scopes(_page):
        nonlocal calls
        panel = panels[min(calls, 1)]
        calls += 1
        return [_Scope([panel])]

    crawler._fresh_visible_tab = tab
    monkeypatch.setattr(crawler_module, "_scopes", scopes)

    assert asyncio.run(crawler._settled_selected_tab_panel(page, "Decision")) is panels[1]
    assert calls >= 2


def test_selected_tab_screenshot_must_exist_and_be_nonzero(tmp_path):
    crawler = object.__new__(AtlasVisualCrawler)
    crawler.output_dir = tmp_path
    target = tmp_path / "screenshots" / "tab.png"

    async def settle(_page, _name):
        return _Panel()

    async def shot(_locator, **_kwargs):
        target.parent.mkdir()
        target.write_bytes(b"png-evidence")
        return "screenshots/tab.png"

    crawler._settled_selected_tab_panel = settle
    crawler._shot_locator = shot

    result = asyncio.run(
        crawler._shot_selected_tab_panel(
            _Page(), name="Decision", page_name="Research Any Ticker",
            interaction="tab-Decision", state="after", viewport="desktop", ticker="NVDA",
        )
    )
    assert result == "screenshots/tab.png"
    assert target.stat().st_size > 0


def test_unsettled_tab_fails_with_bounded_timeout(monkeypatch):
    crawler = object.__new__(AtlasVisualCrawler)
    page = _Page()

    async def tab(_page, _name):
        return _Tab(selected=False)

    crawler._fresh_visible_tab = tab
    monkeypatch.setattr(crawler_module, "_scopes", lambda _page: [_Scope([_Panel()])])

    with pytest.raises(TimeoutError, match="TAB_PANEL_NOT_SEMANTICALLY_SETTLED"):
        asyncio.run(crawler._settled_selected_tab_panel(page, "Decision", timeout_seconds=0.001))


def test_home_tab_capture_uses_semantic_polling_not_blind_global_sleep():
    source = Path("agents/atlas_visual_crawler_v1.py").read_text(encoding="utf-8")
    helper = source[source.index("async def _settled_selected_tab_panel"):source.index("async def _shot_selected_tab_panel")]
    assert "stable_checks >= 2" in helper
    assert "stSpinner" in helper and "stStatusWidget" in helper
    assert "await page.wait_for_timeout(150)" in helper
    assert "sleep(" not in helper
    click_tabs = source[source.index("async def _click_tabs"):source.index("async def _fresh_visible_tab")]
    assert "_shot_selected_tab_panel" in click_tabs
    assert "complete_surface=True" not in click_tabs
