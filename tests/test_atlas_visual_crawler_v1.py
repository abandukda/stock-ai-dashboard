from __future__ import annotations

import ast
import json
from pathlib import Path

from agents.atlas_visual_crawler_v1 import (
    AtlasVisualCrawler,
    GLOBAL_FATALS,
    MOBILE_PAGES,
    PRIMARY_VISIBLE_SIGNALS,
    VISUAL_CRAWLER_VERSION,
    RESEARCH_VNEXT_SECTIONS,
    VisualResult,
)
from agents.product_hardening_certification import ACTIVE_PAGES


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agents" / "atlas_visual_crawler_v1.py"


def test_visual_crawler_has_complete_non_blocking_product_scope():
    assert VISUAL_CRAWLER_VERSION == "ATLAS_VISUAL_CRAWLER_V1_1"
    assert set(PRIMARY_VISIBLE_SIGNALS) == set(ACTIVE_PAGES)
    assert set(MOBILE_PAGES) == {
        "Home", "Research Any Ticker", "Today's Opportunities", "Ask AI",
        "Political Intelligence",
    }
    assert GLOBAL_FATALS == {"APP_UNREACHABLE", "AUTHENTICATION_FAILED", "BROWSER_DIED"}


def test_artifacts_are_complete_and_sanitized(tmp_path, monkeypatch):
    monkeypatch.setattr(AtlasVisualCrawler, "_source_sha", lambda _self: "a" * 40)
    monkeypatch.setattr(
        "agents.atlas_visual_crawler_v1.full_certification_ticker_matrix",
        lambda _root: {"top15": ["NVDA"], "role_tickers": {"etf": "SPY"}},
    )
    crawler = AtlasVisualCrawler(url="http://example.invalid", output_dir=tmp_path, root=ROOT)
    crawler.results.append(VisualResult(
        category="PAGE", page="Home", interaction="navigate",
        expected="visible customer content", observed="visible Home",
        status="PASS", severity="NONE", elapsed_seconds=0.2,
    ))
    crawler.results.append(VisualResult(
        category="TAB", page="Research Any Ticker", interaction="Valuation",
        expected="selected", observed="not selected", status="FAIL",
        severity="P2", elapsed_seconds=0.3,
        screenshots=["screenshots/before.png", "screenshots/after.png"],
        exception={"category": "TypeError", "fingerprint": "1234567890abcdef"},
    ))
    crawler.manifest.extend([
        {"path": "screenshots/before.png", "generated": True},
        {"path": "", "generated": False},
    ])
    summary = crawler._write_artifacts(final=True)
    assert summary["counts"]["screenshots"] == {"expected": 2, "generated": 1, "missing": 1}
    assert summary["counts"]["tabs"] == {"attempted": 1, "passed": 0, "failed": 1}
    names = {path.name for path in tmp_path.iterdir()}
    assert {
        "atlas_visual_qa_summary.json", "atlas_visual_qa_matrix.csv",
        "screenshot_manifest.json", "atlas_visual_qa_summary.md",
        "atlas_visual_qa_summary.html",
    }.issubset(names)
    serialized = json.dumps(summary)
    assert "password" not in serialized.lower()
    assert "traceback" not in serialized.lower()


def test_every_interaction_is_independently_recorded_and_no_stop_first_failure():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    assert "for page_name in ACTIVE_PAGES" in source
    assert "for ticker in tickers" in source
    assert "for name in tabs" in source
    assert "for name, node in candidates" in source
    assert "break" not in ast.get_source_segment(source, next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "_desktop"
    ))


def test_visible_customer_evidence_is_primary_and_markers_are_supplemental():
    source = SOURCE.read_text(encoding="utf-8")
    assert "PRIMARY_VISIBLE_SIGNALS" in source
    assert "_visible_primary" in source
    assert "visible and not rendered_exception" in source
    assert "_page_render_complete" in source


def test_research_and_home_require_actual_visible_controls_and_exact_ticker():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'get_by_label("Ticker", exact=True)' in source
    assert 'get_by_role("button", name="Research ticker", exact=True)' in source
    assert "data-atlas-expected-ticker" in source
    assert "destination and exact_ticker and not exception" in source
    assert "INVALID123" in source
    assert "top15" in source
    assert "marker.scroll_into_view_if_needed" not in source
    assert "visible_cta=true" in source
    assert 'name=re.compile(r"Open Full Research"' in source
    assert "exact_ticker.search" in source
    assert "_discover_visible_home_cards" in source
    assert "preceding::*[@data-atlas-interaction-id][1]" in source
    assert "await self._exact_research_ticker(page, ticker)" in source
    assert "prior in text" not in source
    assert set(RESEARCH_VNEXT_SECTIONS) == {
        "decision", "fundamentals-and-valuation", "technical-and-trade-state",
        "catalysts-and-sentiment", "risk-and-evidence",
    }
    assert "_research_vnext_contract" in source
    assert "vnext-five-section-contract" in source
    assert "self.monitor_ticker" in source


def test_supporting_evidence_and_grounding_are_independently_certified():
    source = SOURCE.read_text(encoding="utf-8")
    assert "transaction_date" in source
    assert "disclosure_date" in source
    assert "amount_range" in source
    assert "_supporting_evidence" in source
    assert "unsupported_numeric" in source
    assert "evidence_metadata" in source
    assert "supporting evidence" in source.lower()
    assert "politician" in source.lower()
    assert "trade date" in source.lower()
    assert "temporarily unavailable" in source.lower()
    assert "data-atlas-response-length" in source


def test_tabs_are_reacquired_after_every_streamlit_rerender():
    source = SOURCE.read_text(encoding="utf-8")
    assert "_fresh_visible_tab" in source
    assert "tab = await self._fresh_visible_tab(page, name)" in source
    assert "_selected_tab_panel_has_content" in source
    assert "selected or panel_identity" in source
    assert "list[tuple[str, Any]]" not in ast.get_source_segment(
        source,
        next(
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_click_tabs"
        ),
    )


def test_screenshots_capture_streamlit_scroll_surface_and_visible_card_cta():
    source = SOURCE.read_text(encoding="utf-8")
    assert "_stitched_streamlit_screenshot" in source
    assert '"capture": "streamlit_stitched"' in source
    assert "_shot_locator" in source
    assert "full-report" in source


def test_route_generation_recovery_requires_current_visible_healthy_page():
    source = SOURCE.read_text(encoding="utf-8")
    assert "_current_route_visible" in source
    assert "route_current and visible and not rendered_exception" in source
    assert "route-generation recovery" in source


def test_browser_session_is_shared_between_desktop_and_mobile():
    source = SOURCE.read_text(encoding="utf-8")
    assert source.count("await browser.new_context") == 1
    assert "await self._desktop(page)" in source
    assert "await self._mobile(page)" in source
    assert "await page.set_viewport_size(MOBILE)" in source
