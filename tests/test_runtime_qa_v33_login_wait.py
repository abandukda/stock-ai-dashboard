from pathlib import Path


def test_login_wait_allows_slow_streamlit_startup():
    source = Path('agents/atlas_runtime_qa_v3.py').read_text(encoding='utf-8')
    assert 'LOGIN_TIMEOUT_SECONDS = 240' in source
    assert 'timeout=300' in source


def test_login_supports_streamlit_text_input_and_secret_cleanup():
    source = Path('agents/atlas_runtime_qa_v3.py').read_text(encoding='utf-8')
    assert '[data-testid="stTextInput"] input' in source
    assert 'configured_secret_length' in source
    assert 'configured viewer password length' in source


def test_workflow_allows_full_authenticated_scan():
    source = Path('.github/workflows/atlas-runtime-qa-v3.yml').read_text(encoding='utf-8')
    assert 'timeout-minutes: 20' in source
    assert 'python -u -m agents.atlas_runtime_qa_v3' in source
