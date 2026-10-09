"""Preregistered comparisons for prospective shadow-methodology validation."""
from __future__ import annotations


VALIDATION_PLAN = {
    "exit_discrimination": {
        "exposure": "EXIT",
        "comparators": ["NON_EXIT_SAME_SCAN", "SPY", "SECTOR_ETF", "MATCHED_CONTROLS"],
        "outcomes": [1, 5, 21, 63, 126, 252],
    },
    "trim_overvaluation": {
        "exposure": "TRIM", "comparator": "HOLD_SAME_THESIS_STATE",
        "outcomes": [1, 5, 21, 63, 126, 252],
    },
    "technical_incremental_value": {
        "exposure": "DETERIORATING_OR_BROKEN", "comparator": "HEALTHY_SAME_THESIS_AND_VALUATION",
        "outcomes": [1, 5, 21, 63, 126, 252],
    },
    "matching_covariates": ["sector", "volatility", "momentum", "beta", "size", "scan_date"],
    "inference": "CLUSTER_BY_SCAN_DATE_OR_COHORT",
    "threshold_tuning": "PROHIBITED_WITHIN_METHODOLOGY_VERSION",
    "survivorship_filtering": "PROHIBITED",
}


def validate_plan() -> bool:
    return (
        VALIDATION_PLAN["threshold_tuning"] == "PROHIBITED_WITHIN_METHODOLOGY_VERSION"
        and VALIDATION_PLAN["survivorship_filtering"] == "PROHIBITED"
        and set(VALIDATION_PLAN["matching_covariates"])
        == {"sector", "volatility", "momentum", "beta", "size", "scan_date"}
    )


__all__ = ["VALIDATION_PLAN", "validate_plan"]
