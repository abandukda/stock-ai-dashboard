"""Bounded orchestration contracts for ATLAS Full QA.

This module contains no investment logic.  It makes the release QA stages,
budgets, completion rules, and evidence packaging explicit and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import time
from typing import Any, Mapping, Sequence


RELEASE_FULL = "RELEASE_FULL"
FAST_PREVIEW = "FAST_PREVIEW"
QA_TIERS = (RELEASE_FULL, FAST_PREVIEW)
STAGES = (
    "identity", "deterministic_qa", "startup", "auth", "structural",
    "interaction", "visual", "analysis", "packaging", "promotion",
)
RELEASE_RUNTIME_TARGET_SECONDS = 60 * 60
RELEASE_RUNTIME_CEILING_SECONDS = 90 * 60


@dataclass
class TimingReport:
    started: float = field(default_factory=time.monotonic)
    stages: dict[str, float] = field(default_factory=lambda: {name: 0.0 for name in STAGES})
    per_page: dict[str, float] = field(default_factory=dict)
    per_ticker: dict[str, float] = field(default_factory=dict)
    per_viewport: dict[str, float] = field(default_factory=dict)
    per_interaction_type: dict[str, float] = field(default_factory=dict)
    retry_counts: dict[str, int] = field(default_factory=dict)
    timeouts: list[dict[str, Any]] = field(default_factory=list)
    screenshot_count: int = 0
    deduplicated_screenshot_count: int = 0
    dom_snapshot_count: int = 0
    browser_navigation_count: int = 0
    calls_avoided: int = 0

    def record_stage(self, name: str, seconds: float) -> None:
        if name not in self.stages:
            raise ValueError(f"UNKNOWN_QA_STAGE:{name}")
        self.stages[name] += max(0.0, float(seconds))

    def payload(self) -> dict[str, Any]:
        total = max(0.0, time.monotonic() - self.started)
        return {
            "schema_version": "ATLAS_QA_TIMING_V1",
            "total_seconds": round(total, 3),
            "runtime_target_seconds": RELEASE_RUNTIME_TARGET_SECONDS,
            "runtime_ceiling_seconds": RELEASE_RUNTIME_CEILING_SECONDS,
            "runtime_budget_status": "EXCEEDED" if total > RELEASE_RUNTIME_CEILING_SECONDS else "WITHIN_CEILING",
            "stages": {key: round(value, 3) for key, value in self.stages.items()},
            "per_page": self.per_page,
            "per_ticker": self.per_ticker,
            "per_viewport": self.per_viewport,
            "per_interaction_type": self.per_interaction_type,
            "retry_counts": self.retry_counts,
            "timeouts": self.timeouts,
            "screenshot_count": self.screenshot_count,
            "deduplicated_screenshot_count": self.deduplicated_screenshot_count,
            "dom_snapshot_count": self.dom_snapshot_count,
            "browser_navigation_count": self.browser_navigation_count,
            "calls_avoided": self.calls_avoided,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.payload(), indent=2) + "\n", encoding="utf-8")


def validate_tier(qa_tier: str, *, promotion_requested: bool) -> str:
    tier = str(qa_tier or RELEASE_FULL).upper()
    if tier not in QA_TIERS:
        raise ValueError(f"UNKNOWN_QA_TIER:{tier}")
    if promotion_requested and tier != RELEASE_FULL:
        raise ValueError("FAST_PREVIEW_CANNOT_PROMOTE")
    return tier


def blocking_findings(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = ((report.get("sheets") or {}).get("Validation_Failures") or [])
    return [dict(row) for row in rows if str(row.get("severity") or "").upper() in {"P0", "P1", "P2"}]


def visual_completion_contract(
    summary: Mapping[str, Any], interactions: Sequence[Mapping[str, Any]],
    screenshots: Sequence[Mapping[str, Any]], *, mobile_required: bool,
) -> dict[str, Any]:
    required = [item for item in interactions if item.get("required", True)]
    passed = [item for item in required if all((
        item.get("click_success") is True,
        item.get("opened") is True,
        item.get("collapse_success") is True,
        item.get("required_content_present", True) is True,
    ))]
    desktop = sum(str(item.get("viewport", "")).lower() == "desktop" for item in screenshots)
    mobile = sum(str(item.get("viewport", "")).lower() == "mobile" for item in screenshots)
    coverage = 100.0 if not required else 100.0 * len(passed) / len(required)
    checks = {
        "finished": summary.get("finished") is True,
        "authentication_success": summary.get("authentication_success") is True,
        "required_pages_passed": summary.get("required_pages_passed") is True,
        "required_interactions_coverage": coverage == 100.0,
        "mobile_required_coverage": (not mobile_required) or mobile > 0,
        "screenshot_manifest_valid": bool(screenshots) and desktop > 0,
        "candidate_binding_valid": summary.get("candidate_binding_valid") is True,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "controls_required": len(required),
        "controls_passed": len(passed),
        "interaction_coverage_pct": round(coverage, 3),
        "desktop_screenshot_count": desktop,
        "mobile_screenshot_count": mobile,
    }


def write_early_blocker_bundle(output_dir: Path, *, candidate: Mapping[str, Any], findings: Sequence[Mapping[str, Any]], timing: TimingReport) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    blockers = [dict(item) for item in findings]
    summary = {
        "status": "FULL_QA_BLOCKED_BEFORE_VISUAL_CRAWL",
        "candidate": dict(candidate),
        "blocking_count": len(blockers),
        "browser_launched": False,
    }
    (output_dir / "qa_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output_dir / "blocking_findings.json").write_text(json.dumps(blockers, indent=2) + "\n", encoding="utf-8")
    timing.write(output_dir / "qa_timing_report.json")

