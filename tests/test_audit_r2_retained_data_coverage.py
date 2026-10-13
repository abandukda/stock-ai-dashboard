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
