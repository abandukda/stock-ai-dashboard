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
