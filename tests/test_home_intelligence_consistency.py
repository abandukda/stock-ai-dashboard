from datetime import datetime, timezone

import pandas as pd

from engines.home_market_data import fetch_home_market_tape
from engines.market_today import build_market_today
from services.atlas_view_summary import (
    build_atlas_street_divergence_explanation,
    build_certified_summary_facts,
    certify_customer_presentation_consistency,
    plain_english_summary,
)
from ui.home_guidance_vnext import _certified_paid_client_full_evidence


def _field(value, status="CERTIFIED"):
    return {"value": value, "certification_status": status}


def _card():
    return {
        "ticker": "MKTX", "company": "MarketAxess Holdings Inc.",
        "certified_customer_evaluation": {
            "ticker": "MKTX", "customer_publication_allowed": True,
            "domains": {"fundamentals_certification": "CERTIFIED", "valuation_package_certification": "CERTIFIED"},
            "decision": {"action": "BUY_NOW"},
            "fields": {
                "price": _field(163.09), "revenue_growth_pct": _field(-0.5),
                "eps_growth_pct": _field(-4.3), "free_cash_flow": _field(332_329_000),
                "forward_eps": _field(8.81752), "forward_revenue": _field(955_453_740),
                "atlas_fair_value": _field(222.14), "atlas_upside_pct": _field(36.1),
            },
            "valuation_methods": (
                {"name": "FCFF Discounted Cash Flow", "value": _field(439.4662), "weight": _field(.2619)},
                {"name": "Forward Earnings Multiple", "value": _field(133.237), "weight": _field(.381)},
            ),
            "risk": {"evidence": {"drawdown_label": "Moderate drawdown"}},
            "wall_street_analysis": {
                "status": "WALL_STREET_AVAILABLE", "as_of": "2026-09-11T18:59:33Z",
                "consensus": {"target_mean": 158.0, "analyst_count": 12}, "recent_trend": "DETERIORATING",
            },
        },
    }


def test_closed_session_daily_bars_remain_available_with_regular_close_semantics():
    index = pd.to_datetime(["2026-09-10", "2026-09-11"], utc=True)
    frame = pd.DataFrame({("Close", "SPY"): [650.0, 655.0]}, index=index)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    tape = fetch_home_market_tape(lambda *args, **kwargs: frame, symbols={"SPY": "S&P 500 · SPY"},
                                  now=lambda: datetime(2026, 9, 12, 14, tzinfo=timezone.utc))
    row = tape["rows"][0]
    assert row["previous_close"] == 650.0
    assert row["price"] == 655.0 and row["point_change"] == 5.0
    assert row["market_session"] == "LATEST_REGULAR_CLOSE"
    assert row["freshness_status"] == "LATEST_COMPLETED_REGULAR_SESSION"
    assert row["provider_timestamp"].endswith("20:00:00Z")
    context = build_market_today(tape, now=datetime(2026, 9, 12, 14, tzinfo=timezone.utc))
    assert context["status"] == "AVAILABLE"
    assert context["market_session"] == "LATEST REGULAR CLOSE"


def test_market_news_is_independent_and_grounded_when_tape_is_unavailable():
    context = build_market_today({"rows": []}, news=[{
        "headline": "Fed holds interest rates steady", "source": "Governed Wire",
        "published_at": "2026-09-11T18:00:00Z", "evidence_id": "NEWS-1",
        "commercial_display_allowed": True,
    }])
    assert context["status"] == "DATA_UNAVAILABLE"
    assert context["major_market_news"][0]["relevance"] == "FED"
    assert "not inferring" in context["interpretation"]


def test_certified_summary_never_contradicts_populated_financial_domains():
    facts = build_certified_summary_facts(_card())
    payload = {"certified_summary_facts": facts}
    copy = plain_english_summary(payload)
    assert "financial evidence is not available" not in copy
    assert "$955.5M" not in copy  # only the two strongest facts are narrated
    assert "$222.14" in copy and "$158.00" in copy and "BUY NOW" in copy
    assert "analysts' assumptions are not disclosed" in copy
    assert certify_customer_presentation_consistency(copy, payload)["valid"] is True


def test_consistency_gate_removes_a_contradictory_claim_without_withholding_record():
    facts = build_certified_summary_facts(_card())
    result = certify_customer_presentation_consistency(
        "Financial evidence is unavailable. ATLAS estimates fair value at $222.14.",
        {"certified_summary_facts": facts},
    )
    assert result["valid"] is False
    assert result["violations"] == ("FINANCIAL_AVAILABILITY_CONTRADICTION",)
    assert result["safe_text"] == "ATLAS estimates fair value at $222.14."


def test_consistency_gate_rejects_numeric_and_unavailable_zero_claims():
    facts = build_certified_summary_facts(_card())
    facts["forward_eps"] = None
    result = certify_customer_presentation_consistency(
        "ATLAS estimates fair value at $999.00. Forward EPS is $0.00. "
        "Wall Street's average target is $12.00.",
        {"certified_summary_facts": facts},
    )
    assert set(result["violations"]) >= {
        "ATLAS_FAIR_VALUE_MISMATCH",
        "WALL_STREET_TARGET_MISMATCH",
        "UNAVAILABLE_FORWARD_EPS_RENDERED_AS_ZERO",
    }


def test_mktx_divergence_uses_certified_method_that_actually_drives_gap():
    result = build_atlas_street_divergence_explanation(build_certified_summary_facts(_card()))
    assert result["classification"] == "MATERIAL_DIVERGENCE"
    assert result["atlas_vs_street_pct"] == 40.59
    assert "long-term cash-flow value" in result["explanation"]
    assert "$439.47" in result["explanation"]
    assert "cannot attribute" in result["explanation"]


def test_tk_partial_street_and_missing_forward_eps_are_precise():
    card = _card()
    certified = card["certified_customer_evaluation"]
    certified["fields"]["forward_eps"] = _field(None, "INSUFFICIENT_INPUTS")
    certified["fields"]["atlas_fair_value"] = _field(42.13)
    certified["fields"]["atlas_upside_pct"] = _field(193.0)
    certified["decision"]["action"] = "ACCUMULATE"
    certified["valuation_methods"] = (
        {"name": "EV / EBITDA", "value": _field(42.1303), "weight": _field(1.0)},
    )
    certified["wall_street_analysis"]["consensus"] = {
        "target_mean": None, "analyst_count": 4, "consensus_rating": "buy",
    }
    facts = build_certified_summary_facts({**card, "company": "Teekay Corporation Ltd.", "company_evidence": {"industry": "Marine Shipping"}})
    copy = plain_english_summary({"certified_summary_facts": facts})
    assert "Wall Street ratings are available from 4 analysts" in copy
    assert "does not have a verified consensus price target" in copy
    assert "No verified Wall Street consensus" not in copy
    assert "one certified valuation method" in copy
    assert "$0.00" not in copy
    assert "freight rates" in copy


def test_bp_single_method_divergence_and_compact_large_numbers():
    card = _card()
    certified = card["certified_customer_evaluation"]
    certified["fields"]["forward_revenue"] = _field(201_005_852_000)
    certified["fields"]["atlas_fair_value"] = _field(79.90)
    certified["fields"]["atlas_upside_pct"] = _field(73.3)
    certified["valuation_methods"] = (
        {"name": "EV / EBITDA", "value": _field(79.8962), "weight": _field(1.0)},
    )
    certified["wall_street_analysis"]["consensus"] = {
        "target_mean": 48.15, "analyst_count": 19, "consensus_rating": "buy",
    }
    facts = build_certified_summary_facts({**card, "company": "BP Plc", "company_evidence": {"industry": "Oil & Gas Integrated"}})
    copy = plain_english_summary({"certified_summary_facts": facts})
    assert "one certified valuation method" in copy
    assert "ATLAS is 65.9% above Wall Street" in copy
    assert "commodity prices" in copy
    html = _certified_paid_client_full_evidence(
        {"customer_action": {"label": "BUILD A POSITION"}}, certified
    )
    assert "$201.0B" in html
    assert "$201,005,852,000.00" not in html
