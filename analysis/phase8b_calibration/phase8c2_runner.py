"""Manual aggregate-only Phase 8C.2 sensitivity runner.

One bounded Alpaca download is retained in memory and reused for every replay.
No raw bars or provider payloads are written.  This runner has no authority to
change or publish a production technical model.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from analysis.phase8b_calibration.calibration import build_calibration_report
from analysis.phase8b_calibration.real_alpaca_runner import (
    DEFAULT_REQUEST_CAP, DEFAULT_TIMEOUT_SECONDS, RequestBudget,
    build_historical_dataset, build_run_summary, fetch_daily_bars,
    validate_calibration_coverage,
)
from analysis.phase8b_calibration.sensitivity import (
    LOCKED_RUN_END_DATE, PHASE8C2_EXPERIMENT_VERSION, candidate_assessment,
    methodology_descriptor, methodology_fingerprint, run_sensitivities,
    verify_run4_baseline,
)
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION


ARTIFACTS = (
    "baseline_reproduction.json",
    "sensitivity_comparison.csv",
    "near_breakout_precision_coverage.csv",
    "confirmed_breakout_preservation.csv",
    "score_monotonicity.csv",
    "segment_robustness.csv",
    "component_diagnostic_ablation.csv",
    "candidate_recommendation.json",
)


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    fields = sorted({key for row in materialized for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(materialized)


def _variant_rows(results: Mapping[str, Any], section: str) -> list[dict[str, Any]]:
    rows = []
    baseline_metrics = results["V1_BASELINE"]["summary"][section]
    baseline_successes = int(baseline_metrics.get("near_to_confirmed") or 0) if section == "near" else 0
    baseline_count = int(baseline_metrics.get("n") or 0)
    for name, result in results.items():
        summary = result["summary"]
        metrics = summary[section]
        row = {
            "variant": name,
            "changed_field": result["changed_field"],
            "changed_value": result["changed_value"],
            "is_committed_v1": result["is_committed_v1"],
            **{key: value for key, value in metrics.items() if not isinstance(value, Mapping)},
        }
        if section == "near":
            successes = int(metrics.get("near_to_confirmed") or 0)
            row.update({
                "successful_early_warnings": successes,
                "successful_warning_retention_ratio": successes / baseline_successes if baseline_successes else None,
                "successful_warnings_sacrificed_vs_v1": baseline_successes - successes,
                "near_event_coverage_ratio_vs_v1": int(metrics.get("n") or 0) / baseline_count if baseline_count else None,
            })
        elif section == "confirmed":
            row.update({
                "confirmed_event_change_vs_v1": int(metrics.get("n") or 0) - baseline_count,
                "confirmation_delay_change_vs_v1": (
                    float(metrics["mean_confirmation_delay_bars"]) - float(baseline_metrics["mean_confirmation_delay_bars"])
                    if metrics.get("mean_confirmation_delay_bars") is not None and baseline_metrics.get("mean_confirmation_delay_bars") is not None else None
                ),
            })
        rows.append(row)
    return rows


def _sensitivity_rows(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, result in results.items():
        summary = result["summary"]
        validation = summary["walk_forward"]["validation"]
        rows.append({
            "variant": name,
            "changed_field": result["changed_field"],
            "changed_value": result["changed_value"],
            "is_committed_v1": result["is_committed_v1"],
            "all_events": summary["event_count"],
            "validation_events": validation["all"].get("n"),
            "validation_near_events": validation["near"].get("n"),
            "validation_near_failure_rate_20d": validation["near"].get("failure_rate_20d"),
            "validation_near_confirmation_rate": validation["near"].get("transition_confirmation_rate"),
            "validation_near_mean_return_20d": validation["near"].get("mean_return_20d"),
            "validation_near_spy_beating_rate_20d": validation["near"].get("spy_beating_rate_20d"),
            "validation_near_mean_bars_to_confirmation": validation["near"].get("mean_bars_to_confirmation"),
            "validation_confirmed_events": validation["confirmed"].get("n"),
            "validation_confirmed_mean_return_20d": validation["confirmed"].get("mean_return_20d"),
            "validation_confirmed_failure_rate_20d": validation["confirmed"].get("failure_rate_20d"),
            "validation_confirmed_mean_mfe_60": validation["confirmed"].get("mean_mfe_60"),
            "validation_confirmed_mean_mae_60": validation["confirmed"].get("mean_mae_60"),
        })
    return rows


def _score_rows(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, result in results.items():
        quality = result["summary"]["score_quality"]
        for bucket, metrics in quality["buckets"].items():
            rows.append({
                "variant": name, "score_bucket": bucket,
                **{key: value for key, value in metrics.items() if not isinstance(value, Mapping)},
                **{f"monotonicity_{key}": value for key, value in quality["monotonicity"].items()},
            })
    return rows


def _segment_rows(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, result in results.items():
        for dimension, groups in result["summary"]["segments"].items():
            for group, sections in groups.items():
                for state_group in ("near", "confirmed"):
                    rows.append({
                        "variant": name, "dimension": dimension, "segment": group,
                        "state_group": state_group,
                        **{key: value for key, value in sections[state_group].items() if not isinstance(value, Mapping)},
                    })
    return rows


def _component_rows(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    diagnostics = results["V1_BASELINE"]["component_diagnostics"]
    return [
        {
            "component": component,
            "diagnostic_type": "OBSERVATIONAL_HIGH_VS_LOW_NOT_PRODUCTION_ABLATION",
            **{key: value for key, value in row.items() if not isinstance(value, Mapping)},
            **{f"high_{key}": value for key, value in row["high_component"].items()},
            **{f"low_{key}": value for key, value in row["low_component"].items()},
        }
        for component, row in diagnostics.items()
    ]


def _conclusions(results: Mapping[str, Any], candidates: Mapping[str, Any]) -> dict[str, Any]:
    baseline = results["V1_BASELINE"]["summary"]
    candidate_rows = candidates["candidates"]
    ranked = sorted(
        candidate_rows,
        key=lambda row: (
            not row["near_failure_improved"],
            row["near_failure_rate_change"] if row["near_failure_rate_change"] is not None else float("inf"),
            -(row["successful_signal_coverage_ratio"] or 0.0),
            row["warning_lead_time_change_bars"],
        ),
    )
    improved = [row for row in ranked if row["near_failure_improved"]]
    strongest = improved[0] if improved else None
    promising = [row for row in candidate_rows if row["designation"] == "PROMISING_RESEARCH_CANDIDATE"]
    components = results["V1_BASELINE"]["component_diagnostics"]
    failure_avoidance = sorted(
        components,
        key=lambda name: components[name]["high_minus_low_failure_rate_20d"] if components[name]["high_minus_low_failure_rate_20d"] is not None else float("inf"),
    )
    validation = baseline["walk_forward"]["validation"]
    security_segments = validation["segments"]["security_type"]
    regime_segments = validation["segments"]["regime"]
    stock_near = security_segments.get("STOCK", {}).get("near", {})
    etf_near = security_segments.get("ETF", {}).get("near", {})
    enough_types = min(int(stock_near.get("n") or 0), int(etf_near.get("n") or 0)) >= 30
    failure_gap = _absolute_gap(stock_near.get("failure_rate_20d"), etf_near.get("failure_rate_20d"))
    return_gap = _absolute_gap(stock_near.get("mean_return_20d"), etf_near.get("mean_return_20d"))
    etf_separate = enough_types and ((failure_gap or 0.0) >= 0.10 or (return_gap or 0.0) >= 0.02)
    regime_failure_values = [row["near"].get("failure_rate_20d") for row in regime_segments.values() if row["near"].get("failure_rate_20d") is not None]
    regime_return_values = [row["near"].get("mean_return_20d") for row in regime_segments.values() if row["near"].get("mean_return_20d") is not None]
    regime_failure_spread = max(regime_failure_values) - min(regime_failure_values) if len(regime_failure_values) >= 2 else None
    regime_return_spread = max(regime_return_values) - min(regime_return_values) if len(regime_return_values) >= 2 else None
    phase8c3_candidates = [
        {
            "variant": row["variant"],
            "changed_field": results[row["variant"]]["changed_field"],
            "frozen_value": results[row["variant"]]["changed_value"],
            "all_other_thresholds": "COMMITTED_V1_UNCHANGED",
            "designation": "PROMISING_RESEARCH_CANDIDATE_NOT_PRODUCTION_APPROVED",
        }
        for row in promising
    ]
    return {
        "authority": "RESEARCH_ONLY_NO_V2_OR_PRODUCTION_THRESHOLD_APPROVAL",
        "A_strongest_predeclared_false_near_reducer": strongest["variant"] if strongest else None,
        "B_successful_signal_coverage_ratio": strongest.get("successful_signal_coverage_ratio") if strongest else None,
        "B_successful_signal_coverage_cost": 1.0 - strongest["successful_signal_coverage_ratio"] if strongest else None,
        "B_successful_early_warnings_sacrificed": strongest.get("successful_early_warnings_sacrificed") if strongest else None,
        "C_warning_lead_time_change_bars": strongest.get("warning_lead_time_change_bars") if strongest else None,
        "D_confirmed_preserving_variants": [row["variant"] for row in candidate_rows if row["confirmed_performance_preserved"]],
        "E_post_2022_score_ordering": validation["score_quality"]["monotonicity"],
        "F_components_most_associated_with_failure_avoidance": failure_avoidance,
        "G_stock_vs_etf_diagnostics": security_segments,
        "G_etf_specific_calibration_conclusion": "SEPARATE_CALIBRATION_RESEARCH_WARRANTED" if etf_separate else "NOT_YET_PROVEN_OR_INSUFFICIENT_SAMPLE",
        "G_failure_rate_gap": failure_gap,
        "G_20d_return_gap": return_gap,
        "H_market_regime_diagnostics": regime_segments,
        "H_failure_rate_spread": regime_failure_spread,
        "H_20d_return_spread": regime_return_spread,
        "H_regime_materially_changes_quality": bool((regime_failure_spread or 0.0) >= 0.10 or (regime_return_spread or 0.0) >= 0.02),
        "I_robust_enough_to_design_v2_candidate": bool(promising),
        "I_promising_research_candidates": promising,
        "I_approved_production_thresholds": [],
        "J_frozen_phase8c3_candidates": phase8c3_candidates,
        "J_phase8c3_next": [
            "Independently reproduce any promising candidate on a later untouched holdout period.",
            "Test only predeclared promising candidates; do not optimize threshold combinations.",
            "Review ETF-specific behavior only if aggregate stock/ETF differences persist with adequate samples.",
            "Validate component findings with predeclared removal tests before changing component weights.",
        ],
    }


def _absolute_gap(left: Any, right: Any) -> float | None:
    return abs(float(left) - float(right)) if left is not None and right is not None else None


def run() -> int:
    key_id = os.getenv("APCA_API_KEY_ID", "").strip()
    secret_key = os.getenv("APCA_API_SECRET_KEY", "").strip()
    if not key_id or not secret_key:
        print(json.dumps({"kind": "phase8c2_complete", "status": "MISSING_CREDENTIALS_ZERO_NETWORK_CALLS", "requests_used": 0}))
        return 2
    universe_path = Path(os.getenv("PHASE8C_UNIVERSE", "analysis/phase8b_calibration/universe_v1.json"))
    locked_summary_path = Path(os.getenv("PHASE8C2_LOCKED_SUMMARY", "run4-baseline/summary.json"))
    if not locked_summary_path.is_file():
        raise RuntimeError("LOCKED_RUN4_AGGREGATE_SUMMARY_REQUIRED")
    universe = json.loads(universe_path.read_text())
    locked_summary = json.loads(locked_summary_path.read_text())
    symbols = tuple(item["ticker"] for item in universe["assets"])
    end = os.getenv("PHASE8C_END_DATE", "").strip() or LOCKED_RUN_END_DATE
    budget = RequestBudget(int(os.getenv("PHASE8C_REQUEST_CAP", str(DEFAULT_REQUEST_CAP))))
    timeout = min(float(os.getenv("PHASE8C_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))), DEFAULT_TIMEOUT_SECONDS)
    print(json.dumps({
        "kind": "phase8c2_start", "experiment": PHASE8C2_EXPERIMENT_VERSION,
        "model": TECHNICAL_MODEL_VERSION, "symbol_count": len(symbols),
        "start": universe["start"], "end": end, "feed": universe["feed"],
        "adjustment": universe["adjustment"], "request_cap": budget.cap,
    }, sort_keys=True))
    ingestion = fetch_daily_bars(
        symbols, start=universe["start"], end=end, feed=universe["feed"],
        adjustment=universe["adjustment"], key_id=key_id, secret_key=secret_key,
        budget=budget, timeout=timeout,
    )
    print(json.dumps({"kind": "data_quality_summary", **ingestion.audit_metadata()}, sort_keys=True))
    coverage = validate_calibration_coverage(universe, ingestion)
    dataset = build_historical_dataset(universe, ingestion)
    baseline_report = build_calibration_report(dataset)
    reproduced_summary = build_run_summary(universe, symbols, ingestion, coverage, baseline_report, budget.used)
    baseline_lock = verify_run4_baseline(locked_summary, reproduced_summary)
    results = run_sensitivities(dataset, baseline_report)
    candidates = candidate_assessment(results)
    output = Path(os.getenv("PHASE8C2_OUTPUT_DIR", "audit_results/phase8c2"))
    output.mkdir(parents=True, exist_ok=True)
    baseline_artifact = {
        "schema_version": "ATLAS_RADAR_PHASE8C2_BASELINE_LOCK_V1",
        "methodology": methodology_descriptor(universe),
        "methodology_fingerprint": methodology_fingerprint(universe),
        "run4_reproduction": baseline_lock,
        "reproduced_summary": reproduced_summary,
        "data_quality": ingestion.audit_metadata(),
        "coverage_policy": coverage,
        "provider_requests_used_once": budget.used,
    }
    (output / "baseline_reproduction.json").write_text(json.dumps(baseline_artifact, sort_keys=True, indent=2) + "\n")
    _write_csv(output / "sensitivity_comparison.csv", _sensitivity_rows(results))
    _write_csv(output / "near_breakout_precision_coverage.csv", _variant_rows(results, "near"))
    _write_csv(output / "confirmed_breakout_preservation.csv", _variant_rows(results, "confirmed"))
    _write_csv(output / "score_monotonicity.csv", _score_rows(results))
    _write_csv(output / "segment_robustness.csv", _segment_rows(results))
    _write_csv(output / "component_diagnostic_ablation.csv", _component_rows(results))
    recommendation = {"schema_version": "ATLAS_RADAR_PHASE8C2_CANDIDATES_V1", **candidates, "conclusions": _conclusions(results, candidates)}
    (output / "candidate_recommendation.json").write_text(json.dumps(recommendation, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "kind": "phase8c2_complete", "status": "SUCCESS",
        "provider_requests_used": budget.used, "download_passes": 1,
        "variant_replays": len(results), "aggregate_artifact_count": len(ARTIFACTS),
        "baseline_status": baseline_lock["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
