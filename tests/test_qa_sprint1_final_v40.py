from pathlib import Path


def test_final_sprint_one_capabilities_present():
    runtime = Path("agents/atlas_runtime_qa_v3.py").read_text(encoding="utf-8")
    journeys = Path("agents/runtime_qa_user_journeys_v40.py").read_text(encoding="utf-8")
    required_runtime = [
        "Visual Formatting",
        "audit_summary_collection",
        "run_user_journeys",
        "failed_requests",
        "console_errors",
        "performance",
    ]
    for token in required_runtime:
        assert token in runtime

    required_journeys = [
        "Navigation coverage",
        "Research Any Ticker",
        "Ask AI",
        "INVALID123",
        "Responsive mobile",
        "horizontal overflow",
    ]
    for token in required_journeys:
        assert token in journeys
