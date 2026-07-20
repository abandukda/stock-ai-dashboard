from engines.risk_intelligence_engine import (
    build_risk_profile,
    risk_profile_to_dict,
    validate_risk_profile,
)


def test_build_risk_profile():
    profile = build_risk_profile({"opportunity_score": 80})
    assert profile.overall_risk_score < 50
    assert validate_risk_profile(profile) == []


def test_higher_opportunity_means_lower_risk():
    high = build_risk_profile({"opportunity_score": 90})
    low = build_risk_profile({"opportunity_score": 40})
    assert high.overall_risk_score < low.overall_risk_score


def test_risk_profile_to_dict():
    profile = build_risk_profile({"Opportunity Score": 75})
    payload = risk_profile_to_dict(profile)
    assert payload["overall_risk_score"] == 25.0
