from pathlib import Path

from agents.atlas_runtime_qa_v3 import research_performance_classification
from agents import runtime_qa_user_journeys_v40 as journeys


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
LIVE = (ROOT / "engines/live_research_engine.py").read_text(encoding="utf-8")
QA = (ROOT / "agents/runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")


def test_research_submission_does_not_force_family_cache_bypass():
    assert "force_refresh=False, api_key=fmp_api_key" in LIVE
    assert "Do not block a complete FMP context on a second legacy" in LIVE
    assert "canonical_fmp_available" in LIVE


def test_one_request_records_one_acquisition_and_exposes_sanitized_performance():
    assert 'atlas_research_acquisition_invocations_{ticker}' in APP
    assert 'data-atlas-qa="research-performance"' in APP
    assert 'data-atlas-provider-calls=' in APP
    assert "family_timings" in APP
    assert "provider payload" not in APP[APP.index('data-atlas-qa="research-performance"'):][:1200].lower()


def test_prior_ticker_exception_identity_is_sanitized_and_ticker_specific():
    assert "_rendered_exception_identity" in QA
    assert '"fingerprint": fingerprint' in QA
    assert '"ticker": ticker' in QA
    assert '"stage": stage' in QA
    body = QA[QA.index("async def _rendered_exception_identity"):QA.index("async def _page_contract_ready")]
    assert "traceback" not in body.lower()
    assert "inner_html" not in body


def test_invalid_ticker_is_rejected_before_research_acquisition():
    validation = APP.index("if submitted and not re.fullmatch")
    acquisition = APP.index("if submitted or auto_live:", validation)
    assert validation < acquisition


def test_spy_corporate_bypass_remains_in_acquisition_contract():
    acquisition = (ROOT / "services/fmp_research_acquisition.py").read_text(encoding="utf-8")
    assert 'if security != "ETF":' in acquisition


def test_six_ask_questions_reuse_context_keyed_report():
    assert 'atlas_ask_report_{ticker}_{_context_identity}' in APP
    assert "if _context_rebuilt:" in APP
    assert 'data-atlas-qa="ask-performance"' in APP
    assert 'data-atlas-context-rebuilt=' in APP


def test_performance_taxonomy_distinguishes_product_from_wait_defect():
    assert research_performance_classification(
        canonical_ready=False, render_complete=False, provider_seconds=45, wait_seconds=45
    ) == "PRODUCT_PERFORMANCE_DEFECT"
    assert research_performance_classification(
        canonical_ready=True, render_complete=False, provider_seconds=2, wait_seconds=45
    ) == "QA_WAIT_DEFECT"


def test_research_and_ask_budgets_are_not_increased():
    assert journeys.RESEARCH_STEP_BUDGET_SECONDS == 45
    assert journeys.ASK_STEP_BUDGET_SECONDS == 30
