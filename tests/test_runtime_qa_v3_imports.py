def test_runtime_qa_v3_imports():
    from agents.atlas_runtime_qa_v3 import run_runtime_qa_v3
    assert callable(run_runtime_qa_v3)
