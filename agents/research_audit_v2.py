
"""
Atlas V2 — Research Completeness and Wiring Audit
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import ast

from engines.atlas_research_builder_v2 import build_atlas_research_v2


ACTIVE_IMPORT_MARKERS = {
    "ui/research_report_v104.py": [
        "from ui.research_report_v2 import render_atlas_research_v2",
        "render_atlas_research_v2(row)",
    ],
    "ui/home_v104.py": [
        "Atlas V2 Institutional Intelligence",
    ],
}


def audit_v2_wiring(root: str | Path = ".") -> list[dict[str, Any]]:
    root = Path(root)
    findings = []

    for relative, markers in ACTIVE_IMPORT_MARKERS.items():
        path = root / relative
        if not path.exists():
            findings.append(
                {
                    "severity": "CRITICAL",
                    "file": relative,
                    "issue": "Required active file is missing.",
                }
            )
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in markers:
            if marker not in text:
                findings.append(
                    {
                        "severity": "CRITICAL",
                        "file": relative,
                        "issue": f"Active V2 marker is missing: {marker}",
                    }
                )

    old_path = root / "ui/research_report_v104.py"
    if old_path.exists():
        text = old_path.read_text(encoding="utf-8", errors="ignore")
        if "render_v105_research_report" in text:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "file": "ui/research_report_v104.py",
                    "issue": "Old V105 report renderer is still active.",
                }
            )

    return findings


def audit_research_row(row: Mapping[str, Any]) -> dict[str, Any]:
    report = build_atlas_research_v2(row)
    findings = []

    for name, section in (report.get("sections") or {}).items():
        completeness = float(section.get("completeness_pct") or 0)
        if completeness == 0:
            severity = (
                "HIGH"
                if name in {"financials", "earnings", "analysts", "technical"}
                else "MEDIUM"
            )
            findings.append(
                {
                    "severity": severity,
                    "section": name,
                    "issue": "Section has no populated structured data.",
                    "recommended_fix": (
                        f"Attach provider or scanner fields for {name} to the "
                        "canonical research row before rendering."
                    ),
                }
            )
        elif completeness < 70:
            findings.append(
                {
                    "severity": "MEDIUM",
                    "section": name,
                    "issue": f"Section is only {completeness:.1f}% complete.",
                    "recommended_fix": (
                        f"Map missing {name} fields into the canonical research row."
                    ),
                }
            )

    if not report.get("trade_plan", {}).get("actionable"):
        findings.append(
            {
                "severity": "HIGH",
                "section": "trade_plan",
                "issue": "Trade plan is unavailable because a current price is missing.",
                "recommended_fix": "Attach the latest quote before rendering the report.",
            }
        )

    return {
        "version": "V2.0-PHASE1",
        "ticker": report.get("ticker"),
        "research_completeness_pct": report.get(
            "research_completeness_pct"
        ),
        "status": "PASS" if not findings else "NEEDS_DATA",
        "findings": findings,
    }


__all__ = ["audit_research_row", "audit_v2_wiring"]
