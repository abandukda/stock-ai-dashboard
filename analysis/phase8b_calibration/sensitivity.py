"""Offline one-factor diagnostics for the locked Bull Run Radar V1 baseline.

This module has no provider, UI, scanner, alert, or investment-decision imports.
It consumes an already validated in-memory historical dataset and emits aggregate
research results only.  The committed V1 configuration is never mutated.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json
import statistics
from typing import Any, Iterable, Mapping, Sequence

from analysis.phase8b_calibration.calibration import (
    HORIZONS, SCORE_BUCKETS, CalibrationEvent, CalibrationReport,
    HistoricalDataset, build_calibration_report, chronological_split,
    summarize_events,
)
from services.live_market.models import TechnicalState
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION, TechnicalConfig
from services.technical_intelligence.engine import TechnicalIntelligenceEngine


PHASE8C2_EXPERIMENT_VERSION = "ATLAS_RADAR_PHASE8C2_ONE_FACTOR_V1"
LOCKED_RUN_NUMBER = 4
LOCKED_RUN_ID = 31985918377
LOCKED_RUN_HEAD_SHA = "17e9d9a4117543c04ccc10d839c32a0c9a3b804f"
LOCKED_RUN_ARTIFACT_DIGEST = "sha256:40fc7366a7b648799edfeeb681ed8fcd445fba1b80c756f858e8d6ba361f3aba"
LOCKED_RUN_END_DATE = "2026-08-16"
WALK_FORWARD_SPLIT = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
MIN_NEAR_VALIDATION_EVENTS = 30
MIN_SUCCESSFUL_SIGNAL_COVERAGE = 0.70
MAX_WARNING_DELAY_BARS = 5.0
MAX_CONFIRMED_RETURN_DEGRADATION = 0.01

PREDECLARED_SENSITIVITIES: Mapping[str, tuple[float | int, ...]] = {
    "breakout_relative_volume": (1.20, 1.40, 1.60),
    "near_breakout_distance_pct": (0.025, 0.035, 0.050),
    "state_score_near": (55.0, 58.0, 62.0),
    "state_score_forming": (40.0, 45.0, 50.0),
    "extended_from_pivot_pct": (0.10, 0.12, 0.15),
    "extended_atr_from_sma20": (2.0, 2.5, 3.0),
    "failed_breakout_buffer_pct": (0.010, 0.015, 0.020),
    "breakout_confirmation_bars": (1, 2, 3),
}

COMPONENTS = ("trend", "momentum", "relative_strength", "volume", "base", "breakout")


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def methodology_descriptor(universe: Mapping[str, Any]) -> dict[str, Any]:
    """Stable lock for methodology; excludes data-dependent dates and outcomes."""
    config = asdict(TechnicalConfig())
    return {
        "experiment_version": PHASE8C2_EXPERIMENT_VERSION,
        "model_version": TECHNICAL_MODEL_VERSION,
        "technical_config": config,
        "universe_version": universe["version"],
        "requested_symbols": [item["ticker"] for item in universe["assets"]],
        "feed": universe["feed"],
        "adjustment": universe["adjustment"],
        "historical_start": universe["start"],
        "walk_forward_split": WALK_FORWARD_SPLIT.isoformat(),
        "quarantine_coverage": {
            "minimum_accepted_equities": 54,
            "required_benchmark_count": 12,
            "minimum_equities_per_sector": 2,
        },
        "predeclared_sensitivities": PREDECLARED_SENSITIVITIES,
    }


def methodology_fingerprint(universe: Mapping[str, Any]) -> str:
    return _canonical_hash(methodology_descriptor(universe))


def baseline_output_fingerprint(summary: Mapping[str, Any]) -> str:
    """Hash Run #4 comparable aggregate fields, never raw bars or provider data."""
    keys = (
        "model_version", "universe_version", "feed", "adjustment",
        "requested_securities", "securities_with_history", "security_symbols",
        "total_bars", "earliest_bar", "latest_bar", "state_counts",
        "transition_counts", "state_outcomes", "score_buckets",
        "security_type_outcomes", "sector_outcomes", "regime_outcomes",
        "liquidity_outcomes", "volatility_outcomes", "market_cap_outcomes",
        "data_quality", "coverage_policy", "walk_forward",
    )
    return _canonical_hash({key: summary.get(key) for key in keys})


def verify_run4_baseline(
    locked_summary: Mapping[str, Any], reproduced_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail exact-date drift; classify later end dates without calling them methodology drift."""
    invariant_keys = ("model_version", "universe_version", "feed", "adjustment", "requested_securities")
    mismatches = [key for key in invariant_keys if locked_summary.get(key) != reproduced_summary.get(key)]
    if mismatches:
        raise ValueError("RUN4_METHODOLOGY_METADATA_MISMATCH:" + ",".join(mismatches))
    locked_latest = str(locked_summary.get("latest_bar") or "")
    current_latest = str(reproduced_summary.get("latest_bar") or "")
    locked_fingerprint = baseline_output_fingerprint(locked_summary)
    reproduced_fingerprint = baseline_output_fingerprint(reproduced_summary)
    exact = locked_fingerprint == reproduced_fingerprint
    if locked_latest == current_latest and not exact:
        raise ValueError("RUN4_BASELINE_DRIFT_AT_SAME_END_DATE")
    return {
        "locked_run_number": LOCKED_RUN_NUMBER,
        "locked_run_id": LOCKED_RUN_ID,
        "locked_run_head_sha": LOCKED_RUN_HEAD_SHA,
        "locked_artifact_digest": LOCKED_RUN_ARTIFACT_DIGEST,
        "locked_output_fingerprint": locked_fingerprint,
        "reproduced_output_fingerprint": reproduced_fingerprint,
        "locked_latest_bar": locked_latest,
        "reproduced_latest_bar": current_latest,
        "status": "EXACT_REPRODUCTION" if exact else "CONSISTENT_METHODOLOGY_END_DATE_DIFFERENCE",
        "exact_output_match": exact,
        "end_date_difference_reported": locked_latest != current_latest,
    }


def unique_variants() -> tuple[tuple[str, str | None, float | int | None, TechnicalConfig], ...]:
    """Return V1 once plus sixteen unique one-factor variants (not 24 duplicate replays)."""
    baseline = TechnicalConfig()
    output: list[tuple[str, str | None, float | int | None, TechnicalConfig]] = [("V1_BASELINE", None, None, baseline)]
    for field, values in PREDECLARED_SENSITIVITIES.items():
        current = getattr(baseline, field)
        for value in values:
            if value == current:
                continue
            output.append((f"{field}={value}", field, value, replace(baseline, **{field: value})))
    return tuple(output)


def _mean(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return statistics.fmean(present) if present else None


def _research_summary(events: Sequence[CalibrationEvent]) -> dict[str, Any]:
    """Extend locked V1 aggregates without changing the Run #4 baseline schema."""
    output = dict(summarize_events(events))
    for horizon in HORIZONS:
        spy = [event.spy_relative_returns[horizon] for event in events if event.spy_relative_returns[horizon] is not None]
        sector = [event.sector_relative_returns[horizon] for event in events if event.sector_relative_returns[horizon] is not None]
        output[f"mean_spy_relative_return_{horizon}d"] = _mean(spy)
        output[f"median_spy_relative_return_{horizon}d"] = statistics.median(spy) if spy else None
        output[f"mean_sector_relative_return_{horizon}d"] = _mean(sector)
        output[f"median_sector_relative_return_{horizon}d"] = statistics.median(sector) if sector else None
    return output


def _near_transition_metrics(events: Sequence[CalibrationEvent]) -> dict[str, Any]:
    by_ticker: dict[str, list[CalibrationEvent]] = defaultdict(list)
    for event in sorted(events, key=lambda item: (item.ticker, item.index)):
        by_ticker[event.ticker].append(event)
    near_events = [event for event in events if event.state == TechnicalState.NEAR_BREAKOUT]
    confirmed_leads: list[int] = []
    failed_leads: list[int] = []
    confirmed = failed = 0
    for near in near_events:
        later = [item for item in by_ticker[near.ticker] if item.index > near.index]
        terminal = None
        for item in later:
            if item.transition.startswith("NEAR_BREAKOUT->"):
                terminal = item
                break
            if item.state == TechnicalState.NEAR_BREAKOUT:
                break  # a later independent warning must not inherit this warning's outcome
        if terminal is None:
            continue
        lead = terminal.index - near.index
        if terminal.state == TechnicalState.BREAKOUT_CONFIRMED:
            confirmed += 1
            confirmed_leads.append(lead)
        elif terminal.state == TechnicalState.FAILED_BREAKOUT:
            failed += 1
            failed_leads.append(lead)
    total_resolved = confirmed + failed
    distances = [event.evidence.get("distance_to_pivot_pct") for event in near_events]
    volumes = [event.evidence.get("relative_volume") for event in near_events]
    component_means = {
        f"component_mean_{component}": _mean(event.components.get(component) for event in near_events)
        for component in COMPONENTS
    }
    return {
        **_research_summary(near_events),
        "near_to_confirmed": confirmed,
        "near_to_failed": failed,
        "resolved_transition_count": total_resolved,
        "transition_confirmation_rate": confirmed / total_resolved if total_resolved else None,
        "transition_failure_rate": failed / total_resolved if total_resolved else None,
        "mean_bars_to_confirmation": _mean(confirmed_leads),
        "median_bars_to_confirmation": statistics.median(confirmed_leads) if confirmed_leads else None,
        "mean_bars_to_failure": _mean(failed_leads),
        "median_bars_to_failure": statistics.median(failed_leads) if failed_leads else None,
        "mean_relative_volume": _mean(volumes),
        "median_relative_volume": statistics.median([float(v) for v in volumes if v is not None]) if any(v is not None for v in volumes) else None,
        "mean_breakout_distance_pct": _mean(distances),
        "median_breakout_distance_pct": statistics.median([float(v) for v in distances if v is not None]) if any(v is not None for v in distances) else None,
        "score_mean": _mean(event.score for event in near_events),
        "score_median": statistics.median([event.score for event in near_events]) if near_events else None,
        **component_means,
    }


def _confirmed_metrics(events: Sequence[CalibrationEvent]) -> dict[str, Any]:
    confirmed = [event for event in events if event.state == TechnicalState.BREAKOUT_CONFIRMED]
    from_near = [event for event in confirmed if event.transition == "NEAR_BREAKOUT->BREAKOUT_CONFIRMED"]
    distances = [event.evidence.get("breakout_distance_pct") for event in confirmed]
    leads = _lead_times(events, TechnicalState.BREAKOUT_CONFIRMED)
    return {
        **_research_summary(confirmed),
        "from_near_count": len(from_near),
        "mean_distance_above_pivot_pct": _mean(distances),
        "median_distance_above_pivot_pct": statistics.median([float(v) for v in distances if v is not None]) if any(v is not None for v in distances) else None,
        "mean_confirmation_delay_bars": _mean(leads),
        "median_confirmation_delay_bars": statistics.median(leads) if leads else None,
    }


def _lead_times(events: Sequence[CalibrationEvent], target: TechnicalState) -> list[int]:
    by_ticker: dict[str, list[CalibrationEvent]] = defaultdict(list)
    for event in sorted(events, key=lambda item: (item.ticker, item.index)):
        by_ticker[event.ticker].append(event)
    leads: list[int] = []
    for ticker_events in by_ticker.values():
        last_near: CalibrationEvent | None = None
        for event in ticker_events:
            if event.state == TechnicalState.NEAR_BREAKOUT:
                last_near = event
            elif event.transition.startswith("NEAR_BREAKOUT->"):
                if event.state == target and last_near is not None:
                    leads.append(event.index - last_near.index)
                last_near = None
    return leads


def _score_quality(events: Sequence[CalibrationEvent]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    ordered_metrics: dict[str, list[float]] = defaultdict(list)
    for low, high, label in SCORE_BUCKETS:
        bucket = [event for event in events if low <= event.score < high]
        summary = _research_summary(bucket)
        summary["confirmation_rate"] = (
            sum(event.state == TechnicalState.BREAKOUT_CONFIRMED for event in bucket) / len(bucket) if bucket else None
        )
        summary["state_failure_rate"] = (
            sum(event.state == TechnicalState.FAILED_BREAKOUT for event in bucket) / len(bucket) if bucket else None
        )
        rows[label] = summary
        for metric in ("confirmation_rate", "state_failure_rate", "failure_rate_20d", "mean_return_20d", "mean_spy_relative_return_20d", "mean_mfe_60", "mean_mae_60"):
            if summary.get(metric) is not None:
                ordered_metrics[metric].append(float(summary[metric]))
    monotonicity = {
        metric: _rank_order_score(values)
        for metric, values in ordered_metrics.items()
    }
    return {"buckets": rows, "monotonicity": monotonicity}


def _rank_order_score(values: Sequence[float]) -> float | None:
    """Signed fraction of adjacent bucket changes in the expected increasing direction."""
    if len(values) < 2:
        return None
    changes = [right - left for left, right in zip(values, values[1:])]
    return sum(1 if value > 0 else -1 if value < 0 else 0 for value in changes) / len(changes)


def _segment_rows(events: Sequence[CalibrationEvent]) -> dict[str, Any]:
    dimensions = {
        "period": lambda e: "PRE_2022_CALIBRATION" if e.timestamp < WALK_FORWARD_SPLIT else "POST_2022_VALIDATION",
        "year": lambda e: str(e.timestamp.year),
        "regime": lambda e: e.regime,
        "security_type": lambda e: e.security_type.value,
        "sector": lambda e: e.sector or "UNKNOWN",
        "market_cap": lambda e: e.market_cap_band or "UNAVAILABLE",
        "liquidity": lambda e: e.liquidity_band,
        "volatility": lambda e: e.volatility_band,
    }
    output: dict[str, Any] = {}
    for dimension, key in dimensions.items():
        groups: dict[str, list[CalibrationEvent]] = defaultdict(list)
        for event in events:
            groups[str(key(event))].append(event)
        output[dimension] = {
            value: {
                "all": _research_summary(rows),
                "near": _near_transition_metrics(rows),
                "confirmed": _confirmed_metrics(rows),
            }
            for value, rows in sorted(groups.items())
        }
    return output


def component_diagnostics(events: Sequence[CalibrationEvent]) -> dict[str, Any]:
    """Observational component ablation proxy; does not mutate weights or V1 behavior."""
    output: dict[str, Any] = {}
    for component in COMPONENTS:
        present = [event for event in events if component in event.components]
        median = statistics.median(event.components[component] for event in present) if present else None
        high = [event for event in present if median is not None and event.components[component] >= median]
        low = [event for event in present if median is not None and event.components[component] < median]
        output[component] = {
            "diagnostic_only": True,
            "component_removed": False,
            "median_component_score": median,
            "high_component": _research_summary(high),
            "low_component": _research_summary(low),
            "high_minus_low_failure_rate_20d": _difference(high, low, "failure_rate_20d"),
            "high_minus_low_return_20d": _difference(high, low, "mean_return_20d"),
            "high_minus_low_spy_relative_return_20d": _difference(high, low, "mean_spy_relative_return_20d"),
            "high_confirmation_rate": _state_rate(high, TechnicalState.BREAKOUT_CONFIRMED),
            "low_confirmation_rate": _state_rate(low, TechnicalState.BREAKOUT_CONFIRMED),
            "high_failed_state_rate": _state_rate(high, TechnicalState.FAILED_BREAKOUT),
            "low_failed_state_rate": _state_rate(low, TechnicalState.FAILED_BREAKOUT),
        }
    return output


def _difference(high: Sequence[CalibrationEvent], low: Sequence[CalibrationEvent], metric: str) -> float | None:
    high_value = _research_summary(high).get(metric)
    low_value = _research_summary(low).get(metric)
    return float(high_value) - float(low_value) if high_value is not None and low_value is not None else None


def _state_rate(events: Sequence[CalibrationEvent], state: TechnicalState) -> float | None:
    return sum(event.state == state for event in events) / len(events) if events else None


def summarize_variant(report: CalibrationReport) -> dict[str, Any]:
    calibration, validation = chronological_split(report.events, WALK_FORWARD_SPLIT)
    return {
        "event_count": len(report.events),
        "state_counts": dict(report.state_counts),
        "all": _research_summary(report.events),
        "near": _near_transition_metrics(report.events),
        "confirmed": _confirmed_metrics(report.events),
        "score_quality": _score_quality(report.events),
        "segments": _segment_rows(report.events),
        "walk_forward": {
            "split": WALK_FORWARD_SPLIT.isoformat(),
            "calibration": {"all": _research_summary(calibration), "near": _near_transition_metrics(calibration), "confirmed": _confirmed_metrics(calibration), "score_quality": _score_quality(calibration), "segments": _segment_rows(calibration)},
            "validation": {"all": _research_summary(validation), "near": _near_transition_metrics(validation), "confirmed": _confirmed_metrics(validation), "score_quality": _score_quality(validation), "segments": _segment_rows(validation)},
        },
    }


def run_sensitivities(
    dataset: HistoricalDataset, baseline_report: CalibrationReport | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, field, value, config in unique_variants():
        report = baseline_report if field is None and baseline_report is not None else build_calibration_report(dataset, TechnicalIntelligenceEngine(config))
        diagnostics = component_diagnostics(report.events) if field is None else None
        if diagnostics is not None:
            for component, row in diagnostics.items():
                peers = {
                    peer: correlation for peer, correlation in report.component_overlap[component].items()
                    if peer != component and correlation is not None
                }
                strongest_peer = max(peers, key=lambda peer: abs(float(peers[peer]))) if peers else None
                row["most_overlapping_component"] = strongest_peer
                row["most_overlapping_correlation"] = peers.get(strongest_peer) if strongest_peer else None
        results[name] = {
            "variant": name,
            "changed_field": field,
            "changed_value": value,
            "is_committed_v1": field is None,
            "summary": summarize_variant(report),
            "component_diagnostics": diagnostics,
        }
    return results


def candidate_assessment(results: Mapping[str, Any]) -> dict[str, Any]:
    """Predeclared fail-closed screen; can only emit research-candidate status."""
    baseline = results["V1_BASELINE"]["summary"]
    base_validation = baseline["walk_forward"]["validation"]
    base_near = base_validation["near"]
    base_confirmed = base_validation["confirmed"]
    rows = []
    for name, result in results.items():
        if name == "V1_BASELINE":
            continue
        validation = result["summary"]["walk_forward"]["validation"]
        near = validation["near"]
        confirmed = validation["confirmed"]
        base_failure = base_near.get("failure_rate_20d")
        failure = near.get("failure_rate_20d")
        base_successes = int(base_near.get("near_to_confirmed") or 0)
        successful_signal_coverage = int(near.get("near_to_confirmed") or 0) / base_successes if base_successes else 0.0
        delay = (near.get("mean_bars_to_confirmation") or 0.0) - (base_near.get("mean_bars_to_confirmation") or 0.0)
        base_return = base_confirmed.get("mean_return_20d")
        confirmed_return = confirmed.get("mean_return_20d")
        failure_improved = failure is not None and base_failure is not None and failure < base_failure
        failure_rate_change = float(failure) - float(base_failure) if failure is not None and base_failure is not None else None
        confirmed_preserved = (
            base_return is not None and confirmed_return is not None
            and confirmed_return >= base_return - MAX_CONFIRMED_RETURN_DEGRADATION
        )
        enough = int(near.get("n") or 0) >= MIN_NEAR_VALIDATION_EVENTS
        concentration = _concentration_assessment(validation["segments"])
        not_concentrated = not any(concentration.values())
        promising = all((failure_improved, successful_signal_coverage >= MIN_SUCCESSFUL_SIGNAL_COVERAGE, delay <= MAX_WARNING_DELAY_BARS, confirmed_preserved, enough, not_concentrated))
        rows.append({
            "variant": name,
            "designation": "PROMISING_RESEARCH_CANDIDATE" if promising else "NOT_PROMISING_UNDER_PREDECLARED_GATES",
            "approved_production_threshold": False,
            "post_2022_near_events": near.get("n"),
            "near_failure_improved": failure_improved,
            "near_failure_rate_change": failure_rate_change,
            "successful_signal_coverage_ratio": successful_signal_coverage,
            "warning_lead_time_change_bars": delay,
            "confirmed_performance_preserved": confirmed_preserved,
            "adequate_sample": enough,
            "not_one_segment_dependent": not_concentrated,
            "concentration_flags": concentration,
            "successful_early_warnings_retained": int(near.get("near_to_confirmed") or 0),
            "successful_early_warnings_sacrificed": max(0, base_successes - int(near.get("near_to_confirmed") or 0)),
        })
    return {
        "designation_boundary": "RESEARCH_ONLY_NO_PRODUCTION_APPROVAL_AUTHORITY",
        "gates": {
            "minimum_post_2022_near_events": MIN_NEAR_VALIDATION_EVENTS,
            "minimum_successful_signal_coverage_ratio": MIN_SUCCESSFUL_SIGNAL_COVERAGE,
            "maximum_warning_delay_bars": MAX_WARNING_DELAY_BARS,
            "maximum_confirmed_20d_return_degradation": MAX_CONFIRMED_RETURN_DEGRADATION,
            "must_improve_post_2022_near_failure_rate": True,
            "must_not_be_one_year_sector_or_regime_dependent": True,
        },
        "candidates": rows,
    }


def _concentration_assessment(segments: Mapping[str, Any]) -> dict[str, bool]:
    """Flag validation improvements with too little temporal/cross-sectional breadth."""
    def successes(dimension: str) -> dict[str, int]:
        return {key: int(row["near"].get("near_to_confirmed") or 0) for key, row in segments[dimension].items()}

    years, sectors, regimes = successes("year"), successes("sector"), successes("regime")
    def concentrated(values: Mapping[str, int], minimum_groups: int) -> bool:
        active = [value for value in values.values() if value >= 3]
        total = sum(values.values())
        return len(active) < minimum_groups or (total > 0 and max(values.values(), default=0) / total > 0.60)

    sector_total = sum(sectors.values())
    return {
        "one_year_dependent": concentrated(years, 2),
        "one_sector_dependent": concentrated(sectors, 2),
        "semiconductor_leadership_dependent": sector_total > 0 and sectors.get("Semiconductors", 0) / sector_total > 0.50,
        "one_regime_dependent": concentrated(regimes, 2),
    }
