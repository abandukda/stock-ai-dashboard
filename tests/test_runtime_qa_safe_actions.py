from agents.atlas_runtime_qa_v2 import DESTRUCTIVE_TERMS, DEFAULT_URL

def test_safe_registry():
    assert {"delete","buy","sell","reset"}.issubset(DESTRUCTIVE_TERMS)

def test_default_url():
    assert DEFAULT_URL=="https://stock-ai-dashboard.streamlit.app"
