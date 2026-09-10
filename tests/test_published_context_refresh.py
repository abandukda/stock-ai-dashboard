from copy import deepcopy

import pytest

from scripts.refresh_published_context import protected_digest, refresh_rows
from services.context_evidence import CONTEXT_ENDPOINTS


def test_context_refresh_workflow_cannot_invoke_discovery_or_overnight():
    source = open(".github/workflows/context_only_refresh.yml", encoding="utf-8").read()
    assert "scripts/refresh_published_context.py" in source
    assert "overnight_market_scan.py" not in source
    assert "discovery_candidate_pool.json full_evaluation_pool.json" in source
    assert "ATLAS_DATA_MODE: INTERNAL_TRIAL" in source


def rows(count=150):
    return [
        {
            "ticker": f"T{i:03d}", "production_rank": i,
            "canonical_investment_evaluation": {
                "guidance": {"state": "BUY_NOW" if i == 1 else "WAIT_FOR_CONFIRMATION"},
                "opportunity": {"score": 80}, "decision_confidence": {"score": 75},
                "trade_plan": {"entry_low": 10, "entry_high": 12},
            },
        }
        for i in range(1, count + 1)
    ]


def test_context_endpoint_contract_is_bounded_to_post_selection_families():
    assert set(CONTEXT_ENDPOINTS) == {
        "price_target", "recommendations", "earnings_estimate", "revenue_estimate",
        "eps_trend", "analyst_ratings/light", "press_releases",
        "insider_transactions", "institutional_holders",
    }


def test_refresh_preserves_exact_canonical_decision_digest_and_order(monkeypatch):
    original = rows()
    expected = protected_digest(original)
    def enrich(source, **kwargs):
        output = deepcopy(source)
        for row in output:
            row["wall_street_analysis"] = {
                "status": "WALL_STREET_AVAILABLE", "provider": "TWELVE_DATA",
                "evidence_ids": (f"TD-{row['ticker']}",),
                "commercial_display_status": "DISPLAY_ALLOWED_INTERNAL_TRIAL",
                "consensus": {"target_mean": 20}, "non_scoring": True,
            }
        return output, {"provider_calls": 1350, "successful_calls": 1350, "endpoint_success": {}}
    monkeypatch.setattr("scripts.refresh_published_context.enrich_published_context", enrich)
    refreshed, report = refresh_rows(original)
    assert report["canonical_decisions_unchanged"] is True
    assert report["canonical_decision_digest_before"] == report["canonical_decision_digest_after"] == expected
    assert [row["ticker"] for row in refreshed] == [row["ticker"] for row in original]
    assert all(row["wall_street_analysis"]["non_scoring"] is True for row in refreshed)


def test_refresh_rejects_non_150_population():
    with pytest.raises(RuntimeError, match="REQUIRES_CURRENT_TOP_150"):
        refresh_rows(rows(149))


def test_refresh_rejects_any_canonical_mutation(monkeypatch):
    original = rows()
    def corrupt(source, **kwargs):
        output = deepcopy(source)
        output[0]["canonical_investment_evaluation"]["guidance"]["state"] = "AVOID"
        return output, {"provider_calls": 1}
    monkeypatch.setattr("scripts.refresh_published_context.enrich_published_context", corrupt)
    with pytest.raises(RuntimeError, match="CHANGED_CANONICAL_DECISIONS"):
        refresh_rows(original)
