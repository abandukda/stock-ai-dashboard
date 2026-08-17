from __future__ import annotations

from dataclasses import asdict
import inspect
import json
import os
from pathlib import Path

import pytest

from analysis.phase8b_calibration.phase8c2_runner import ARTIFACTS, run
from analysis.phase8b_calibration.sensitivity import (
    LOCKED_RUN_ARTIFACT_DIGEST, LOCKED_RUN_END_DATE, LOCKED_RUN_HEAD_SHA,
    LOCKED_RUN_ID, LOCKED_RUN_NUMBER, PREDECLARED_SENSITIVITIES,
    baseline_output_fingerprint, candidate_assessment, methodology_fingerprint,
    run_sensitivities, unique_variants, verify_run4_baseline,
)
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION, TechnicalConfig
from tests.test_phase8b_calibration import dataset


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase8c2-radar-sensitivity.yml"
UNIVERSE = ROOT / "analysis/phase8b_calibration/universe_v1.json"


def test_workflow_is_manual_read_only_and_uses_one_runner_download():
    text = WORKFLOW.read_text()
    trigger = text.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger
    for forbidden in ("schedule:", "push:", "pull_request:", "workflow_call:"):
        assert forbidden not in trigger
    assert "contents: read" in text and "actions: read" in text
    assert "python -m analysis.phase8b_calibration.phase8c2_runner" in text
    assert "overnight_market_scan" not in text
    assert "git commit" not in text and "git push" not in text
    assert text.count("phase8c2_runner") == 1
    assert 'run-id: "31985918377"' in text


def test_workflow_security_and_aggregate_artifact_allowlist():
    text = WORKFLOW.read_text()
    assert "${{ secrets.APCA_API_KEY_ID }}" in text
    assert "${{ secrets.APCA_API_SECRET_KEY }}" in text
    assert "::add-mask::${APCA_API_KEY_ID}" in text
    assert "::add-mask::${APCA_API_SECRET_KEY}" in text
    assert "*.json" not in text and "*.csv" not in text
    for artifact in ARTIFACTS:
        assert f"audit_results/phase8c2/{artifact}" in text
    assert "ohlcv" not in text.lower()


def test_locked_run4_identity_and_exact_v1_discipline():
    assert LOCKED_RUN_NUMBER == 4
    assert LOCKED_RUN_ID == 31985918377
    assert LOCKED_RUN_HEAD_SHA == "17e9d9a4117543c04ccc10d839c32a0c9a3b804f"
    assert LOCKED_RUN_ARTIFACT_DIGEST == "sha256:40fc7366a7b648799edfeeb681ed8fcd445fba1b80c756f858e8d6ba361f3aba"
    assert LOCKED_RUN_END_DATE == "2026-08-16"
    assert TECHNICAL_MODEL_VERSION == "BULL_RUN_RADAR_V1_PROVISIONAL"


def test_only_predeclared_one_factor_ranges_are_enumerated_once():
    assert PREDECLARED_SENSITIVITIES == {
        "breakout_relative_volume": (1.20, 1.40, 1.60),
        "near_breakout_distance_pct": (0.025, 0.035, 0.050),
        "state_score_near": (55.0, 58.0, 62.0),
        "state_score_forming": (40.0, 45.0, 50.0),
        "extended_from_pivot_pct": (0.10, 0.12, 0.15),
        "extended_atr_from_sma20": (2.0, 2.5, 3.0),
        "failed_breakout_buffer_pct": (0.010, 0.015, 0.020),
        "breakout_confirmation_bars": (1, 2, 3),
    }
    variants = unique_variants()
    assert len(variants) == 17
    assert variants[0][0] == "V1_BASELINE"
    assert sum(item[1] is None for item in variants) == 1
    baseline = TechnicalConfig()
    for _, field, value, config in variants[1:]:
        changed = [key for key, current in asdict(baseline).items() if asdict(config)[key] != current]
        assert changed == [field]
        assert getattr(config, field) == value
    assert TechnicalConfig() == baseline


def test_methodology_lock_is_stable_and_sensitive_to_universe_or_config():
    universe = json.loads(UNIVERSE.read_text())
    first = methodology_fingerprint(universe)
    assert first == methodology_fingerprint(universe)
    changed = json.loads(json.dumps(universe))
    changed["adjustment"] = "split"
    assert methodology_fingerprint(changed) != first


def _summary(latest="2026-08-16T04:00:00+00:00", states=None):
    return {
        "model_version": TECHNICAL_MODEL_VERSION,
        "universe_version": "ATLAS_RADAR_CALIBRATION_UNIVERSE_V1",
        "feed": "iex", "adjustment": "all", "requested_securities": 73,
        "securities_with_history": 72, "security_symbols": ["NVDA", "SPY"],
        "total_bars": 1000, "earliest_bar": "2016-01-04T05:00:00+00:00",
        "latest_bar": latest, "state_counts": states or {"NEAR_BREAKOUT": 2},
        "transition_counts": {}, "state_outcomes": {}, "score_buckets": {},
        "security_type_outcomes": {}, "sector_outcomes": {}, "regime_outcomes": {},
        "liquidity_outcomes": {}, "volatility_outcomes": {}, "market_cap_outcomes": {},
        "data_quality": {}, "coverage_policy": {}, "walk_forward": {},
    }


def test_baseline_lock_exact_reproduction_and_end_date_drift_classification():
    locked = _summary()
    exact = verify_run4_baseline(locked, dict(locked))
    assert exact["status"] == "EXACT_REPRODUCTION" and exact["exact_output_match"]
    later = _summary("2026-08-17T04:00:00+00:00", {"NEAR_BREAKOUT": 3})
    drift = verify_run4_baseline(locked, later)
    assert drift["status"] == "CONSISTENT_METHODOLOGY_END_DATE_DIFFERENCE"
    assert drift["end_date_difference_reported"]
    same_date_drift = _summary(states={"NEAR_BREAKOUT": 4})
    with pytest.raises(ValueError, match="BASELINE_DRIFT"):
        verify_run4_baseline(locked, same_date_drift)
    assert baseline_output_fingerprint(locked) == baseline_output_fingerprint(dict(locked))


def test_sensitivity_replay_is_deterministic_rich_and_does_not_mutate_v1():
    before = TechnicalConfig()
    first = run_sensitivities(dataset())
    second = run_sensitivities(dataset())
    assert first == second
    assert len(first) == 17 and TechnicalConfig() == before
    baseline = first["V1_BASELINE"]
    assert baseline["is_committed_v1"]
    assert baseline["component_diagnostics"]
    assert {"near", "confirmed", "score_quality", "segments", "walk_forward"} <= set(baseline["summary"])
    assert {"period", "year", "regime", "security_type", "sector", "market_cap", "liquidity", "volatility"} <= set(baseline["summary"]["segments"])
    for result in first.values():
        assert set(result["summary"]["near"]) >= {
            "near_to_confirmed", "near_to_failed", "mean_bars_to_confirmation",
            "mean_bars_to_failure", "mean_relative_volume", "mean_breakout_distance_pct",
        }
        assert set(result["summary"]["confirmed"]) >= {
            "mean_distance_above_pivot_pct", "median_distance_above_pivot_pct",
            "mean_confirmation_delay_bars", "median_confirmation_delay_bars",
        }
        validation = result["summary"]["walk_forward"]["validation"]
        assert {"score_quality", "segments"} <= set(validation)
        assert "mean_spy_relative_return_20d" in validation["near"]
    component = first["V1_BASELINE"]["component_diagnostics"]["trend"]
    assert {"high_confirmation_rate", "low_confirmation_rate", "most_overlapping_component", "most_overlapping_correlation"} <= set(component)


def test_candidate_screen_can_never_approve_a_production_threshold():
    results = run_sensitivities(dataset())
    assessment = candidate_assessment(results)
    assert assessment["designation_boundary"] == "RESEARCH_ONLY_NO_PRODUCTION_APPROVAL_AUTHORITY"
    assert assessment["candidates"]
    assert all(not row["approved_production_threshold"] for row in assessment["candidates"])
    assert all(row["designation"] in {"PROMISING_RESEARCH_CANDIDATE", "NOT_PROMISING_UNDER_PREDECLARED_GATES"} for row in assessment["candidates"])
    assert all("successful_early_warnings_sacrificed" in row for row in assessment["candidates"])
    assert all(set(row["concentration_flags"]) == {"one_year_dependent", "one_sector_dependent", "semiconductor_leadership_dependent", "one_regime_dependent"} for row in assessment["candidates"])


def test_missing_credentials_make_zero_calls_and_write_no_artifacts(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    monkeypatch.setenv("PHASE8C2_OUTPUT_DIR", str(tmp_path))
    assert run() == 2
    assert not list(tmp_path.iterdir())
    assert "MISSING_CREDENTIALS_ZERO_NETWORK_CALLS" in capsys.readouterr().out


def test_runner_has_no_production_authority_or_raw_persistence():
    import analysis.phase8b_calibration.phase8c2_runner as runner
    import analysis.phase8b_calibration.sensitivity as sensitivity

    source = (inspect.getsource(runner) + inspect.getsource(sensitivity)).lower()
    forbidden = (
        "streamlit", "overnight_market_scan", "opportunity_score", "atlas_fair_value",
        "recommendation_key", "position_size", "send_email", "git push", "git commit",
    )
    assert not any(term in source for term in forbidden)
    assert ".parquet" not in source and "raw_payload" not in source
    assert "bull_run_radar_v2" not in source
