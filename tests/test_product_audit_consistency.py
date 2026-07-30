
from agents.product_audit_agent import audit_row


def test_buy_now_without_upside_is_critical():
    issues = audit_row(
        {
            "ticker": "TEST",
            "committee_verdict": "BUY_NOW",
            "opportunity_score": 75,
            "confidence_pct": 72,
            "component_details": {
                "fundamentals": {"status": "AVAILABLE"},
                "technical": {"status": "AVAILABLE"},
                "valuation": {"status": "AVAILABLE"},
            },
            "expected_return_pct": None,
            "position_size_range": "3–5%",
        }
    )
    assert any(
        issue["severity"] == "CRITICAL"
        and "validated upside" in issue["title"]
        for issue in issues
    )
