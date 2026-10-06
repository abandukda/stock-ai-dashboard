from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

from agents.atlas_visual_crawler_v1 import (
    AtlasVisualCrawler,
    GLOBAL_FATALS,
    MOBILE_PAGES,
    REQUIRED_PAGE_VIEWPORTS,
    REQUIRED_RESEARCH_TICKERS,
    EARNINGS_VNEXT_SECTION_LABELS,
    RECOVERY_VNEXT_SECTION_LABELS,
    recovery_candidate_archetypes,
    PRIMARY_VISIBLE_SIGNALS,
    VISUAL_CRAWLER_VERSION,
    RESEARCH_VNEXT_SECTIONS,
    RESEARCH_VNEXT_SECTION_LABELS,
    RESEARCH_COMPLETION_TIMEOUT_SECONDS,
    _research_declared_architecture,
    classify_research_terminal_state,
    certified_research_fields_reconciled,
    normalize_research_action,
    research_submission_failure,
    research_submission_proven,
    VisualResult,
)
from services.vnext_presentation_contract import RESEARCH_VNEXT_VERSION
from agents.product_hardening_certification import ACTIVE_PAGES


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "agents" / "atlas_visual_crawler_v1.py"


def test_research_field_reconciliation_accepts_current_customer_labels_and_values():
    assert certified_research_fields_reconciled({
        "action": "BUY NOW",
        "atlas_fair_value": "$338.82",
        "opportunity": "86.68",
        "decision_confidence": "88.54%",
    }) is True


def test_research_action_normalization_is_presentation_equivalent_only():
    assert normalize_research_action("BUY_NOW") == "BUY_NOW"
    assert normalize_research_action("BUY NOW") == "BUY_NOW"
    assert normalize_research_action("WAIT FOR CONFIRMATION") == "WAIT_FOR_CONFIRMATION"


def test_research_field_reconciliation_accepts_fair_value_display_formats():
    for value in ("$123.40", "$123", "123.4"):
        assert certified_research_fields_reconciled({
            "action": "BUY_NOW", "atlas_fair_value": value,
            "opportunity": "86.68", "decision_confidence": "88.54%",
        }) is True


def test_research_field_reconciliation_rejects_missing_or_unavailable_fields():
    complete = {
        "action": "BUY_NOW", "atlas_fair_value": "$338.82",
        "opportunity": "86.68", "decision_confidence": "88.54%",
    }
    for key in complete:
        missing = dict(complete)
        missing.pop(key)
        assert certified_research_fields_reconciled(missing) is False
    for key in ("atlas_fair_value", "opportunity", "decision_confidence"):
        unavailable = dict(complete)
        unavailable[key] = "Unavailable"
        assert certified_research_fields_reconciled(unavailable) is False


def test_research_field_reconciliation_rejects_unrelated_action_text():
    assert certified_research_fields_reconciled({
        "action": "BUY NOW appears elsewhere on page",
        "atlas_fair_value": "$338.82", "opportunity": "86.68",
        "decision_confidence": "88.54%",
    }) is False


def test_research_field_extractor_uses_ticker_scoped_action_and_metric_nodes():
    source = SOURCE.read_text(encoding="utf-8")
    block = source.split("async def _research_certified_fields", 1)[1].split(
        "def _source_sha", 1
    )[0]
    assert 'st-key-vnext_decision_action_{ticker}' in block
    assert 'data-testid="stMetric"' in block
    assert 'data-testid="stMetricLabel"' in block
    assert 'data-testid="stMetricValue"' in block
    assert '"ATLAS FAIR VALUE": "atlas_fair_value"' in block
    assert '"OPPORTUNITY": "opportunity"' in block
    assert '"DECISION CONFIDENCE": "decision_confidence"' in block


def test_visual_crawler_has_complete_non_blocking_product_scope():
    assert VISUAL_CRAWLER_VERSION == "ATLAS_VISUAL_CRAWLER_V1_1"
    assert set(PRIMARY_VISIBLE_SIGNALS) == set(ACTIVE_PAGES)
    assert set(MOBILE_PAGES) == {
        "Home", "Research Any Ticker", "Today's Opportunities", "Ask AI",
        "Political Intelligence", "Earnings Intelligence", "Full Ranked Scan",
        "Recovery",
    }
    assert GLOBAL_FATALS == {"APP_UNREACHABLE", "AUTHENTICATION_FAILED", "BROWSER_DIED"}
    assert RESEARCH_COMPLETION_TIMEOUT_SECONDS >= 90


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
    assert "name for name in ACTIVE_PAGES" in source
    assert "for ticker in REQUIRED_RESEARCH_TICKERS" in source
    assert "for name in tabs" in source
    assert "for name, node in candidates" in source
    assert "break" not in ast.get_source_segment(source, next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "_required_desktop"
    ))


def _contract_crawler(tmp_path, monkeypatch):
    monkeypatch.setattr(AtlasVisualCrawler, "_source_sha", lambda _self: "a" * 40)
    monkeypatch.setattr(
        "agents.atlas_visual_crawler_v1.full_certification_ticker_matrix",
        lambda _root: {"top15": [], "role_tickers": {}},
    )
    return AtlasVisualCrawler(url="http://example.invalid", output_dir=tmp_path, root=ROOT)


def _result(*, category, page, viewport="desktop", ticker="", status="PASS", required=True):
    return VisualResult(
        category=category, page=page, interaction="contract", expected="pass",
        observed=status, status=status, severity="NONE" if status == "PASS" else "P1",
        elapsed_seconds=0.1, ticker_context=ticker, viewport=viewport,
        required=required,
    )


def _passing_required_results():
    rows = [
        _result(category="PAGE", page=page, viewport=viewport)
        for page, viewport in REQUIRED_PAGE_VIEWPORTS
    ]
    rows.extend(
        _result(category="RESEARCH", page="Research Any Ticker", ticker=ticker)
        for ticker in REQUIRED_RESEARCH_TICKERS
    )
    rows.append(_result(
        category="RESEARCH", page="Research Any Ticker", ticker="NVDA",
        viewport="mobile",
    ))
    return rows


def test_required_home_research_mobile_and_ticker_failures_block(tmp_path, monkeypatch):
    crawler = _contract_crawler(tmp_path, monkeypatch)
    for target in (
        ("PAGE", "Home", "desktop", ""),
        ("PAGE", "Research Any Ticker", "desktop", ""),
        ("PAGE", "Home", "mobile", ""),
        ("RESEARCH", "Research Any Ticker", "desktop", "MSFT"),
    ):
        crawler.results = _passing_required_results()
        category, page, viewport, ticker = target
        for row in crawler.results:
            if (row.category, row.page, row.viewport, row.ticker_context) == target:
                row.status = "FAIL"
                break
        assert crawler._required_completeness()["status"] == "FAIL"


def test_optional_legacy_defects_are_recorded_without_blocking_required_coverage(tmp_path, monkeypatch):
    crawler = _contract_crawler(tmp_path, monkeypatch)
    crawler.results = _passing_required_results()
    crawler.results.extend([
        _result(category="FULL_SCAN", page="Full Ranked Scan", status="FAIL", required=False),
        _result(category="FULL_SCAN_CANDIDATE", page="Full Ranked Scan", status="FAIL", required=False),
    ])
    summary = crawler._summary(final=True)
    assert summary["required_completeness"]["status"] == "PASS"
    assert summary["counts"]["supplementary"]["failed"] == 2
    assert len(summary["defects"]) == 2


def test_required_coverage_never_passes_with_zero_research_or_incomplete_mobile(tmp_path, monkeypatch):
    crawler = _contract_crawler(tmp_path, monkeypatch)
    crawler.results = [
        _result(category="PAGE", page=page, viewport=viewport)
        for page, viewport in REQUIRED_PAGE_VIEWPORTS
    ]
    assert crawler._required_completeness()["status"] == "FAIL"
    crawler.results = [
        row for row in _passing_required_results()
        if not (row.category == "PAGE" and row.viewport == "mobile")
    ]
    assert crawler._required_completeness()["status"] == "FAIL"


def test_required_journeys_run_before_supplementary_desktop_and_mobile():
    source = SOURCE.read_text(encoding="utf-8")
    run = source.split("async def run", 1)[1].split("def _summary", 1)[0]
    assert run.index("_required_desktop") < run.index("_required_mobile")
    assert run.index("_required_mobile") < run.index("_supplementary_desktop")
    assert run.index("_supplementary_desktop") < run.index("_supplementary_mobile")
    assert "except Exception as exc" in source.split("async def _supplementary_desktop", 1)[1]


def test_authentication_and_source_identity_remain_fail_closed():
    workflow = (ROOT / ".github/workflows/atlas-runtime-qa-v3.yml").read_text()
    source = SOURCE.read_text(encoding="utf-8")
    assert "AUTHENTICATION_FAILED" in source
    assert "expected_sha=self.expected_deployed_source_sha" in source
    assert "required_failures" in workflow
    assert "required_completeness" in workflow


def test_visible_customer_evidence_is_primary_and_markers_are_supplemental():
    source = SOURCE.read_text(encoding="utf-8")
    assert "PRIMARY_VISIBLE_SIGNALS" in source
    assert "_visible_primary" in source
    assert "visible and not rendered_exception" in source
    assert "_page_render_complete" in source


def test_earnings_vnext_crawler_contract_is_visible_and_non_blocking():
    source = SOURCE.read_text(encoding="utf-8")
    assert set(EARNINGS_VNEXT_SECTION_LABELS) >= {
        "Recently Reported", "Upcoming Earnings", "Guidance & Estimate Changes",
        "Market Reaction", "ATLAS Decision After Earnings", "Deep Evidence",
    }
    assert "_earnings_vnext_contract" in source
    assert 'data-atlas-earnings-version="ATLAS_EARNINGS_VNEXT_V1"' in source
    assert "Estimate revision direction" in source
    assert "Event-aligned market reaction" in source


def test_recovery_vnext_crawler_contract_is_visible_and_non_blocking():
    source = SOURCE.read_text(encoding="utf-8")
    assert len(RECOVERY_VNEXT_SECTION_LABELS) == 12
    assert set(RECOVERY_VNEXT_SECTION_LABELS) >= {
        "Recovery Snapshot", "Why It Fell", "Evidence of Recovery",
        "Technical Confirmation", "What Invalidates Recovery", "Deep Evidence",
    }
    assert "_recovery_vnext_contract" in source
    assert 'data-atlas-recovery-version="ATLAS_RECOVERY_VNEXT_V1"' in source
    assert "section_count == len(RECOVERY_VNEXT_SECTION_LABELS)" in source
    assert '"Recovery"' in source
    assert "_recovery_candidate_journeys" in source
    assert 'get_by_role("button", name=f"View Investment Case — {ticker}", exact=True)' in source
    assert "recovery_status == research_status" in source
    assert "recommendation_match" in source


def test_recovery_candidate_archetypes_cover_population_and_evidence_dynamically():
    candidates = [
        {"ticker": "AAA", "score": "91", "evidence": "Complete"},
        {"ticker": "BBB", "score": "70", "evidence": "Complete"},
        {"ticker": "CCC", "score": "55", "evidence": "Partial evidence"},
        {"ticker": "DDD", "score": "40", "evidence": "Incomplete"},
    ]
    selected = recovery_candidate_archetypes(candidates)
    by_role = {role: item["ticker"] for role, item in selected}
    assert by_role == {
        "first": "AAA", "middle": "CCC", "last": "DDD",
        "high-evidence": "AAA", "partial-evidence": "CCC",
    }


def test_recovery_crawler_records_independent_candidate_failures_and_continues():
    source = SOURCE.read_text(encoding="utf-8")
    method = source.split("async def _recovery_candidate_journeys", 1)[1].split("async def _current_route_visible", 1)[0]
    assert "for role, candidate in archetypes" in method
    assert "except Exception as exc" in method
    assert 'await self._page_visit(page, "Recovery", viewport=viewport)' in method
    assert "if not drill_down or role not in drill_roles:\n                    continue" in method


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
    assert 'name=re.compile(r"(?:Open Full Research|View Investment Case)"' in source
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


def test_home_crawler_certifies_guidance_vnext_authority_and_layout_contract():
    source = SOURCE.read_text(encoding="utf-8")
    assert "_home_guidance_vnext_contract" in source
    for marker in (
        'home-guidance-vnext', 'market-today', 'atlas-market-read',
        'atlas_action_summary', 'best_opportunities', 'worth_watching',
        'home-actionable-card', 'data-atlas-evidence-status',
    ):
        assert marker in source
    assert "ATLAS Action Summary" in source
    assert "Strongest Opportunities" in source
    assert "Worth Watching" in source
    assert "ATLAS found no stocks meeting the strongest certified opportunity threshold" in source
    assert "ATLAS Fair Value" in source
    assert "Decision Confidence" in source
    assert "document.documentElement.scrollWidth > window.innerWidth" in source
    method = source.split("async def _home_cards", 1)[1].split("async def _open_buy_now_expander", 1)[0]
    assert "except Exception as exc" in method
    assert 'await self._page_visit(page, "Home", viewport=viewport)' in method


def test_production_research_submission_waits_for_stronger_terminal_contract():
    proven, mode = research_submission_proven(
        streamlit_event_frames=1,
        rerun_before=1,
        rerun_after=2,
        submission_marker=False,
        completed_research={},
    )
    assert proven is False
    assert mode == "UNPROVEN"

    proven, mode = research_submission_proven(
        streamlit_event_frames=1,
        rerun_before=1,
        rerun_after=2,
        submission_marker=False,
        completed_research={
            "ticker": True,
            "no_stale_ticker": True,
            "lifecycle_complete": True,
            "vnext": True,
            "certified_fields_reconciled": True,
            "provider_boundary_zero": True,
        },
    )
    assert proven is True
    assert mode == "CERTIFIED_END_TO_END_SUBMISSION"

    proven, mode = research_submission_proven(
        streamlit_event_frames=1,
        rerun_before=1,
        rerun_after=2,
        submission_marker=True,
        completed_research={
            "ticker": True,
            "no_stale_ticker": True,
            "lifecycle_complete": True,
            "vnext": True,
            "certified_fields_reconciled": True,
            "provider_boundary_zero": True,
        },
    )
    assert proven is True
    assert mode == "LEGACY_MARKER_AND_CERTIFIED_COMPLETION"

    source = SOURCE.read_text(encoding="utf-8")
    boundary = source.split("async def _require_submission_boundary", 1)[1].split(
        "def _monitor_research_ticker", 1
    )[0]
    assert "RESEARCH_COMPLETION_TIMEOUT_SECONDS" in boundary
    assert "and submission_marker" not in boundary


def _submission_surface(**overrides):
    surface = {
        "ticker": True,
        "no_stale_ticker": True,
        "lifecycle_complete": True,
        "vnext": True,
        "certified_fields_reconciled": True,
        "provider_boundary_zero": True,
    }
    surface.update(overrides)
    return surface


def test_marker_absent_requires_event_rerun_exact_owner_terminal_and_fields():
    for overrides in (
        {"streamlit_event_frames": 0},
        {"rerun_after": 1},
    ):
        arguments = {
            "streamlit_event_frames": 1,
            "rerun_before": 1,
            "rerun_after": 2,
            "submission_marker": False,
            "completed_research": _submission_surface(),
            **overrides,
        }
        assert research_submission_proven(**arguments) == (False, "UNPROVEN")

    for surface_overrides in (
        {"ticker": False},
        {"no_stale_ticker": False},
        {"lifecycle_complete": False},
        {"vnext": False},
        {"certified_fields_reconciled": False},
        {"provider_boundary_zero": False},
    ):
        assert research_submission_proven(
            streamlit_event_frames=1,
            rerun_before=1,
            rerun_after=2,
            submission_marker=False,
            completed_research=_submission_surface(**surface_overrides),
        ) == (False, "UNPROVEN")


def test_submission_failure_classification_does_not_mislabel_observed_rerun():
    assert research_submission_failure(
        streamlit_event_frames=1,
        rerun_before=1,
        rerun_after=2,
        completed_research=_submission_surface(ticker=False),
    ) == "RESEARCH_TICKER_OWNERSHIP_MISMATCH"
    assert research_submission_failure(
        streamlit_event_frames=1,
        rerun_before=1,
        rerun_after=1,
        completed_research=_submission_surface(),
    ) == "RESEARCH_RERUN_NOT_OBSERVED"
    assert research_submission_failure(
        streamlit_event_frames=0,
        rerun_before=1,
        rerun_after=2,
        completed_research=_submission_surface(),
    ) == "RESEARCH_SUBMISSION_EVENT_NOT_OBSERVED"


def test_required_research_matrix_covers_current_production_contract():
    assert REQUIRED_RESEARCH_TICKERS == ("NVDA", "MSFT", "AVT")
    assert ("Research Any Ticker", "desktop") in REQUIRED_PAGE_VIEWPORTS
    assert ("Research Any Ticker", "mobile") in REQUIRED_PAGE_VIEWPORTS
    source = SOURCE.read_text(encoding="utf-8")
    assert '"certified_fields_reconciled"' in source
    assert '"no_stale_ticker"' in source
    assert 'data-atlas-provider-calls' in (ROOT / "app.py").read_text(encoding="utf-8")


def test_crawler_tracks_ux3b_decision_story_without_restoring_legacy_tabs():
    source = SOURCE.read_text(encoding="utf-8")
    assert '"decision_story"' in source
    for block in (
        "decision-why", "decision-core-metrics", "why-atlas-likes-it",
        "what-stops-atlas", "what-changes-the-thesis", "watching-next",
    ):
        assert block in source
    assert len(RESEARCH_VNEXT_SECTIONS) == 5


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
    assert "self._required_desktop(page), timeout=225" in source
    assert "self._required_mobile(page), timeout=105" in source
    assert "await self._supplementary_desktop(page)" in source
    assert "await self._supplementary_mobile(page)" in source
    assert "await page.set_viewport_size(MOBILE)" in source


class _LifecycleNode:
    def __init__(self, status):
        self.status = status

    async def get_attribute(self, name):
        return self.status if name == "data-atlas-status" else None


class _LifecycleLocator:
    def __init__(self, statuses):
        self.statuses = list(statuses)

    async def count(self):
        return len(self.statuses)

    def nth(self, index):
        return _LifecycleNode(self.statuses[index])


class _LifecycleScope:
    def __init__(self, *, requested, statuses, context=True):
        self.requested = requested
        self.statuses = statuses
        self.context = context

    def locator(self, selector):
        if 'data-atlas-qa="research-container"' in selector:
            for ticker, statuses in self.statuses.items():
                if f'data-atlas-ticker="{ticker}"' in selector:
                    return _LifecycleLocator(statuses)
            return _LifecycleLocator([])
        if 'data-atlas-qa="research-context-v1"' in selector:
            matched = self.context and f'data-atlas-ticker="{self.requested}"' in selector
            return _LifecycleLocator(["context"] if matched else [])
        return _LifecycleLocator([])


def _completed_research_fixture(monkeypatch, tmp_path, *, statuses, exception=False):
    monkeypatch.setattr(AtlasVisualCrawler, "_source_sha", lambda _self: "a" * 40)
    monkeypatch.setattr(
        "agents.atlas_visual_crawler_v1.full_certification_ticker_matrix",
        lambda _root: {"top15": ["NVDA"], "role_tickers": {"etf": "SPY"}},
    )
    crawler = AtlasVisualCrawler(url="http://example.invalid", output_dir=tmp_path, root=ROOT)
    scope = _LifecycleScope(requested="NVDA", statuses=statuses)
    monkeypatch.setattr("agents.atlas_visual_crawler_v1._scopes", lambda _page: [scope])

    async def vnext(_page, _ticker):
        return {
            "version": RESEARCH_VNEXT_VERSION,
            "all_sections": True,
            "ask_cta": True,
            "withheld_terminal": False,
            "publication_allowed": True,
        }

    async def rendered_exception(_page):
        return exception

    monkeypatch.setattr(crawler, "_research_vnext_contract", vnext)
    monkeypatch.setattr("agents.atlas_visual_crawler_v1._has_rendered_exception", rendered_exception)
    async def visible_text(_page):
        return "ATLAS View ATLAS Rating: BUY NOW"
    monkeypatch.setattr("agents.atlas_visual_crawler_v1._visible_text", visible_text)
    return asyncio.run(crawler._completed_research(object(), "NVDA"))


def _terminal(**overrides):
    values = {
        "ticker_present": True,
        "lifecycle_complete": True,
        "authoritative_version": True,
        "five_sections": False,
        "ask_cta": False,
        "withheld_marker": True,
        "publication_allowed": False,
        "published_decision_evidence": False,
        "visible_text": "RATING NOT PUBLISHED ATLAS does not have enough certified evidence to publish a rating for this snapshot.",
        "rendered_exception": False,
        "loading": False,
    }
    values.update(overrides)
    return classify_research_terminal_state(**values)


def test_rating_not_published_is_an_explicit_completed_terminal_state():
    assert _terminal() == "RATING_NOT_PUBLISHED_COMPLETE"


def test_published_research_still_requires_sections_and_ask_cta():
    assert _terminal(
        publication_allowed=True, withheld_marker=False, five_sections=True,
        ask_cta=True, published_decision_evidence=True,
        visible_text="ATLAS View ATLAS Rating: BUY NOW",
    ) == "PUBLISHED_RESEARCH_COMPLETE"
    assert _terminal(
        publication_allowed=True, withheld_marker=False, five_sections=False,
        ask_cta=True, visible_text="ATLAS View",
    ) == "RESEARCH_RENDER_INCOMPLETE"


def test_published_research_rejects_declared_count_when_required_tab_content_is_broken():
    complete_tabs = set(RESEARCH_VNEXT_SECTION_LABELS)
    assert complete_tabs == {
        "ATLAS View", "ATLAS Fair Value", "Live Market & Trade",
        "Additional Context", "Decision Evidence",
    }
    assert not complete_tabs.intersection({
        "Decision", "Fundamentals & Valuation", "Technical & Trade State",
        "Catalysts & Sentiment", "Risk & Evidence",
    })
    assert _research_declared_architecture(5, complete_tabs) is True
    broken_tabs = complete_tabs - {RESEARCH_VNEXT_SECTION_LABELS[-1]}
    # The root still claims five sections, but required Decision Evidence
    # semantic control is absent: certification must fail closed.
    assert _research_declared_architecture(5, broken_tabs) is False
    assert _terminal(
        publication_allowed=True, withheld_marker=False, five_sections=False,
        ask_cta=True, published_decision_evidence=True,
        visible_text="ATLAS View ATLAS Rating: BUY NOW",
    ) == "RESEARCH_RENDER_INCOMPLETE"
    assert _terminal(
        publication_allowed=True, withheld_marker=False, five_sections=True,
        ask_cta=True, published_decision_evidence=False,
        visible_text="ATLAS View",
    ) == "RESEARCH_RENDER_INCOMPLETE"


def test_withheld_terminal_rejects_blank_fake_loading_error_and_missing_version():
    assert _terminal(ticker_present=False) == "RESEARCH_RENDER_INCOMPLETE"
    assert _terminal(withheld_marker=False) == "RESEARCH_RENDER_INCOMPLETE"
    assert _terminal(visible_text="RATING NOT PUBLISHED") == "RESEARCH_RENDER_INCOMPLETE"
    assert _terminal(visible_text="") == "RESEARCH_RENDER_INCOMPLETE"
    assert _terminal(loading=True) == "RESEARCH_RENDER_INCOMPLETE"
    assert _terminal(rendered_exception=True) == "RESEARCH_RENDER_INCOMPLETE"
    assert _terminal(authoritative_version=False) == "RESEARCH_RENDER_INCOMPLETE"


def test_withheld_terminal_rejects_action_fv_potential_pillars_and_deep_case_leaks():
    for leaked in (
        "WATCH — NOT READY YET", "BUY NOW", "BUILD A POSITION", "ATLAS FAIR VALUE",
        "POTENTIAL", "SIX PILLARS", "FULL INVESTMENT CASE",
    ):
        assert _terminal(visible_text=f"RATING NOT PUBLISHED {leaked}") == "RESEARCH_RENDER_INCOMPLETE"


def test_completed_research_uses_later_exact_ticker_complete(monkeypatch, tmp_path):
    result = _completed_research_fixture(
        monkeypatch, tmp_path, statuses={"NVDA": ["loading", "complete"]},
    )
    assert result["complete"] is True
    assert result["terminal_status"] == "complete"


def test_completed_research_rejects_loading_without_completion(monkeypatch, tmp_path):
    result = _completed_research_fixture(
        monkeypatch, tmp_path, statuses={"NVDA": ["loading"]},
    )
    assert result["complete"] is False
    assert result["terminal_status"] == "loading"


def test_completed_research_ignores_other_ticker_completion(monkeypatch, tmp_path):
    result = _completed_research_fixture(
        monkeypatch, tmp_path, statuses={"NVDA": ["loading"], "AAPL": ["complete"]},
    )
    assert result["complete"] is False
    assert result["terminal_status"] == "loading"


def test_completed_research_rejects_stale_complete_followed_by_new_loading(monkeypatch, tmp_path):
    result = _completed_research_fixture(
        monkeypatch, tmp_path, statuses={"NVDA": ["complete", "loading"]},
    )
    assert result["complete"] is False
    assert result["terminal_status"] == "loading"


def test_completed_research_rejects_rendered_exception(monkeypatch, tmp_path):
    result = _completed_research_fixture(
        monkeypatch, tmp_path, statuses={"NVDA": ["loading", "complete"]}, exception=True,
    )
    assert result["complete"] is False
    assert result["terminal_status"] == "complete"
    assert result["rendered_exception"] is True


def test_visual_crawler_certifies_full_scan_vnext_on_desktop_and_mobile():
    source = SOURCE.read_text(encoding="utf-8")
    assert '"Full Ranked Scan", "Recovery"' in source
    assert "_full_scan_vnext_contract" in source
    assert "_full_scan_candidate_journeys" in source
    assert 'data-atlas-full-scan-version="ATLAS_FULL_SCAN_VNEXT_V1"' in source
    assert "data-atlas-production-rank" in source
    assert "data-atlas-filtered-position" in source
    assert "first_mid_last" in source
    assert '("high-evidence", high)' in source
    assert '("partial-evidence", partial)' in source


def test_full_scan_crawler_clicks_visible_exact_ticker_cta_and_reconciles_state():
    source = SOURCE.read_text(encoding="utf-8")
    block = source.split("async def _full_scan_candidate_journeys", 1)[1].split(
        "async def _current_route_visible", 1
    )[0]
    assert 'name=f"View Investment Case — {ticker}"' in block
    assert "scroll_into_view_if_needed" in block
    assert "await button.click" in block
    assert 'self._current_route_visible(page, "Research Any Ticker")' in block
    assert "self._exact_research_ticker(page, ticker)" in block
    assert "candidate[\"decision_status\"] == research_status" in block
    assert 'await self._page_visit(page, "Full Ranked Scan"' in block
