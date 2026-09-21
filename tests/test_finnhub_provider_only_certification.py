from scripts.finnhub_provider_only_certification import (
    UNRESOLVED_METRICS, safe_derivations, technical_recomputation,
)


def test_ambiguous_finnhub_metrics_are_never_scoring_certified():
    assert "operatingMarginTTM" in UNRESOLVED_METRICS
    assert "revenueGrowthTTMYoy" in UNRESOLVED_METRICS


def test_safe_ratio_derivation_requires_same_period_and_currency():
    report = {"fiscal_period": "FY", "canonical_facts": {
        "revenue": {"value": 100, "period_end": "2025-12-31", "currency": "USD", "source_record_version": "a"},
        "ebit": {"value": 20, "period_end": "2025-12-31", "currency": "USD", "source_record_version": "a"},
    }}
    result = safe_derivations([report])
    assert result["operating_margin"]["classification"] == "SAFE_DERIVATION_AVAILABLE"
    assert result["operating_margin"]["value_percentage_points"] == 20
    report["canonical_facts"]["ebit"]["currency"] = "EUR"
    assert safe_derivations([report])["operating_margin"]["classification"] == "AMBIGUOUS_METRIC_REQUIRED"


def test_technical_recomputation_fails_closed_without_history():
    assert technical_recomputation("AAPL", {}) == {"status": "INSUFFICIENT_HISTORY", "bar_count": 0}
