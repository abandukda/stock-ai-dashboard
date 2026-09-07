from services.discovery_engine_v2 import (
    architecture_experiment, curate_customer_150, qualification_channels, recall_report,
    select_candidate_pool, select_full_evaluation_pool, validation_sample,
)


def broad(ticker, **values):
    return {"ticker": ticker, "price": 100, "sma20": 99, "sma50": 95, "sma200": 90,
            "rsi": 55, "dollar_volume": 10_000_000, "conviction": 45, **values}


def evaluated(ticker, action, opportunity=70, confidence=80, certified=True):
    row = broad(ticker)
    row["canonical_investment_evaluation"] = {
        "guidance": {"state": action}, "opportunity": opportunity,
        "decision_confidence": confidence, "component_coverage": 95,
    }
    row["publication_certification"] = {"customer_publication_allowed": certified}
    return row


def test_multi_path_qualification_is_not_single_score():
    growth = broad("GROW", conviction=10, revenue_growth=.20, earnings_growth=.15,
                   operating_profit_margin=.12, free_cash_flow=100)
    recovery = broad("REC", conviction=10, sma50=105, rsi=45)
    assert "QUALITY_GROWTH" in qualification_channels(growth)
    assert "RECOVERY" in qualification_channels(recovery)
    assert {row["ticker"] for row in select_candidate_pool([growth, recovery], 10)} == {"GROW", "REC"}


def test_protected_and_lane_candidates_receive_full_evaluation():
    rows = [broad(f"T{i}", revenue_growth=.1 if i == 9 else None,
                  free_cash_flow=100 if i == 9 else None) for i in range(20)]
    candidates = select_candidate_pool(rows, 20)
    selected = select_full_evaluation_pool(candidates, 5)
    assert any(row["ticker"] == "T9" for row in selected)
    assert len({row["ticker"] for row in selected}) == 5


def test_attractive_entry_lane_is_protected_from_aggregate_cutoff():
    candidates = []
    for index in range(20):
        row = broad(f"T{index}")
        row.update({"medium_stage_score": 100 - index, "protected_positive_lane": index < 4,
                    "prescreen_channels": ["TECHNICAL_SETUP"]})
        candidates.append(row)
    candidates[-1]["prescreen_channels"] = ["ATTRACTIVE_ENTRY"]
    selected = select_full_evaluation_pool(candidates, 5)
    assert "T19" in {row["ticker"] for row in selected}


def test_governed_1400_pool_retains_late_entry_lane_without_skipping_full_evaluation():
    candidates = []
    for index in range(1500):
        item = broad(f"T{index:04d}")
        item.update({"medium_stage_score": 1500 - index,
                     "protected_positive_lane": index < 1024,
                     "prescreen_channels": ["ATTRACTIVE_ENTRY"] if index >= 1024 else ["QUALITY_GROWTH"]})
        candidates.append(item)
    selected = select_full_evaluation_pool(candidates, 1400)
    assert len(selected) == 1400
    assert "T1399" in {row["ticker"] for row in selected}
    assert all(row.get("light_evaluation") is None for row in selected)


def test_validation_sample_is_deterministic_and_has_cutoff_controls():
    rows = [broad(f"T{i:03}") for i in range(300)]
    one = validation_sample(rows, near_cutoff=100, random_size=100, seed="run")
    two = validation_sample(rows, near_cutoff=100, random_size=100, seed="run")
    assert [row["ticker"] for row in one] == [row["ticker"] for row in two]
    assert len(one) == 200
    assert sum(row["discovery_validation_cohort"] == "NEAR_CUTOFF" for row in one) == 100


def test_d0_and_d1_misses_are_detected_without_changing_action():
    retained = [evaluated("KEEP", "WAIT_FOR_CONFIRMATION")]
    controls = [evaluated("MISSBUY", "BUY_NOW"), evaluated("MISSBUILD", "ACCUMULATE")]
    report = recall_report(retained, controls)
    assert report["discovery_gate"] == "FAIL"
    assert report["severity_counts"]["D0"] == 1
    assert report["severity_counts"]["D1"] == 1
    assert controls[0]["canonical_investment_evaluation"]["guidance"]["state"] == "BUY_NOW"


def test_customer_selection_uses_certified_full_evaluation_and_includes_all_buys():
    rows = [evaluated(f"WAIT{i}", "WAIT_FOR_CONFIRMATION", 99) for i in range(160)]
    rows += [evaluated("BUY1", "BUY_NOW", 65), evaluated("BUILD1", "ACCUMULATE", 90)]
    rows += [evaluated("UNCERTIFIED", "BUY_NOW", 100, certified=False)]
    selected = curate_customer_150(rows)
    tickers = {row["ticker"] for row in selected}
    assert {"BUY1", "BUILD1"}.issubset(tickers)
    assert "UNCERTIFIED" not in tickers
    assert len(selected) == 150
    assert [row["production_rank"] for row in selected] == list(range(1, 151))


def test_architecture_experiment_reports_every_governed_scenario():
    eligible = [broad(f"T{i:03}", revenue_growth=.1, free_cash_flow=100) for i in range(700)]
    evaluated_rows = [evaluated(f"T{i:03}", "BUY_NOW" if i < 3 else "ACCUMULATE") for i in range(250)]
    result = architecture_experiment(eligible, evaluated_rows)
    assert len(result["scenarios"]) == 6 * 13
    assert result["recommended"] is not None
    assert result["scenarios"][0]["validation_population"] == 250
