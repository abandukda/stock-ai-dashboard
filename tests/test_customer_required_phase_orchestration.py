import ast
import json
from pathlib import Path

from scripts.prepare_report_card_qa_fixture import prepare
from scripts.prepare_customer_experience_qa_evidence import _r1_acceptance
from services.prospective_report_card import ProspectiveLedger


ROOT = Path(__file__).resolve().parents[1]
CRAWLER = (ROOT / "agents/atlas_visual_crawler_v1.py").read_text()
WORKFLOW = (ROOT / ".github/workflows/atlas_customer_experience_autonomous_qa.yml").read_text()
PREPARER = (ROOT / "scripts/prepare_customer_experience_qa_evidence.py").read_text()
APP = (ROOT / "app.py").read_text()


def _crawler_constant(name: str):
    module = ast.parse(CRAWLER)
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            expression = node.value
            if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name) and expression.func.id == "frozenset":
                expression = expression.args[0]
            return ast.literal_eval(expression)
    raise AssertionError(f"missing crawler constant: {name}")


def test_required_phase_has_exact_customer_routes_and_mobile_coverage() -> None:
    REQUIRED_CUSTOMER_ROUTES = _crawler_constant("REQUIRED_CUSTOMER_ROUTES")
    REQUIRED_PAGE_VIEWPORTS = frozenset(_crawler_constant("REQUIRED_PAGE_VIEWPORTS"))
    assert REQUIRED_CUSTOMER_ROUTES == ("Home", "Research", "Watchlist", "Ask ATLAS")
    required_mobile = {page for page, viewport in REQUIRED_PAGE_VIEWPORTS if viewport == "mobile"}
    assert required_mobile == {
        "Home", "Research Any Ticker", "Watchlist Intelligence", "Ask AI",
    }
    assert not {"Recovery", "ETFs", "Full Ranked Scan"} & required_mobile


def test_customer_role_visual_evidence_adds_governed_360_without_weakening_390_gate() -> None:
    assert 'MOBILE = {"width": 390, "height": 844}' in CRAWLER
    assert 'NARROW_MOBILE = {"width": 360, "height": 800}' in CRAWLER
    assert 'viewport="mobile_360"' in CRAWLER
    assert 'for ticker in ("NVDA", "CRC")' in CRAWLER
    assert "CUSTOMER_ROLE_WATCHLIST_FAILED_MOBILE_360" in CRAWLER


def test_customer_navigation_keeps_all_four_routes_visible_at_390_and_360() -> None:
    app = Path("app.py").read_text(encoding="utf-8")
    assert "@media(max-width:420px)" in app
    assert 'justify-content:space-between;gap:.08rem!important' in app
    assert 'font-size:.64rem!important' in app


def test_required_phase_budget_is_explicit_and_below_ceiling() -> None:
    REQUIRED_PHASE_BUDGET = _crawler_constant("REQUIRED_PHASE_BUDGET")
    REQUIRED_PHASE_TIMEOUT_SECONDS = _crawler_constant("REQUIRED_PHASE_TIMEOUT_SECONDS")
    worst_case = sum(
        item["timeout_seconds"] * (item["retries"] + 1)
        for item in REQUIRED_PHASE_BUDGET.values()
    )
    assert worst_case <= REQUIRED_PHASE_TIMEOUT_SECONDS == 720
    assert all(item["retries"] == 0 for item in REQUIRED_PHASE_BUDGET.values())


def test_research_tabs_follow_successful_terminal_completion() -> None:
    completion = CRAWLER.index("completion.get(\"certification_incomplete\")")
    click_tabs = CRAWLER.index("await self._click_tabs(", completion)
    assert click_tabs > completion


def test_required_home_drilldowns_cover_exact_regression_tickers() -> None:
    assert '("NVDA", "MSFT", "CODA")' in CRAWLER
    assert "click_registered={destination}" in CRAWLER
    assert "exact_ticker={exact_ticker}" in CRAWLER
    assert 'data-atlas-qa="home-guidance-research-cta"' in CRAWLER
    assert "View Research" in CRAWLER


def test_full_certified_inventory_retains_research_drilldowns() -> None:
    home = (ROOT / "ui/home_guidance_vnext.py").read_text(encoding="utf-8")
    assert 'with st.expander(f"View all certified opportunities ({len(actionable)})"' in home
    assert '_open_research(ticker, f"home_all_certified_{index}_{ticker}", compact=True)' in home


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


def test_r1_visual_acceptance_is_an_explicit_fail_closed_b1_b18_gate() -> None:
    for index in range(1, 19):
        assert f'"B{index}"' in PREPARER
    assert 'all(item["status"] == "PASS" for item in results_out)' in PREPARER
    assert 'r1_acceptance["status"] == "PASS"' in PREPARER
    assert 'incomplete_published' in PREPARER
    assert 'get("completed_research_predicates")' in PREPARER
    assert '!= "PUBLISHED_RESEARCH_COMPLETE"' in PREPARER


def test_b18_fails_when_published_submission_contains_incomplete_predicate() -> None:
    required = {
        "required_completeness": {"status": "PASS"},
        "results": [{
            "category": "RESEARCH_SUBMISSION_BOUNDARY",
            "interaction": "submit-event-and-rerun",
            "ticker_context": "NVDA",
            "viewport": "mobile",
            "required": True,
            "status": "PASS",
            "observed": json.dumps({
                "publication_allowed": True,
                "research_terminal_state": "RESEARCH_RENDER_INCOMPLETE",
                "completed_research_predicates": {"complete": False},
            }),
        }],
        "screenshot_manifest": [],
    }
    acceptance = _r1_acceptance(required, {}, [])
    b18 = next(item for item in acceptance["criteria"] if item["criterion"] == "B18")
    assert b18["status"] == "FAIL"
    assert acceptance["status"] == "FAIL"


def test_b18_uses_final_structured_state_not_intermediate_settlement_history() -> None:
    required = {
        "required_completeness": {"status": "PASS"},
        "results": [{
            "category": "RESEARCH_SUBMISSION_BOUNDARY",
            "interaction": "submit-event-and-rerun",
            "ticker_context": "NVDA",
            "viewport": "mobile",
            "required": True,
            "status": "PASS",
            "observed": json.dumps({
                "publication_allowed": True,
                "research_terminal_state": "PUBLISHED_RESEARCH_COMPLETE",
                "completed_research_predicates": {"complete": True},
                "settlement_observations": [{
                    "complete": False,
                    "research_terminal_state": "RESEARCH_RENDER_INCOMPLETE",
                }, {
                    "complete": True,
                    "research_terminal_state": "PUBLISHED_RESEARCH_COMPLETE",
                }],
            }),
        }],
        "screenshot_manifest": [],
    }
    acceptance = _r1_acceptance(required, {}, [])
    b18 = next(item for item in acceptance["criteria"] if item["criterion"] == "B18")
    assert b18["status"] == "PASS"


def test_customer_role_visual_evidence_covers_launch_surfaces_and_exact_viewports() -> None:
    assert 'DESKTOP = {"width": 1440, "height": 900}' in CRAWLER
    assert 'MOBILE = {"width": 390, "height": 844}' in CRAWLER
    assert "_customer_role_visual_evidence" in CRAWLER
    assert 'for ticker in ("NVDA", "AVT", "CRC")' in CRAWLER
    assert 'interaction="customer-copy-contract"' in CRAWLER


def test_research_timeout_is_owned_by_submission_settlement_and_preserves_diagnostics() -> None:
    assert "settlement_deadline = time.monotonic() + RESEARCH_COMPLETION_TIMEOUT_SECONDS" in CRAWLER
    assert '"dom_marker_inventory": marker_inventory' in CRAWLER
    assert '"research_input_value":' in CRAWLER
    assert "wait_for(self._submit_research" not in CRAWLER


def test_qa_app_defaults_to_the_governed_materialized_runtime() -> None:
    assert '"audit_results/full_qa/runtime"' in APP
    assert 'if os.getenv("ATLAS_QA_MODE", "").strip().lower()' in APP
    assert "DATA_DIR = Path(DATA_DIR)" in APP


def test_supplementary_phase_is_non_blocking_and_runs_after_required_certification() -> None:
    required = WORKFLOW.index("Required-first customer surface certification")
    certify = WORKFLOW.index("Consolidate exact-authority certification")
    supplementary = WORKFLOW.index("Supplementary non-blocking visual findings")
    assert required < certify < supplementary
    assert "if: steps.certify.outcome == 'success'" in WORKFLOW
    assert "--phase supplementary" in WORKFLOW
