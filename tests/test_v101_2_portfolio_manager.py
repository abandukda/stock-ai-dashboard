from engines.portfolio_manager_engine import (
    build_portfolio_plan,
    calibrate_confidence,
    validate_portfolio_contract,
)


def candidate(ticker, opportunity, completeness, technical=70):
    return {
        "ticker": ticker,
        "sector": "Technology",
        "industry": "Software",
        "opportunity_score": opportunity,
        "research_completeness_pct": completeness,
        "required_pillars_passed_pct": completeness,
        "technical_score": technical,
        "quality_score": 80,
        "smart_money_score": 75,
        "government_policy_score": 70,
        "policymaker_disclosure_score": 60,
        "fundamentals_freshness_days": 2,
        "institutional_freshness_days": 5,
        "government_policy_freshness_days": 3,
        "policymaker_disclosure_freshness_days": 10,
        "news_freshness_days": 1,
    }


def test_confidence_varies_with_evidence():
    high = calibrate_confidence(candidate("HIGH", 95, 95))
    low = calibrate_confidence(
        candidate("LOW", 70, 50, technical=35)
    )
    assert high["confidence_pct"] > low["confidence_pct"]
    assert high["confidence_band"] != low["confidence_band"]


def test_policy_support_increases_confidence():
    supported = candidate("POL", 85, 85)
    unsupported = dict(supported)
    unsupported["government_policy_score"] = 20

    assert (
        calibrate_confidence(supported)["confidence_pct"]
        > calibrate_confidence(unsupported)["confidence_pct"]
    )


def test_policymaker_buying_is_low_weight_support():
    base = candidate("BASE", 85, 85)

    positive = dict(base)
    positive["policymaker_disclosure_score"] = 95

    negative = dict(base)
    negative["policymaker_disclosure_score"] = 10

    gap = (
        calibrate_confidence(positive)["confidence_pct"]
        - calibrate_confidence(negative)["confidence_pct"]
    )

    assert 0 < gap < 5


def test_freshness_penalizes_stale_data():
    fresh = candidate("FRESH", 90, 90)
    stale = dict(fresh)

    for key in (
        "fundamentals",
        "institutional",
        "government_policy",
        "policymaker_disclosure",
        "news",
    ):
        stale[f"{key}_freshness_days"] = 90

    assert (
        calibrate_confidence(fresh)["confidence_pct"]
        > calibrate_confidence(stale)["confidence_pct"]
    )


def test_portfolio_contract():
    model = build_portfolio_plan(
        [
            candidate("A", 95, 95),
            candidate("B", 88, 85),
            {
                **candidate("C", 82, 80),
                "sector": "Healthcare",
                "industry": "Biotechnology",
            },
        ]
    )

    assert validate_portfolio_contract(model) == []

    total = round(
        sum(
            item["recommended_allocation_pct"]
            for item in model["allocations"]
        )
        + model["recommended_cash_pct"],
        1,
    )
    assert total == 100.0


def test_empty_portfolio_holds_cash():
    model = build_portfolio_plan([])

    assert model["recommended_cash_pct"] == 100.0
    assert model["allocations"] == []


def test_legacy_minimal_rows_remain_compatible():
    model = build_portfolio_plan(
        [
            {
                "ticker": "A",
                "opportunity_score": 100,
            },
            {
                "ticker": "B",
                "opportunity_score": 50,
            },
        ]
    )

    assert len(model["allocations"]) == 2
    assert (
        model["allocations"][0]["recommended_allocation_pct"]
        >= model["allocations"][1]["recommended_allocation_pct"]
    )
