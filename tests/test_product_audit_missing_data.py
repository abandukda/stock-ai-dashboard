
from agents.product_audit_agent import audit_row


def test_missing_required_component_is_not_treated_as_zero():
    issues = audit_row(
        {
            "ticker": "TEST",
            "committee_verdict": "MONITOR",
            "component_details": {
                "fundamentals": {"status": "NOT_LOADED"},
                "technical": {"status": "AVAILABLE"},
                "valuation": {"status": "AVAILABLE"},
            },
        }
    )
    assert any(
        issue["category"] == "Required Data"
        and "fundamentals" in issue["title"]
        for issue in issues
    )
