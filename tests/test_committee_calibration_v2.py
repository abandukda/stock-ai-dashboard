
from engines.investment_committee_v104 import build_committee_verdict


def row(**overrides):
    base = {
        "opportunity_score": 68,
        "confidence_pct": 62,
        "component_coverage_pct": 75,
        "expected_return_pct": 20,
        "components": {
            "fundamentals": 65,
            "technical": 64,
            "valuation": 70,
            "analyst": 70,
            "institutional": None,
            "political": None,
        },
        "component_details": {
            "fundamentals": {"status": "AVAILABLE"},
            "technical": {"status": "AVAILABLE"},
        },
        "investment_thesis": "Revenue and cash-flow trends remain constructive.",
    }
    base.update(overrides)
    return base


def test_missing_optional_evidence_does_not_force_avoid():
    result = build_committee_verdict(row())
    assert result["committee_verdict"] == "ACCUMULATE"


def test_buy_now_requires_actionable_quality_and_timing():
    result = build_committee_verdict(
        row(
            opportunity_score=75,
            confidence_pct=72,
            component_coverage_pct=82,
            expected_return_pct=24,
            components={
                "fundamentals": 72,
                "technical": 74,
                "valuation": 70,
                "analyst": 76,
                "institutional": None,
                "political": None,
            },
        )
    )
    assert result["committee_verdict"] == "BUY_NOW"


def test_confirmed_material_weakness_can_produce_avoid():
    result = build_committee_verdict(
        row(
            opportunity_score=42,
            expected_return_pct=-8,
            components={
                "fundamentals": 32,
                "technical": 30,
                "valuation": 30,
                "analyst": 40,
            },
        )
    )
    assert result["committee_verdict"] == "AVOID"


def test_partial_financial_status_is_not_treated_as_confirmed_weakness():
    result = build_committee_verdict(
        row(
            opportunity_score=58,
            confidence_pct=54,
            components={
                "fundamentals": 30,
                "technical": 60,
                "valuation": 60,
                "analyst": 60,
            },
            component_details={
                "fundamentals": {"status": "PARTIAL"},
                "technical": {"status": "AVAILABLE"},
            },
        )
    )
    assert result["committee_verdict"] != "AVOID"
