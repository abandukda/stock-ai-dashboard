from __future__ import annotations
from typing import Any, Mapping
from engines.research_enrichment_v105 import build_enriched_research_report

REQUIRED=("financials","analysts","earnings","news","political","ownership","technical")

def audit_research_completeness(row: Mapping[str, Any]) -> dict[str, Any]:
    report=build_enriched_research_report(row)
    findings=[]; available=0
    for name in REQUIRED:
        section=report[name]
        if section.get("status")=="available":
            available+=1
        else:
            findings.append({
                "severity":"HIGH" if name in {"financials","analysts","earnings"} else "MEDIUM",
                "section":name,
                "issue":"Section is unavailable",
                "recommended_fix":f"Map the provider payload for {name} into the V105 enrichment contract or add a live fallback.",
            })
    coverage=round(available/len(REQUIRED)*100.0,1)
    return {
        "version":"V105","ticker":report.get("ticker"),"coverage_pct":coverage,
        "available_sections":available,"total_sections":len(REQUIRED),
        "status":"PASS" if coverage==100 else "NEEDS_DATA","findings":findings,
    }

__all__=["audit_research_completeness"]
