"""Controlled repair planning. This module never pushes to main."""

from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import json
from typing import Any, Iterable, Mapping


RISKY_KEYWORDS = (
    "scoring", "weight", "threshold", "valuation", "position_size",
    "authentication", "secret", "permission", "delete",
)


def classify_risk(issue: Mapping[str, Any]) -> str:
    text = " ".join(
        str(issue.get(key) or "")
        for key in ("category", "element", "recommendation", "actual")
    ).lower()
    return "HIGH_APPROVAL_REQUIRED" if any(word in text for word in RISKY_KEYWORDS) else "STANDARD_REVIEW"


def create_fix_plan(issues: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        likely = issue.get("likely_files") or ["UNDER_REVIEW"]
        for file_name in likely:
            groups[str(file_name)].append(dict(issue))

    actions = []
    for file_name, related in groups.items():
        severities = {item.get("severity", "MEDIUM") for item in related}
        risk = max((classify_risk(item) for item in related), default="STANDARD_REVIEW")
        actions.append({
            "file": file_name,
            "issue_count": len(related),
            "severities": sorted(severities),
            "approval_level": risk,
            "action": (
                "Generate a complete replacement file plus regression tests. "
                "Do not merge automatically."
            ),
            "issues": related,
        })

    actions.sort(
        key=lambda item: (
            0 if "CRITICAL" in item["severities"] else 1,
            0 if "HIGH" in item["severities"] else 1,
            -item["issue_count"],
        )
    )
    return {
        "mode": "CONTROLLED_REPAIR_PLANNING",
        "direct_production_writes": False,
        "human_approval_required": True,
        "replacement_file_actions": actions,
    }


def write_fix_plan(report: Mapping[str, Any], output_dir: str | Path) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    plan = create_fix_plan(report.get("issues") or [])
    path = output / "atlas_fix_plan.json"
    path.write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")
    return path
