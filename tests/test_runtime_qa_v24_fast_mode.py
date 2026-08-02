from pathlib import Path

def test_fast_mode_defaults():
    source = Path("agents/atlas_runtime_qa_v2.py").read_text(encoding="utf-8")
    assert "DEFAULT_SCREENSHOTS = False" in source
    assert "SCREENSHOT_TIMEOUT_MS = 3500" in source
    assert "--screenshots" in source
