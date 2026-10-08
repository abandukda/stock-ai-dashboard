from pathlib import Path

from ui.atlas_design_system import action_badge, action_class


ROOT = Path(__file__).resolve().parents[1]


def test_action_visual_language_covers_every_governed_state():
    states = (
        "BUY_NOW", "BUILD_A_POSITION", "WAIT_FOR_BETTER_ENTRY",
        "WAIT_FOR_CONFIRMATION", "WATCH_NOT_READY", "AVOID",
        "RATING_NOT_PUBLISHED",
    )
    for state in states:
        badge = action_badge(state)
        assert action_class(state) in badge
        assert state.replace("_", " ").title() in badge
        assert "<i aria-hidden=\"true\"></i>" in badge


def test_design_system_uses_semantic_anchors_not_generated_ids():
    source = (ROOT / "ui" / "atlas_design_system.py").read_text()
    assert "data-atlas-qa" in source
    assert "data-testid" in source
    assert "prefers-reduced-motion" in source
    assert "nth-child" not in source
    assert "#root >" not in source


def test_customer_surfaces_expose_polish_anchors_without_authority_changes():
    sources = {
        "app": (ROOT / "app.py").read_text(),
        "research": (ROOT / "ui" / "research_vnext.py").read_text(),
        "earnings": (ROOT / "ui" / "earnings_vnext.py").read_text(),
        "watchlist": (ROOT / "ui" / "watchlist_vnext.py").read_text(),
        "report_card": (ROOT / "ui" / "internal_report_card.py").read_text(),
    }
    assert 'data-atlas-qa="ask-atlas-vnext"' in sources["app"]
    assert "Certified equity research" in sources["research"]
    assert "Executive evidence review" in sources["earnings"]
    assert "atlas-watchlist-card-anchor" in sources["watchlist"]
    assert "atlas-report-card-hero" in sources["report_card"]
    assert "customer_authority(row)" in sources["watchlist"]


def test_internal_report_card_remains_customer_hidden():
    source = (ROOT / "ui" / "internal_report_card.py").read_text()
    assert 'data-atlas-customer-visible="false"' in source
    assert "Not a public performance claim" in source
