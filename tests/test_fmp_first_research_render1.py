from __future__ import annotations

from engines.analyst_intelligence import _date, _first, build_analyst_intelligence
from engines.atlas_research_builder_v2 import build_atlas_research_v2
from engines.semantic_fields import is_missing_scalar


def _nvda_fixture() -> dict:
    return {
        "ticker": "NVDA",
        "company": "NVIDIA",
        "security_type": "EQUITY",
        "current_price": 100.0,
        "atlas_fair_value": 120.0,
        "opportunity_score": 80.0,
        "confidence_pct": 75.0,
        "analyst_actions": [
            {
                "firm": "Example Research",
                "action": "upgrade",
                "from_grade": "Hold",
                "to_grade": "Buy",
                # Reproduces the sanitized container shape from Run #53.
                "date": ["2026-08-20"],
            },
            {
                "firm": "Second Research",
                "action": "maintain",
                "to_grade": "Buy",
                "date": "2026-08-19",
            },
        ],
        "analyst_estimates": [
            {"date": "2026-12-31", "eps_estimate_avg": 0, "revenue_estimate_avg": -1}
        ],
        "earnings_history": [
            {"date": "2026-05-01", "eps_actual": 0, "eps_estimate": -0.1}
        ],
        "ratios": {"return_on_equity": 0, "debt_to_equity": -1},
        "company_news": [
            {"headline": "Sanitized company update", "published_at": "2026-08-20", "url": "https://example.invalid/story"}
        ],
        "institutional_holders": [
            {"investor": "Example Fund", "shares": 0, "weight": -0.1, "reporting_date": "2026-06-30", "filing_date": "2026-08-10"}
        ],
        "press_releases": [],
        "management_guidance": None,
    }


def test_full_nvda_research_builder_survives_container_shaped_evidence(monkeypatch):
    monkeypatch.setattr(
        "engines.atlas_research_builder_v2.attach_price_history", lambda row: dict(row)
    )
    report = build_atlas_research_v2(_nvda_fixture())
    assert report["ticker"] == "NVDA"
    assert report["analyst_intelligence"]["recent_actions"][0]["firm"] == "Second Research"
    assert report["analyst_intelligence"]["current_price"] == 100.0


def test_repaired_analyst_helper_is_the_active_builder_dependency():
    intelligence = build_analyst_intelligence(_nvda_fixture())
    assert intelligence["recent_actions"][0]["firm"] == "Second Research"
    assert _date(["2026-08-20"]) is None


def test_missing_semantics_and_analyst_lookup_are_container_safe():
    cases = (
        (None, True), ("", True), ("Unavailable", True),
        (0, False), (-2.5, False),
        ([], True), ({}, True), ((), True), (set(), True),
        ([1], False), ({"a": 1}, False), ((1,), False), ({1}, False),
    )
    for value, expected_missing in cases:
        assert is_missing_scalar(value) is expected_missing
        result = _first({"value": value}, "value")
        if expected_missing:
            assert result is None
        else:
            assert result == value


def test_relevant_analyst_fields_accept_fuzzed_shapes_without_typeerror():
    values = ("2026-08-20", ["2026-08-20"], {"date": "2026-08-20"}, [], {}, None, 0, -1)
    for value in values:
        row = _nvda_fixture()
        row["analyst_actions"] = [{"firm": "Example Research", "date": value, "action": "upgrade"}]
        result = build_analyst_intelligence(row)
        assert isinstance(result["recent_actions"], list)
