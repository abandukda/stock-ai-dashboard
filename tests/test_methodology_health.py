from datetime import datetime, timezone

from services.full_universe_decision_publication import publish_evaluations
from services.methodology_health import methodology_health


def test_methodology_health_counts_governed_diagnostics_and_version_mismatch():
    row={"ticker":"A","canonical_investment_evaluation":{"atlas_valuation":{"professional_valuation_v2":{
        "status":"PUBLISHED","valuation_methodology_version":"STALE","valuation_as_of":"2026-09-01T00:00:00+00:00",
        "valuation_diagnostics":{"flags":["MODEL_DISPERSION_HIGH","WACC_BELOW_RISK_FREE"]}}}}}
    result=methodology_health([row],now=datetime(2026,9,6,tzinfo=timezone.utc))
    assert result["published_count"]==1 and result["high_model_dispersion_count"]==1
    assert result["wacc_below_risk_free_count"]==1 and result["methodology_mismatch_count"]==1
    assert result["status"]=="DEGRADED"


def test_failed_publication_cannot_overwrite_last_valid_canonical_evaluation():
    old={"version":"CANONICAL","guidance":{"state":"BUY_NOW"}}
    rows=[{"ticker":"A","canonical_investment_evaluation":old}]
    published=publish_evaluations(rows,{"status":"DATA_UNAVAILABLE","evaluations":{}})
    assert published[0]["canonical_investment_evaluation"]==old
