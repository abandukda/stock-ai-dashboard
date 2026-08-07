from pathlib import Path
from agents.runtime_qa_user_journeys_v40 import (
    RESEARCH_TICKERS,
    INVALID_TICKER,
    ASK_AI_PROMPTS,
    SAFE_DENY_RE,
)


def test_synthetic_research_coverage():
    assert {"NVDA", "AVGO", "CRM"}.issubset(set(RESEARCH_TICKERS))
    assert INVALID_TICKER == "INVALID123"


def test_ask_ai_has_multiple_ticker_aware_prompts():
    assert len(ASK_AI_PROMPTS) >= 3
    for ticker, prompt in ASK_AI_PROMPTS:
        assert ticker in prompt


def test_destructive_controls_are_denied():
    for label in ("Delete", "Logout", "Sell", "Buy", "Reset", "Billing"):
        assert SAFE_DENY_RE.search(label)


def test_runtime_integrates_user_journeys():
    source = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    assert "run_user_journeys" in source
    assert "atlas_user_journeys_v40.json" in source
    assert '"user_journeys": user_journeys' in source
