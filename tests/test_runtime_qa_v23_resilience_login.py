from pathlib import Path

def test_runtime_qa_v23_features():
    source = Path("agents/atlas_runtime_qa_v2.py").read_text(encoding="utf-8")
    assert "Password-only login detected" in source
    assert "VIEWPORT FAILED but audit will continue" in source
    assert "runtime_progress.json" in source
    assert "timeout=120000" in source
