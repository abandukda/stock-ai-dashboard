from pathlib import Path

from ui.report_card_preview import customer_report_card_preview


ROOT = Path(__file__).resolve().parents[1]


def test_report_card_preview_defaults_to_honest_pending_state():
    preview = customer_report_card_preview()
    assert preview["state"] == "PENDING"
    assert "pending" in preview["title"].lower()
    assert "realized returns" in preview["body"]


def test_report_card_preview_requires_all_publication_gates():
    base = {"customer_visible": True, "public_performance_claims_allowed": True,
            "published_observation_count": 1}
    assert customer_report_card_preview(base)["state"] == "AVAILABLE"
    for key in ("customer_visible", "public_performance_claims_allowed"):
        candidate = dict(base)
        candidate[key] = False
        assert customer_report_card_preview(candidate)["state"] == "PENDING"
    assert customer_report_card_preview({**base, "published_observation_count": 0})["state"] == "PENDING"


def test_customer_surfaces_share_premium_page_hierarchy():
    design = (ROOT / "ui" / "atlas_design_system.py").read_text(encoding="utf-8")
    research = (ROOT / "ui" / "customer_research_v2.py").read_text(encoding="utf-8")
    watchlist = (ROOT / "ui" / "watchlist_vnext.py").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert ".atlas-page-hero" in design
    assert ".atlas-report-preview" in design
    assert "atlas-page-hero-research" in research
    assert "atlas-page-hero-watchlist" in watchlist
    assert "atlas-page-hero-ask" in app


def test_pending_preview_never_contains_performance_numbers():
    preview = customer_report_card_preview({"published_observation_count": 99})
    joined = " ".join(preview.values())
    assert preview["state"] == "PENDING"
    assert "%" not in joined
    assert "success rate" not in joined.lower()


def test_customer_report_card_projection_exposes_only_public_outcome_counts():
    preview = customer_report_card_preview({
        "customer_visible": True, "public_performance_claims_allowed": True,
        "published_observation_count": 4, "published_signal_count": 3,
        "measured_signal_count": 2, "successful_signal_count": 1,
        "unsuccessful_signal_count": 1, "pending_signal_count": 1,
        "ledger_tip_digest": "must-not-leak", "backup_path": "/protected/report-card.sqlite3",
    })
    assert preview["state"] == "AVAILABLE"
    assert (preview["tracked"], preview["measured"], preview["successful"],
            preview["unsuccessful"], preview["pending"]) == ("3", "2", "1", "1", "1")
    rendered = " ".join(preview.values())
    assert "must-not-leak" not in rendered and "/protected" not in rendered


def test_invalid_or_unapproved_report_card_counts_fail_to_pending():
    for count in (-1, True, "not-a-count"):
        preview = customer_report_card_preview({
            "customer_visible": True, "public_performance_claims_allowed": True,
            "published_observation_count": count,
        })
        assert preview["state"] == "PENDING"
        assert preview["tracked"] == "Not public"


def test_integrated_visual_gate_uses_approved_tokens_and_components():
    design = (ROOT / "ui" / "atlas_design_system.py").read_text(encoding="utf-8")
    for token in ("#080F1D", "#0C1627", "#111E32", "#17263D", "#26364D",
                  "#F2F6FC", "#99ABC4", "#37C6B5", "#6A9EFF", "#43C995",
                  "#F17883", "#F0BC68", "--atlas-radius:14px", "--atlas-gap:20px"):
        assert token in design
    for component in ("atlas-shell", "atlas-section-header", "atlas-metric-card",
                      "atlas-opportunity-card", "atlas-ai-insight-panel", "atlas-financial-chart",
                      "atlas-evidence-badge", "atlas-freshness-indicator",
                      "atlas-report-card-summary", "atlas-empty-state"):
        assert component in design


def test_home_command_center_is_responsive_at_required_mobile_widths():
    home = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert 'data-atlas-qa="home-command-deck"' in home
    assert "MARKET PULSE" in home
    assert "@media(max-width:700px)" in home
    assert "@media(max-width:420px)" in home
    assert "COMPANY SPOTLIGHT" not in home
    # The governed Home contract features three ideas, with the complete list retained.
    assert "enumerate(actionable[:3])" in home
    assert "remaining = all_actionable[3:]" in home
    assert "View all {len(all_actionable)} BUY NOW opportunities" in home
    assert "render_customer_report_card_preview" in home


def test_visual_gate_has_keyboard_and_high_contrast_fallbacks():
    design = (ROOT / "ui" / "atlas_design_system.py").read_text(encoding="utf-8")
    assert ":focus-visible" in design
    assert "@media(forced-colors:active)" in design
    preview = (ROOT / "ui" / "report_card_preview.py").read_text(encoding="utf-8")
    assert "SPY comparison pending" in preview
    assert "Source-bound observations required" in preview


def test_rendered_pending_preview_hides_unapproved_counts_and_preserves_off_state():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
from ui.report_card_preview import render_customer_report_card_preview
render_customer_report_card_preview({'published_observation_count': 987654321, 'published_signal_count': 987654321})
''').run()
    assert not app.exception
    rendered = '\n'.join(str(item.value) for item in app.markdown)
    assert 'data-atlas-report-card-preview-state="PENDING"' in rendered
    assert 'Public activation OFF' in rendered
    assert 'Returns and SPY comparison pending' in rendered
    assert '987654321' not in rendered
    assert '<details><summary>How performance will be measured</summary>' in rendered
