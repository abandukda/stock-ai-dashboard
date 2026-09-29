from copy import deepcopy

from services.executor_publication_bridge import bridge_evaluation, build_publication_bundle


def _source():
    return {
        "ticker": "TEST", "company": "Test", "current_price": 10.0, "market_cap": 1_000.0,
        "current_shares_outstanding": None, "diluted_shares": 100.0, "basic_shares": 99.0,
        "operating_cash_flow": 120.0, "capital_expenditures": 20.0,
        "free_cash_flow": 100.0, "normalized_fcf": 100.0, "cash_and_equivalents": 10.0,
        "total_debt": 20.0, "professional_evidence_as_of": "2026-09-29T00:00:00+00:00",
        "professional_evidence_lineage": {"provider": "FINNHUB", "evidence_ids": ["FS", "BF"], "fields": {
            "free_cash_flow": {"provider": "FINNHUB", "evidence_id": "FS", "period": "2025-12-31", "currency": "USD", "unit": "USD"},
            "market_cap": {"provider": "FINNHUB", "evidence_id": "BF", "as_of": "2026-09-29T00:00:00+00:00", "currency": "USD", "unit": "USD"},
        }},
    }


def _terminal(action="WAIT_FOR_CONFIRMATION"):
    evaluation = {
        "ticker": "TEST", "evaluated_at": "2026-09-29T00:00:00+00:00",
        "guidance": {"state": action}, "opportunity": 50, "decision_confidence": 50,
        "component_coverage": 80, "decision_metrics_methodology": "M", "decision_digest": "D",
        "market_snapshot": {"price": 10, "provider": "FINNHUB", "evidence_id": "PX", "provider_timestamp": "2026-09-28T00:00:00+00:00"},
        "technical_confirmation": {"status": "AVAILABLE", "fingerprint": "F", "as_of": "2026-09-28T00:00:00+00:00", "evidence": {"methodology_version": "T", "adjustment_mode": "SPLIT_ADJUSTED_ONLY", "volume_evidence_id": "VOL"}},
        "fundamentals": {"status": "PARTIAL", "source": "FINNHUB", "evidence_ids": ["FS"], "as_of": "2026-09-29T00:00:00+00:00"},
        "risk": {"status": "AVAILABLE", "as_of": "2026-09-28T00:00:00+00:00"},
        "trade_plan": {"entry_low": 9, "entry_high": 10, "stop_loss": 8},
        "volume_intelligence": {"status": "AVAILABLE", "evidence_id": "VOL", "as_of": "2026-09-28T00:00:00+00:00", "completed_daily_evidence": True, "valid_daily_volume_baseline": True},
        "atlas_valuation": {"professional_valuation_v2": {"status": "PUBLISHED", "company_type": "PROFITABLE_OPERATING_COMPANY", "atlas_base_fair_value": 10, "valuation_as_of": "2026-09-29T00:00:00+00:00", "models": [{"methodology_id": "VAL_P_FCF_V1", "status": "PUBLISHED", "value": 10, "weight": 1, "key_assumptions": {}}], "model_weights": {"VAL_P_FCF_V1": 1}, "valuation_diagnostics": {"flags": []}}},
    }
    return {"ticker": "TEST", "terminal_data_state": "CERTIFIED_EVALUATION", "canonical_action": action, "evaluation": evaluation, "evaluation_digest": "E"}


def test_bridge_is_deep_copy_and_preserves_decision_fields():
    terminal, source = _terminal(), _source()
    before_terminal, before_source = deepcopy(terminal), deepcopy(source)
    row = bridge_evaluation(terminal, source)
    assert terminal == before_terminal and source == before_source
    assert row["canonical_investment_evaluation"]["guidance"] == terminal["evaluation"]["guidance"]
    assert row["canonical_investment_evaluation"]["fundamentals"]["coverage_status"] == "PARTIAL"
    assert row["canonical_investment_evaluation"]["trade_plan"]["source"] == "ATLAS_TRADE_PLAN_FROM_CERTIFIED_TECHNICALS_V1"
    assert row["canonical_investment_evaluation"]["trial_presentation_fields"]["current_shares_outstanding"] is None
    assert row["canonical_investment_evaluation"]["trial_presentation_fields"]["share_structure"]["market_cap_reconciliation_shares"] == 100
    assert row["canonical_investment_evaluation"]["positive_action_revalidation"]["status"] == "NOT_REQUIRED"


def test_bridge_revalidates_buy_only_after_fundamentals_and_valuation_propagation(monkeypatch):
    def certified_validation(_row):
        return {
            "customer_publication_allowed": True,
            "certification_state": "CERTIFIED",
            "model_applicability": [
                {"methodology_id": "VAL_P_FCF_V1", "applicability": "PRIMARY_APPROPRIATE"},
                {"methodology_id": "VAL_FORWARD_PE_V1", "applicability": "PRIMARY_APPROPRIATE"},
            ],
            "valuation_evidence_strength": {
                "strong_action_eligible": True, "published_method_count": 2,
                "unmet_requirements": [],
            },
        }

    monkeypatch.setattr("services.executor_publication_bridge.validate_valuation", certified_validation)
    terminal = _terminal("BUY_NOW")
    terminal["evaluation"]["market_snapshot"]["latest_completed_session_valid"] = True
    terminal["evaluation"]["technical_confirmation"]["completed_bar"] = True
    professional = terminal["evaluation"]["atlas_valuation"]["professional_valuation_v2"]
    professional["models"].append({
        "methodology_id": "VAL_FORWARD_PE_V1", "status": "PUBLISHED",
        "value": 11, "weight": 0.5, "key_assumptions": {},
    })
    professional["models"][0]["weight"] = 0.5
    terminal["evaluation"]["risk"]["primary_risk"] = "Execution"
    terminal["evaluation"]["opportunity_thesis"] = "Certified multi-method value"
    professional["valuation_explanation"] = {
        "primary_valuation_driver": "Cash flow",
        "biggest_valuation_uncertainty": "Forecast delivery",
    }
    row = bridge_evaluation(terminal, _source())
    evaluation = row["canonical_investment_evaluation"]
    assert evaluation["fundamentals"]["status"] == "AVAILABLE"
    assert evaluation["valuation_validation"]["customer_publication_allowed"] is True
    assert evaluation["positive_action_revalidation"]["status"] == "BUY_NOW_REVALIDATED"
    assert evaluation["positive_action_revalidation"]["canonical_method_corroboration"]["certified_method_count"] == 2
    assert evaluation["guidance"] == terminal["evaluation"]["guidance"]
    assert evaluation["opportunity"] == terminal["evaluation"]["opportunity"]
    assert evaluation["decision_confidence"] == terminal["evaluation"]["decision_confidence"]


def test_bundle_keeps_zero_buy_state_and_report_card_off():
    terminal = _terminal()
    candidate = {
        "candidate_digest": "digest", "evidence_snapshot_at": "2026-09-29T00:00:00+00:00",
        "source_sha": "sha", "universe_sha256": "universe", "supported_symbol_count": 1,
        "provider_authority_version": "authority", "methodology_version": "method",
        "valuation_version": "valuation", "six_pillar_version": "pillars",
        "action_engine_version": "action",
        "evaluations": [terminal],
    }
    artifacts, manifest = build_publication_bundle(candidate=candidate, source_rows={"TEST": _source()})
    assert artifacts["market_scan_state.json"]["report_card_prospective_active"] is False
    assert artifacts["market_scan_state.json"]["provider_calls"] == 0
    assert artifacts["market_scan_state.json"]["discovery_v2"]["recall"]["discovery_gate"] == "PASS"
    assert len(artifacts["full_evaluation_pool.json"]) == 1
    row = artifacts["full_evaluation_pool.json"][0]
    assert row["candidate_digest"] == "digest"
    assert row["methodology_version"] == "method"
    assert row["valuation_version"] == "valuation"
    assert row["six_pillar_version"] == "pillars"
    assert row["action_engine_version"] == "action"
    assert manifest["executor_candidate_identity"]["candidate_digest"] == "digest"
    assert manifest["executor_candidate_identity"]["valuation_version"] == "valuation"
    assert manifest["methodology_versions"] == ["method"]
    assert manifest["valuation_version"] == "valuation"
    assert manifest["six_pillar_version"] == "pillars"
    assert manifest["action_engine_version"] == "action"
    assert manifest["report_card_prospective_active"] is False


def test_margin_unit_contract_is_serialized_without_period_inference():
    source = _source()
    source["operating_profit_margin"] = 12.5
    row = bridge_evaluation(_terminal(), source)
    trial = row["canonical_investment_evaluation"]["trial_presentation_fields"]
    assert trial["historical_operating_margin"] == 12.5
    assert trial["operating_margin_lineage"]["scale"] == "PERCENTAGE_POINTS"
    assert "basis" not in trial["operating_margin_lineage"]
