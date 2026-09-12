from services.home_runtime_contract import build_home_runtime_contract


def _story():
    return {
        "home_action_count_contract": {
            "reconciled": True, "artifact_run_id": "run-1", "artifact_source_sha": "a" * 40,
            "generated_at": "2026-09-12T01:00:00Z", "certification_digest": "cert",
            "customer_publication_count": 2, "home_featured_count": 1,
            "home_featured_action_counts": {"BUY_NOW": 1},
        },
        "market_today": {"version": "MARKET_TODAY_V1", "status": "AVAILABLE", "source": "TWELVE_DATA",
                         "as_of": "2026-09-12T14:31:00Z", "major_market_news": []},
        "home_featured_cards": [{
            "ticker": "ABC", "price_as_of": "2026-09-12T14:31:00Z",
            "decision_as_of": "2026-09-11T20:00:00Z", "decision_snapshot_id": "snapshot-1",
            "decision_digest": "decision-1", "targeted_revalidation": {"state": "CURRENT"},
            "certified_customer_evaluation": {"customer_publication_allowed": True,
                                               "digests": {"valuation_digest": "valuation-1"}},
        }],
    }


def test_runtime_contract_reconciles_modules_and_exposes_separate_timestamps(monkeypatch):
    monkeypatch.setenv("ATLAS_BUILD_SHA", "b" * 40)
    monkeypatch.setenv("ATLAS_DEPLOY_BRANCH", "main")
    result = build_home_runtime_contract(_story(), market_health={"symbols_available": ["SPY"]})
    assert result["runtime_ready"] is True
    assert result["code_sha"] == "b" * 40
    assert result["per_ticker"][0]["live_price_timestamp"] != result["per_ticker"][0]["decision_timestamp"]


def test_runtime_contract_fails_closed_for_missing_required_modules():
    story = _story()
    story["home_action_count_contract"]["reconciled"] = False
    story["market_today"].pop("major_market_news")
    result = build_home_runtime_contract(story)
    assert result["runtime_ready"] is False
    assert "HOME_ACTION_RECONCILIATION_FAILED" in result["failure_reasons"]
    assert "MARKET_NEWS_CONTRACT_MISSING" in result["failure_reasons"]
