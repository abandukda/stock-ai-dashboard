from pathlib import Path

from agents.atlas_deep_qa import (
    PAGES,
    UX_CLASSES,
    classify_fields,
    consistency_findings,
    domain_health,
    root_causes,
    representative_tickers,
)


def test_deep_qa_covers_every_primary_page_and_required_ux_classes():
    assert len(PAGES) == 14
    assert "Developer Center" in PAGES
    assert {"UNEXPLAINED_CONTROL", "AMBIGUOUS_METRIC", "MISSING_HELP_TEXT", "NO_NEXT_ACTION"} <= UX_CLASSES


def test_missing_report_date_makes_zero_eps_suspicious():
    fields = classify_fields({"ticker": "NVDA", "Reported EPS": 0.0}, "NVDA")
    by = {item["field"]: item for item in fields}
    assert by["latest_reported_date"]["status"] == "MISSING"
    assert by["reported_eps"]["status"] == "SUSPICIOUS_ZERO"
    findings = consistency_findings("NVDA", fields)
    assert any(item["category"] == "POSSIBLE_FALSE_ZERO" for item in findings)


def test_zero_requires_explicit_provenance_to_be_valid():
    fields = classify_fields({
        "ticker": "AR",
        "Reported EPS": 0,
        "Latest Reported": "2026-08-01",
        "provenance": {"Reported EPS": {"source_value": 0, "provider": "test"}},
    }, "AR")
    assert next(item for item in fields if item["field"] == "reported_eps")["status"] == "ZERO_VALID"


def test_root_causes_group_occurrences_instead_of_exploding_issue_count():
    completeness = [
        {"ticker": ticker, "group": "financial", "field": "roic", "status": "MISSING", "mapped_key": "", "provider": "UNKNOWN"}
        for ticker in ("NVDA", "CRM", "AVGO", "AR")
    ]
    roots = root_causes(completeness, [], {}, [], [])
    assert len(roots) == 1
    assert roots[0]["occurrence_count"] == 4
    assert roots[0]["affected_tickers"] == ["AR", "AVGO", "CRM", "NVDA"]


def test_health_uses_unique_roots_not_occurrence_count():
    root = {"severity": "HIGH", "category": "Required Data", "affected_tickers": ["NVDA"] * 100}
    score = domain_health([root], 14, True)
    assert score["domains"]["Data Completeness"] > 0
    assert "unique root causes" in score["calculation"]


def test_developer_center_is_self_explanatory():
    source = Path("ui/developer_center.py").read_text(encoding="utf-8")
    for text in (
        "Internal quality-control center",
        "Simulates real user activity",
        "repeated explanations",
        "Groups detected problems into root causes",
        "Shows how Atlas QA tests are executed",
        "Reset Filters",
        "Next action",
        "Deep QA Domain Health",
        "unique root causes weighted by severity",
    ):
        assert text in source


def test_representative_selection_uses_saved_membership_without_recomputing_decisions():
    rows = {
        "NVDA": {"_qa_sources": ["market_full_scan.json"]},
        "CRM": {"_qa_sources": ["market_full_scan.json"]},
        "AVGO": {"_qa_sources": ["market_full_scan.json"]},
        "AR": {"_qa_sources": ["market_full_scan.json"]},
        "REC": {"_qa_sources": ["recovery_scan.json"]},
        "WATCH": {"_qa_sources": ["watchlist_scan.json"]},
        "EARN": {"next_earnings_date": "2026-09-01"},
        "VOL": {"volume_ratio": 2.1},
    }
    assert {"REC", "WATCH", "EARN", "VOL"} <= set(representative_tickers(rows))
