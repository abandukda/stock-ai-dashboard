import pytest
from pathlib import Path
from services.model_validation import MIN_SAMPLE,append_outcomes,governed_aggregate,lifecycle,mature_store,regression_alerts,validation_report
from services.performance_tracking import mature_snapshot

def snapshot(**overrides):
    value={"snapshot_id":"s1","ticker":"ABC","timestamp":"2026-01-01T20:00:00Z","action":"BUY_NOW","opportunity_thesis":"VALUE_RERATING","opportunity":90,"decision_confidence":90,"valuation_confidence":80,"six_pillars":{"technical_quality":85,"fundamental_quality":75},"price":100,"entry_low":95,"entry_high":101,"stop":90,"technical_target":120}
    value.update(overrides);return value

def bars():
    return [{"timestamp":"2026-01-02T20:00:00Z","open":100,"high":103,"low":96,"close":102},{"timestamp":"2026-01-05T20:00:00Z","open":102,"high":121,"low":100,"close":120},{"timestamp":"2026-01-06T20:00:00Z","open":120,"high":122,"low":89,"close":91},{"timestamp":"2026-01-07T20:00:00Z","high":95,"low":90,"close":94},{"timestamp":"2026-01-08T20:00:00Z","high":98,"low":93,"close":97}]

def test_maturation_target_before_stop_benchmark_and_holding_outcome():
    records=mature_snapshot(snapshot(),bars(),[{"timestamp":b["timestamp"],"close":100+i} for i,b in enumerate(bars())])
    one,five=records
    assert one["horizon_sessions"]==1 and one["entry_reached"] is True
    assert five["target_reached"] and five["stop_reached"] and five["target_before_stop"] is True
    assert five["holding_period_outcome"]=="TARGET_REACHED" and five["time_to_first_material_outcome"]==2
    assert five["benchmark_relative_return"]==pytest.approx(-.07)

def test_no_lookahead_excludes_pre_snapshot_bars_and_unelapsed_horizons():
    assert mature_snapshot(snapshot(),[{"timestamp":"2025-12-31T20:00:00Z","close":999}])==[]
    assert [x["horizon_sessions"] for x in mature_snapshot(snapshot(),bars()[:4])]==[1]

def test_lifecycle_preserves_initial_action_and_records_direction_and_outcomes():
    later=snapshot(snapshot_id="s2",timestamp="2026-01-08T20:00:00Z",action="ACCUMULATE")
    outcome={**mature_snapshot(snapshot(),bars())[-1],"snapshot_id":"s1"}
    item=lifecycle([snapshot(),later],[outcome])[0]
    assert item["initial_action"]=="BUY_NOW" and item["latest_action"]=="ACCUMULATE"
    assert item["action_changes"][0]["direction"]=="DOWNGRADE" and item["target_reached"]

def test_small_sample_suppresses_conclusions_and_full_sample_enables_observation():
    record={**mature_snapshot(snapshot(),bars())[0],"action":"BUY_NOW"}
    small=governed_aggregate([record],"action")[0]
    assert small["publication_status"]=="INSUFFICIENT_MATURED_SAMPLE" and small["average_return"] is None
    full=governed_aggregate([record]*MIN_SAMPLE,"action")[0]
    assert full["publication_status"]=="OBSERVATIONAL" and full["average_return"] is not None

def test_calibration_report_and_regression_alerts_are_review_only():
    base={"price_return":.01,"benchmark_relative_return":.01,"max_drawdown":-.1,"action":"BUY_NOW","opportunity_thesis":"VALUE_RERATING","decision_confidence":90,"opportunity":90,"valuation_confidence":90,"technical_quality":90,"fundamental_quality":90,"snapshot_id":"x","horizon_sessions":20}
    report=validation_report([snapshot()],[{**base,"snapshot_id":str(i)} for i in range(MIN_SAMPLE)])
    assert report["customer_performance_enabled"] is False and report["sample_size_by_horizon"]["20"]==MIN_SAMPLE
    assert report["unobserved_snapshot_count"]==1 and report["unobserved_tickers"]==["ABC"]
    synthetic={"aggregations":{"action":[{"action":"BUY_NOW","publication_status":"OBSERVATIONAL","average_relative_return":0,"worst_drawdown":-.1},{"action":"ACCUMULATE","publication_status":"OBSERVATIONAL","average_relative_return":.1,"worst_drawdown":-.1}],"decision_confidence_bucket":[],"opportunity_thesis":[]}}
    assert regression_alerts(synthetic)==[{"type":"BUY_NOW_UNDERPERFORMS_BUILD","action":"REVIEW_ONLY"}]

def test_admin_dashboard_is_internal_and_has_small_sample_copy():
    source=Path("ui/developer_center.py").read_text()
    assert "Model Validation — Internal Only" in source and "Insufficient matured sample" in source
    assert "Customer-facing performance remains disabled" in source

def test_outcome_store_is_append_only_and_matures_by_ticker(tmp_path):
    records=mature_store([snapshot()],{"ABC":bars()})
    path=tmp_path/"outcomes.jsonl"
    assert append_outcomes(path,records)==2 and append_outcomes(path,records)==0
    changed={**records[0],"price_return":999}
    with pytest.raises(ValueError,match="IMMUTABLE_OUTCOME_CONFLICT"):append_outcomes(path,[changed])
