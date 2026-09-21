from scripts.finnhub_provider_only_certification import (
    UNRESOLVED_METRICS, canonical_dry_run_v2, financial_bridges, safe_derivations, technical_recomputation,
)
from engines.decision_metrics_v1 import build_decision_metrics


def test_ambiguous_finnhub_metrics_are_never_scoring_certified():
    assert "operatingMarginTTM" in UNRESOLVED_METRICS
    assert "revenueGrowthTTMYoy" in UNRESOLVED_METRICS


def test_safe_ratio_derivation_requires_same_period_and_currency():
    report = {"fiscal_period": "FY", "canonical_facts": {
        "revenue": {"value": 100, "period_end": "2025-12-31", "currency": "USD", "source_record_version": "a"},
        "ebit": {"value": 20, "period_end": "2025-12-31", "currency": "USD", "source_record_version": "a"},
    }}
    result = safe_derivations([report])
    assert result["operating_margin"]["classification"] == "SAFE_DERIVED"
    assert result["operating_margin"]["value_percentage_points"] == 20
    report["canonical_facts"]["ebit"]["currency"] = "EUR"
    assert safe_derivations([report])["operating_margin"]["classification"] == "PERIOD_MISMATCH"


def test_gross_margin_can_use_same_report_revenue_minus_cost():
    report = {"fiscal_period": "FY", "canonical_facts": {
        "revenue": {"value": 100, "period_end": "2025-12-31", "currency": "USD", "source_record_version": "a"},
        "cost_of_revenue": {"value": 60, "period_end": "2025-12-31", "currency": "USD", "source_record_version": "a"},
    }}
    result = safe_derivations([report])["gross_margin"]
    assert result["classification"] == "SAFE_DERIVED"
    assert result["value_percentage_points"] == 40


def test_share_concepts_remain_distinct_in_bridge():
    facts = {
        name: {"value": value, "normalized_unit": "SHARES", "source_field": name,
               "period_end": "2025-12-31", "source_record_version": "a"}
        for name, value in (("shares_outstanding", 10), ("weighted_average_shares_basic", 9),
                            ("weighted_average_shares_diluted", 11))
    }
    bridge = financial_bridges([{"fiscal_period": "FY", "canonical_facts": facts}])["shares"]
    assert bridge["shares_outstanding"]["value"] == 10
    assert bridge["weighted_average_shares_basic"]["value"] == 9
    assert bridge["weighted_average_shares_diluted"]["value"] == 11


def test_unresolved_volume_does_not_become_zero_or_prevent_other_metrics():
    metrics = build_decision_metrics(
        technical={"status": "AVAILABLE", "score": 75, "feed_health": "HEALTHY"},
        fundamentals={"status": "AVAILABLE", "score": 75, "data": {
            "revenue": 1, "eps": 1, "operating_margin_pct": 20,
            "free_cash_flow": 1, "current_ratio": 2,
        }},
        valuation={"status": "PUBLISHED", "validation_passed": True, "fair_value": 120, "expected_return": 20},
        risk={"status": "AVAILABLE", "score": 75},
        trade_plan={"entry_low": 95, "entry_high": 105, "stop": 90, "target": 125},
        volume={"status": "DATA_UNAVAILABLE", "relative_volume": None},
        market_snapshot={"price": 100, "fresh_current_price": True},
    )
    assert metrics["volume_quality"]["score"] is None
    assert metrics["volume_quality"]["effective_weight"] == 0
    assert metrics["opportunity"] is not None
    assert metrics["decision_confidence"] is not None


def test_canonical_dry_run_excludes_ambiguous_units_and_does_not_blame_volume_for_valuation_gap():
    facts = {
        "revenue": {"value": 100}, "net_income": {"value": 10}, "free_cash_flow": {"value": 8},
    }
    run = canonical_dry_run_v2(
        [{"fiscal_period": "FY", "canonical_facts": facts}],
        {"net_margin": {"classification": "SAFE_DERIVED"}},
        {"shares": {"shares_outstanding": {"classification": "SOURCE_FACT_MISSING"}}},
        {"status": "MATCH", "volume_certification": "CERTIFIED_COMPLETED_POST_CLOSE_CONSOLIDATED"},
    )
    assert run["certified_action"] is False
    assert "operatingMarginTTM" in run["unresolved_fields_excluded"]
    assert "VOLUME_SEMANTICS_UNRESOLVED" not in run["blockers"]
    assert "NO_CERTIFIED_PROFESSIONAL_VALUATION_METHOD" in run["blockers"]


def test_technical_recomputation_fails_closed_without_history():
    assert technical_recomputation("AAPL", {}) == {"status": "INSUFFICIENT_HISTORY", "bar_count": 0}


def test_completed_post_close_volume_supports_average_rvol_liquidity_and_breakout():
    count = 220
    payload = {
        "timestamps": list(range(1, count + 1)),
        "open": [100.0] * count,
        "high": [102.0] * count,
        "low": [99.0] * count,
        "close": [101.0] * count,
        "volume": [1_000_000.0] * (count - 1) + [2_000_000.0],
        "completed_session_flags": [True] * count,
    }
    result = technical_recomputation("AAPL", payload)
    assert result["status"] == "MATCH"
    assert result["volume_certification"] == "CERTIFIED_COMPLETED_POST_CLOSE_CONSOLIDATED"
    assert result["completed_daily_evidence"] is True
    assert result["independent"]["average_volume20"] == 1_050_000.0
    assert result["independent"]["average_dollar_volume20"] == 106_050_000.0
    assert result["relative_volume_completed_session"] == 2_000_000 / 1_050_000
    assert result["breakout_confirmation_eligible"] is True


def test_partial_current_session_is_excluded_from_certified_volume_calculations():
    count = 221
    payload = {
        "timestamps": list(range(1, count + 1)),
        "open": [100.0] * count,
        "high": [102.0] * count,
        "low": [99.0] * count,
        "close": [101.0] * count,
        "volume": [1_000_000.0] * (count - 1) + [99_000_000.0],
        "completed_session_flags": [True] * (count - 1) + [False],
    }
    result = technical_recomputation("AAPL", payload)
    assert result["bar_count"] == 220
    assert result["independent"]["average_volume20"] == 1_000_000.0
    assert result["relative_volume_completed_session"] == 1.0
