from __future__ import annotations

import json

from core.pipeline_v104 import build_v104_pipeline
from engines.research_context import build_production_decision
from ui.home_v104 import (
    _confidence,
    _customer_updated_at,
    build_home_opportunity_card,
)
from ui.research_vnext import (
    _decision_value,
    _metric_currency_range,
    build_research_decision_view,
)


def _crc_rows():
    payload = json.loads(open("market_full_scan.json", encoding="utf-8").read())
    rows = payload if isinstance(payload, list) else payload.get("results") or []
    persisted = next(row for row in rows if row.get("ticker") == "CRC")
    projected = next(
        row for row in build_v104_pipeline(rows)["ranked_candidates"]
        if row.get("ticker") == "CRC"
    )
    return persisted, projected


def test_crc_home_and_research_share_persisted_decision_authority():
    persisted, projected = _crc_rows()
    canonical = build_production_decision(persisted)
    card = build_home_opportunity_card(projected)
    report = {
        "ticker": "CRC",
        "research_context": {"production_decision": dict(canonical)},
        "research_completeness_pct": 45,
        "guidance_summary": {},
        "trade_plan": {},
    }
    view = build_research_decision_view(report)

    assert projected["raw"] == persisted
    assert card["production_decision"] == dict(canonical)
    assert card["state"] == "Unavailable"
    assert card["opportunity"] is None
    assert card["confidence"] == 97
    assert card["supported_upside"] == 58.3
    assert view["header"].recommendation is None
    assert view["header"].opportunity is None
    assert view["header"].confidence == 97
    assert _decision_value(report, "decision_expected_return", "atlas_expected_return_pct") == 58.3


def test_actionable_and_monitor_fixtures_preserve_exact_canonical_values():
    for recommendation, opportunity, confidence, expected in (
        ("BUY_NOW", 84, 78, 18.4),
        ("MONITOR", 62, 71, -4.2),
    ):
        raw = {
            "ticker": "TEST", "Recommendation": recommendation,
            "Opportunity": opportunity, "Confidence": confidence,
            "decision_expected_return_pct": expected,
        }
        wrapper = {
            "ticker": "TEST", "committee_verdict": "BUY_NOW",
            "opportunity_score": 99, "confidence_pct": 99,
            "expected_return_pct": 99, "raw": raw,
        }
        card = build_home_opportunity_card(wrapper)
        assert (card["state"], card["opportunity"], card["confidence"], card["supported_upside"]) == (
            recommendation, opportunity, confidence, expected,
        )


def test_confidence_is_unsigned_while_upside_remains_signed():
    assert _confidence(78.4) == "78.4%"
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert '_confidence(card.get("confidence"))' in source
    assert '_pct(card.get("supported_upside"))' in source


def test_currency_range_escapes_streamlit_math_delimiters():
    assert _metric_currency_range(52.15, 53.34) == r"\$52.15–\$53.34"


def test_research_banner_has_no_independent_monitor_fallback():
    source = open("ui/research_vnext.py", encoding="utf-8").read()
    assert 'banner_state = _scalar_text(' in source
    assert 'report.get("committee_verdict") or "Monitor"' not in source


def test_readable_freshness_and_compact_mobile_contracts():
    assert _customer_updated_at("2026-08-30T00:02:00+00:00") == "Aug 29, 8:02 PM ET"
    source = open("ui/home_v104.py", encoding="utf-8").read()
    assert "flex-wrap:nowrap !important" in source
    assert "atlas-ux3-empty-section" in source
    assert "Catalyst unavailable" in source
    assert "margin-right:7rem" in source
    assert 'st.columns([3, 2])' in source
    assert 'row.get("committee_verdict") or "Unavailable"' in source


def test_platform_owned_overlay_safe_area_is_reserved_without_hiding_controls():
    home = open("ui/home_v104.py", encoding="utf-8").read()
    research = open("ui/research_vnext.py", encoding="utf-8").read()
    for source in (home, research):
        assert '[data-testid="stMainBlockContainer"]' in source
        assert "padding-bottom:max(6.5rem" in source
        assert "display:none" not in source[source.index("Streamlit Community Cloud") if "Streamlit Community Cloud" in source else source.index("fixed Streamlit Cloud"):][:800]
    assert ':has(> [data-testid="stElementContainer"] .atlas-ux3-card-head)' in home
    assert "padding-right:7.5rem" in home
    assert "margin-right:7rem" in home
    assert '[data-testid="stMetric"] { padding-right:7rem' in research


def test_host_overlay_clearance_targets_only_exposed_home_and_research_surfaces():
    home = open("ui/home_v104.py", encoding="utf-8").read()
    research = open("ui/research_vnext.py", encoding="utf-8").read()
    assert "h2#best-opportunities-right-now" in home
    assert "max-width:calc(100% - 7.5rem)" in home
    assert '[data-testid="stColumn"]:last-child' in home
    assert '[data-testid="column"]:last-child' not in home
    assert 'class="atlas-ux3-action-label"' in home
    assert 'class="atlas-ux3-action-copy"' in home
    assert "padding-right:3.5rem" in home
    assert "padding-right:7.5rem" in home
    assert '[data-testid="stAlert"] [data-testid="stMarkdownContainer"]' in research
    assert '[data-testid="stExpander"] summary' in research
    assert "padding-right:3.5rem" in research
    assert "padding-right:7.5rem" in research
    assert '[data-testid="stMainBlockContainer"] {\n          padding-right' not in home
    assert '[data-testid="stMainBlockContainer"] {\n          padding-right' not in research
