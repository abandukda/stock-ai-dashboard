from scripts.audit_r2_retained_data_coverage import audit, markdown
from pathlib import Path


def test_audit_requires_field_evidence_before_calling_value_certified():
    result = audit([
        {"ticker": "A", "latest_revenue": 10, "professional_evidence_lineage": {"fields": {"latest_revenue": {"evidence_id": "e1", "period": "2025"}}}},
        {"ticker": "B", "latest_revenue": 20},
    ])
    assert result["fields"]["latest_revenue"]["value"] == 2
    assert result["fields"]["latest_revenue"]["certified"] == 1
    assert result["fields"]["latest_revenue"]["period_bound"] == 1


def test_markdown_explicitly_excludes_qa_context_from_production_authority():
    text = markdown(audit([]), Path("market_full_scan.json"))
    assert "Provider calls: **0**" in text
    assert "QA-scoped contextual bundle" in text
    assert "must not be promoted" in text


def test_audit_discloses_partial_population_and_field_period_lineage():
    result = audit([
        {
            "ticker": "NVDA", "latest_revenue": 10,
            "professional_evidence_lineage": {"fields": {"latest_revenue": {
                "evidence_id": "e1", "period": "FY2026", "frequency": "ANNUAL",
                "provider": "FINNHUB", "unit": "USD",
            }}},
        }
    ], expected_population=6033, source_identity={"source_run_id": "37216506983"})
    assert result["source_population_expected"] == 6033
    assert result["source_population_accessible"] == 1
    assert result["population_completeness_state"] == "SOURCE_ARTIFACT_PARTIAL"
    row = next(item for item in result["field_period_rows"] if item["field_id"] == "latest_revenue")
    assert row == {
        "ticker": "NVDA", "field_id": "latest_revenue", "value_present": True,
        "unit": "USD", "frequency": "ANNUAL", "fiscal_period": "FY2026",
        "provider": "FINNHUB", "evidence_id": "e1", "retained_accessible": True,
        "certified": True, "customer_projected": True,
        "remediation_class": "RETAINED_PROJECTABLE",
    }


def test_audit_never_labels_missing_partial_source_data_as_provider_unavailable():
    result = audit([{"ticker": "AVT"}], expected_population=6033)
    row = next(item for item in result["field_period_rows"] if item["field_id"] == "latest_revenue")
    assert row["remediation_class"] == "NOT_RETAINED_IN_SOURCE"
    assert "PROVIDER" not in row["remediation_class"]
