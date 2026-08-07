from pathlib import Path


def test_enterprise_workflow_runs_on_push_and_schedule():
    source = Path(".github/workflows/atlas-runtime-qa-v3.yml").read_text(encoding="utf-8")
    assert "Atlas QA Enterprise" in source
    assert "push:" in source
    assert "schedule:" in source
    assert source.count('cron: "') >= 3
    assert "timeout-minutes: 30" in source
    assert "agents/runtime_qa_user_journeys_v40.py" in source
