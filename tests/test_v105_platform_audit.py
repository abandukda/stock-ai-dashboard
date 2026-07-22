
from pathlib import Path
from agents.platform_audit_agent_v105 import run_platform_audit
from ui.platform_audit_v105 import render_v105_platform_audit


def test_v105_audit_contract():
    report = run_platform_audit(Path.cwd(), {"ranked_candidates": []})
    assert report["version"] == "V105"
    assert report["read_only"] is True
    assert "status" in report
    assert "findings" in report
    assert "ui_inventory" in report


def test_v105_audit_ui_export():
    assert callable(render_v105_platform_audit)


def test_v105_detects_fixed_coverage():
    pipeline = {
        "ranked_candidates": [
            {"component_coverage_pct": 80}
            for _ in range(6)
        ],
        "research_candidates": [{"ticker": "A"}],
    }
    report = run_platform_audit(Path.cwd(), pipeline)
    titles = [item["title"] for item in report["findings"]]
    assert "Evidence coverage is identical across the universe" in titles
