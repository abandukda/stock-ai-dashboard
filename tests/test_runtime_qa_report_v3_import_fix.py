import json
from pathlib import Path

from agents.runtime_qa_report_v3 import (
    load_latest_runtime_qa,
    load_latest_runtime_qa_v3,
    runtime_qa_v3_available,
    summarize_runtime_qa_v3,
)


def test_missing_report_returns_none(tmp_path):
    missing = tmp_path / "missing.json"
    assert load_latest_runtime_qa_v3(missing) is None
    assert runtime_qa_v3_available(missing) is False


def test_valid_report_loads(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            {
                "version": "ATLAS-RUNTIME-QA-V3.3",
                "status": "COMPLETE",
                "audit_valid": True,
                "health_score": 96,
                "pages_inspected": 14,
                "duration_seconds": 123.4,
                "severity_counts": {
                    "CRITICAL": 0,
                    "HIGH": 1,
                    "MEDIUM": 2,
                    "LOW": 3,
                },
            }
        ),
        encoding="utf-8",
    )

    report = load_latest_runtime_qa_v3(path)
    assert report["health_score"] == 96
    assert load_latest_runtime_qa(path) == report

    summary = summarize_runtime_qa_v3(report)
    assert summary["audit_valid"] is True
    assert summary["pages_inspected"] == 14
    assert summary["high"] == 1


def test_malformed_report_does_not_raise(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    assert load_latest_runtime_qa_v3(path) is None
