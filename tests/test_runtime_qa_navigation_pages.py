from agents.atlas_runtime_qa_v2 import PAGE_NAMES, DEFAULT_URL


def test_expected_navigation_pages_are_registered():
    assert "Volume Intelligence" in PAGE_NAMES
    assert "Developer Center" in PAGE_NAMES
    assert "Research Any Ticker" in PAGE_NAMES


def test_default_deployed_url():
    assert DEFAULT_URL == "https://stock-ai-dashboard.streamlit.app"
