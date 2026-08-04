from agents.code_contract_mapper_v3 import discover_navigation_from_app


def test_navigation_fallback_contains_volume():
    pages = discover_navigation_from_app("does-not-exist.py")
    assert "Volume Intelligence" in pages
    assert "Developer Center" in pages
