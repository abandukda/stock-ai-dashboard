from pathlib import Path

from agents.atlas_visual_crawler_v1 import (
    REQUIRED_CUSTOMER_ROUTES,
    REQUIRED_PAGE_VIEWPORTS,
    REQUIRED_PHASE_BUDGET,
    REQUIRED_PHASE_TIMEOUT_SECONDS,
)
from scripts.prepare_report_card_qa_fixture import prepare
from services.prospective_report_card import ProspectiveLedger


ROOT = Path(__file__).resolve().parents[1]
CRAWLER = (ROOT / "agents/atlas_visual_crawler_v1.py").read_text()
WORKFLOW = (ROOT / ".github/workflows/atlas_customer_experience_autonomous_qa.yml").read_text()
PREPARER = (ROOT / "scripts/prepare_customer_experience_qa_evidence.py").read_text()


def test_required_phase_has_exact_customer_routes_and_mobile_coverage() -> None:
    assert REQUIRED_CUSTOMER_ROUTES == ("Home", "Research", "Earnings", "Watchlist", "Ask ATLAS")
    required_mobile = {page for page, viewport in REQUIRED_PAGE_VIEWPORTS if viewport == "mobile"}
    assert required_mobile == {
        "Home", "Research Any Ticker", "Earnings Intelligence",
        "Watchlist Intelligence", "Ask AI",
    }
    assert not {"Recovery", "ETFs", "Full Ranked Scan"} & required_mobile


def test_required_phase_budget_is_explicit_and_below_ceiling() -> None:
    worst_case = sum(
        item["timeout_seconds"] * (item["retries"] + 1)
        for item in REQUIRED_PHASE_BUDGET.values()
    )
    assert worst_case <= REQUIRED_PHASE_TIMEOUT_SECONDS == 480
    assert all(item["retries"] == 0 for item in REQUIRED_PHASE_BUDGET.values())


def test_research_tabs_follow_successful_terminal_completion() -> None:
    completion = CRAWLER.index("completion.get(\"certification_incomplete\")")
    click_tabs = CRAWLER.index("await self._click_tabs(", completion)
    assert click_tabs > completion


def test_required_home_drilldowns_cover_exact_regression_tickers() -> None:
    assert '("NVDA", "MSFT", "CODA")' in CRAWLER
    assert "click_registered={destination}" in CRAWLER
    assert "exact_ticker={exact_ticker}" in CRAWLER


def test_failed_crawls_still_reach_consolidation_and_classification() -> None:
    assert "id: required_browser\n        continue-on-error: true" in WORKFLOW
    assert "id: required_report_card\n        continue-on-error: true" in WORKFLOW
    assert "Bind required browser evidence to governed authority\n        if: always()" in WORKFLOW
    assert "customer_required_phase.json" in WORKFLOW


def test_report_card_signal_digest_and_privacy_are_required() -> None:
    assert "crawl_report_card_durable_ui.py" in WORKFLOW
    assert "ATLAS_INTERNAL_REPORT_CARD_UI_ENABLED: \"true\"" in WORKFLOW
    assert "ATLAS_VIEWER_QA_PASSWORD" in WORKFLOW
    assert "report_card_signal_detail" in PREPARER
    assert "customer_report_card_off" in PREPARER


def test_report_card_browser_fixture_is_ephemeral_integral_and_backed_up(tmp_path) -> None:
    ledger_path = prepare(tmp_path / "primary", tmp_path / "backup")
    ledger = ProspectiveLedger(ledger_path)
    assert ledger.verify() != "GENESIS"
    assert len(ledger.rows("SIGNAL")) == 1
    assert list((tmp_path / "backup").glob("report-card-*.sqlite3"))


def test_zero_provider_run_does_not_claim_live_price_certification() -> None:
    assert "ZERO_PROVIDER_RENDERED_CLASSIFICATION_ONLY" in PREPARER
    assert 'ATLAS_QA_PROVIDER_CALLS_ALLOWED: "0"' in WORKFLOW


def test_supplementary_phase_is_non_blocking_and_runs_after_required_certification() -> None:
    required = WORKFLOW.index("Required-first customer surface certification")
    certify = WORKFLOW.index("Consolidate exact-authority certification")
    supplementary = WORKFLOW.index("Supplementary non-blocking visual findings")
    assert required < certify < supplementary
    assert "if: steps.certify.outcome == 'success'" in WORKFLOW
    assert "--phase supplementary" in WORKFLOW
