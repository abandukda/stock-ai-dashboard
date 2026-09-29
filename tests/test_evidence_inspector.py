from copy import deepcopy

from services.evidence_inspector import PARAMETERS, STATUSES, coverage_report, inspect_ticker, inventory


def _evaluation():
    return {
        "version": "CANONICAL_INVESTMENT_EVALUATION_V1",
        "ticker": "AAPL",
        "evaluated_at": "2026-09-28T21:00:00+00:00",
        "market_snapshot": {
            "price": 200.0, "provider_timestamp": "2026-09-28T20:00:00+00:00",
            "received_timestamp": "2026-09-28T20:01:00+00:00", "evidence_id": "market-1",
        },
        "technical_confirmation": {
            "score": 80.0, "state": "READY", "as_of": "2026-09-28T20:00:00+00:00",
            "evidence": {"rsi_14": 55.0, "atr_14": 3.0, "sma_20": 195.0, "sma_50": 190.0, "sma_200": 170.0},
        },
        "fundamentals": {"data": {
            "revenue_growth_pct": 8.0, "eps_growth_pct": 10.0, "gross_margin_pct": 45.0,
            "operating_margin_pct": 30.0, "free_cash_flow": 100.0,
            "operating_cash_flow": 120.0, "current_ratio": 1.5, "debt_to_equity": 1.0,
        }},
        "risk": {"net_debt_to_ebitda": 1.0, "evidence": {"volatility_risk": "low", "drawdown_label": "shallow drawdown"}},
        "trade_plan": {"entry_low": 190.0, "entry_high": 205.0, "stop_loss": 180.0, "target_1": 250.0},
        "volume_intelligence": {"relative_volume": 1.2, "evidence_id": "volume-1", "completed_daily_evidence": True, "valid_daily_volume_baseline": True},
        "atlas_valuation": {
            "fair_value": 240.0, "expected_return": 20.0,
            "professional_valuation_v2": {
                "canonical_inputs": {
                    "market_cap": 3_000_000_000_000, "capex": -20.0,
                    "normalized_fcf": 100.0, "justified_p_fcf": 25.0,
                    "forecast_fcff": [100.0, 110.0], "risk_free_rate": .04,
                    "equity_risk_premium": .05, "beta": 1.1, "cost_of_debt": .04,
                    "tax_rate": .21, "wacc": .085, "terminal_growth": .025,
                    "total_debt": 50.0, "cash_and_equivalents": 60.0,
                    "diluted_shares": 15.0, "dividend_next": 1.0,
                    "dividend_growth": .04, "cost_of_equity": .095,
                },
                "peer_evidence": {"p_fcf": {"final_peer_set": ["MSFT", "GOOG", "META"]}},
                "models": [{"methodology_id": "VAL_P_FCF_V1", "status": "PUBLISHED", "value": 240.0}],
            },
        },
        "decision_metrics": {"entry_quality": {"details": {"reward_risk_ratio": 3.0}}},
        "technical_quality": {"score": 80.0, "effective_weight": 25.0, "status": "AVAILABLE"},
        "fundamental_quality": {"score": 75.0, "effective_weight": 20.0, "status": "AVAILABLE"},
        "valuation_quality": {"score": 70.0, "effective_weight": 20.0, "status": "AVAILABLE"},
        "risk_quality": {"score": 85.0, "effective_weight": 15.0, "status": "AVAILABLE"},
        "entry_quality": {"score": 90.0, "effective_weight": 10.0, "status": "AVAILABLE"},
        "volume_quality": {"score": 80.0, "effective_weight": 10.0, "status": "AVAILABLE"},
        "opportunity": 78.5, "decision_confidence": 82.0, "component_coverage": 100.0,
        "guidance": {"state": "BUY_NOW", "market_regime": "BULLISH", "reason_codes": ["ALL_GATES_PASSED"]},
        "positive_action_revalidation": {"status": "BUY_NOW_REVALIDATED"},
        "decision_digest": "digest-1",
    }


def test_inventory_is_explicit_unique_and_machine_readable():
    rows = inventory()
    assert len(rows) == len(PARAMETERS) >= 80
    assert len({item["parameter_name"] for item in rows}) == len(rows)
    required = {"parameter_name", "canonical_name", "engine", "source", "required_or_optional",
                "expected_type", "expected_unit", "expected_currency", "expected_period_basis",
                "normalization_rule", "downstream_consumers"}
    assert all(required <= set(item) for item in rows)


def test_inspector_is_internal_non_mutating_and_traces_derived_parents():
    source = _evaluation()
    original = deepcopy(source)
    report = inspect_ticker(source)
    assert source == original
    assert report["customer_visible"] is False
    assert report["raw_provider_payload_included"] is False
    assert report["traceability"] == {"status": "PASS", "failure_code": None, "untraceable_inputs": []}
    assert report["decision_trace"]["question"] == "WHY BUY_NOW"
    fcf = next(item for item in report["parameters"] if item["parameter"] == "free_cash_flow")
    assert fcf["formula"] == "operating_cash_flow - abs(capex)"
    assert fcf["parents"] == ["operating_cash_flow", "capex"]
    assert all(item["status"] in STATUSES for item in report["parameters"])


def test_missing_and_contract_pending_are_explicit_not_silent_zeroes():
    report = inspect_ticker({"ticker": "MISS", "guidance": {"state": "RATING_NOT_PUBLISHED"}})
    by_name = {item["parameter"]: item for item in report["parameters"]}
    assert by_name["current_price"]["status"] == "MISSING_PROVIDER_FACT"
    assert by_name["current_price"]["normalized_value"] is None
    assert by_name["forward_eps"]["status"] == "CONTRACT_PENDING"
    assert report["decision_trace"]["question"] == "WHY NOT BUY_NOW"


def test_full_universe_coverage_report_ranks_gaps_without_changing_methodology():
    report = coverage_report([_evaluation(), {"ticker": "MISS", "guidance": {"state": "RATING_NOT_PUBLISHED"}}])
    assert report["symbol_count"] == 2
    assert report["canonical_parameter_count"] == len(PARAMETERS)
    assert report["status"] == "PARAMETER_VISIBILITY_COMPLETE"
    assert report["untraceable_inputs"] == []
    assert report["troubleshooting_queue"]
    assert all(item["methodology_impact"] == "NONE" for item in report["troubleshooting_queue"])


def test_developer_center_is_the_only_ui_surface_for_inspector():
    source = open("ui/developer_center.py", encoding="utf-8").read()
    assert "Evidence Inspector — Internal QA Only" in source
    assert "raw_provider_payload_included" not in source
    assert "services.evidence_inspector" in source
