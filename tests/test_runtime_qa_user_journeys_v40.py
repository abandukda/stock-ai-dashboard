from pathlib import Path
from agents.runtime_qa_user_journeys_v40 import (
    RESEARCH_TICKERS,
    INVALID_TICKER,
    ASK_AI_PROMPTS,
    SAFE_DENY_RE,
    PAGE_READY_TEXT,
)


def test_synthetic_research_coverage():
    assert {"NVDA", "AAPL", "SPY"}.issubset(set(RESEARCH_TICKERS))
    assert INVALID_TICKER == "INVALID123"


def test_ask_ai_has_multiple_ticker_aware_prompts():
    assert len(ASK_AI_PROMPTS) == 6
    for ticker, prompt in ASK_AI_PROMPTS:
        assert ticker in prompt


def test_destructive_controls_are_denied():
    for label in ("Delete", "Logout", "Sell", "Buy", "Reset", "Billing"):
        assert SAFE_DENY_RE.search(label)


def test_explicit_state_markers_drive_research_and_ask_ai():
    app = Path("app.py").read_text(encoding="utf-8")
    journeys = Path("agents/runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="research-container"' in app
    assert 'data-atlas-qa="ask-ai-response"' in app
    assert "typed_ticker" in app and "active_research_ticker" in app
    assert "_wait_for_qa_state" in journeys
    assert '"research-container"' in journeys and '"ask-ai-response"' in journeys


def test_invalid_ticker_is_expected_error_pass_and_no_destructive_fallback():
    source = Path("agents/runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")
    assert 'expected_status = "error" if ticker == INVALID_TICKER else "complete"' in source
    assert '"PASS" if invalid_handled and marker_ready else "FAIL"' in source
    assert "SAFE_DENY_RE.search(label)" in source


def test_runtime_integrates_user_journeys():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert "run_user_journeys" in source
    assert "atlas_user_journeys_v40.json" in source
    assert '"user_journeys": user_journeys' in source


def test_navigation_requires_selected_control_and_page_specific_content():
    source = Path("agents/runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")
    assert "await control.is_checked()" in source
    assert "selected and page_ready" in source
    assert 'return False, time.monotonic() - started' in source
    assert PAGE_READY_TEXT["Research Any Ticker"].search(
        "Enter a ticker to open current Atlas research."
    )
    assert not PAGE_READY_TEXT["Research Any Ticker"].search("Earnings Intelligence")
    assert PAGE_READY_TEXT["Ask AI"].search("Ask about a ticker or ranking")
    assert not PAGE_READY_TEXT["Ask AI"].search("Live Atlas Research")
