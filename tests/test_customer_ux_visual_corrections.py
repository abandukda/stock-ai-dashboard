from pathlib import Path

import pytest

from engines.home_guidance_story_v1 import customer_action_presentation
from services.vnext_presentation_contract import CUSTOMER_ACTION_LABELS, PRESENTATION_TRUST_TIERS
from ui.home_guidance_vnext import _compact_card_narrative, _compact_primary_risk, _compact_reason, _display
from ui.research_vnext import _customer_fair_value, _customer_potential


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("state", "label"),
    tuple(CUSTOMER_ACTION_LABELS.items()),
)
def test_every_canonical_action_has_one_customer_label(state, label):
    assert customer_action_presentation(state)["label"] == label
    assert _display(state) == label


def test_certified_fair_value_and_potential_override_stale_report_values():
    report = {
        "atlas_fair_value": None,
        "atlas_expected_return_pct": 999,
        "certified_customer_evaluation": {
            "fields": {
                "atlas_fair_value": {"value": 42.13, "certification_status": "CERTIFIED"},
                "atlas_upside_pct": {"value": 35.0, "certification_status": "CERTIFIED"},
            }
        },
    }
    assert _customer_fair_value(report) == 42.13
    assert _customer_potential(report) == 35.0


def test_high_uncertainty_certification_remains_customer_publishable():
    report = {"certified_customer_evaluation": {"fields": {
        "atlas_fair_value": {"value": 42.13, "certification_status": "CERTIFIED_HIGH_UNCERTAINTY"},
        "atlas_upside_pct": {"value": 193.0, "certification_status": "CERTIFIED_HIGH_UNCERTAINTY"},
    }}}
    assert _customer_fair_value(report) == 42.13
    assert _customer_potential(report) == 193.0


def test_uncertified_fair_value_cannot_leave_stale_potential_visible():
    report = {
        "atlas_fair_value": 42.13,
        "atlas_expected_return_pct": 35.0,
        "certified_customer_evaluation": {
            "fields": {
                "atlas_fair_value": {"value": None, "certification_status": "DATA_UNAVAILABLE"},
                "atlas_upside_pct": {"value": 35.0, "certification_status": "REVIEW_REQUIRED"},
            }
        },
    }
    assert _customer_fair_value(report) is None
    assert _customer_potential(report) is None


def test_home_reason_does_not_promote_entry_mechanics_into_investment_reason():
    card = {
        "display_price": 14.38,
        "trade_plan": {"entry_low": 14.14, "entry_high": 14.50},
        "entry_relationship": "WITHIN_ENTRY_RANGE",
        "customer_plain_english_summary": {},
    }
    reason = _compact_reason(card)
    assert "entry range" not in reason.lower()
    assert reason == "A concise certified investment reason is unavailable for this snapshot."


def test_home_reason_does_not_present_company_name_as_investment_reason():
    card = {
        "company": "Teekay Corporation Ltd",
        "customer_plain_english_summary": {"text": "Teekay Corporation Ltd. Additional evidence follows."},
    }
    assert _compact_reason(card) == "A concise certified investment reason is unavailable for this snapshot."


def test_home_suppresses_duplicate_thesis_and_risk_copy():
    card = {
        "certified_summary_facts": {
            "business_driver": "Execution remains the central consideration",
            "primary_risk": "Execution remains the central consideration",
        },
    }
    thesis, risk = _compact_card_narrative(card)
    assert thesis == "Execution remains the central consideration."
    assert risk is None


def test_home_does_not_render_classifier_fragments_as_customer_risk_prose():
    card = {"evaluation": {"risk": {"evidence": {"drawdown_label": "shallow drawdown"}}}}
    assert _compact_primary_risk(card) == "Not published for this certified snapshot."


def test_home_hides_empty_modules_and_explains_featured_vs_total_inventory():
    source = (ROOT / "ui" / "home_guidance_vnext.py").read_text(encoding="utf-8")
    assert "Showing {visible} featured idea" in source
    assert "from {total} total certified BUY NOW" in source
    assert 'st.markdown("## What Changed")' not in source
    assert 'st.markdown("## Opportunity Spotlight")' not in source
    assert 'st.markdown("## Catalysts & Earnings")' not in source
    assert "Not shown because verified evidence is unavailable" in source


def test_trust_tiers_have_distinct_customer_copy_and_visual_classes():
    assert len(set(PRESENTATION_TRUST_TIERS.values())) == 4
    source = (ROOT / "ui" / "research_vnext.py").read_text(encoding="utf-8")
    for css_class in (
        "atlas-trust-certified-atlas",
        "atlas-trust-external-analyst-context",
        "atlas-trust-live-market-context",
        "atlas-trust-contextual-intelligence",
    ):
        assert css_class in source
    assert "TWELVE_DATA" not in source
    assert "Completeness:" not in source
    assert "Atlas Quant Fair Value" not in source
    assert "Atlas-FV Expected Return" not in source


def test_mobile_navigation_contract_prevents_horizontal_chip_overflow():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    research_source = (ROOT / "ui" / "research_vnext.py").read_text(encoding="utf-8")
    assert "overflow-x:auto" in app_source
    assert "scroll-snap-type:x proximity" in app_source
    assert "grid-template-columns:1fr 1fr" in research_source
    assert 'overflow-x:visible' in research_source
