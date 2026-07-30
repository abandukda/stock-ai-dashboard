
from agents.product_audit_agent import audit_navigation


def test_volume_and_developer_pages_are_required():
    issues = audit_navigation(["Home"])
    titles = [item["title"] for item in issues]
    assert "Required page is not exposed: Volume Intelligence" in titles
    assert "Required page is not exposed: Developer Center" in titles
