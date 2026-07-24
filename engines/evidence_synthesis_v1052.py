from __future__ import annotations
from typing import Any, Mapping

def build_ai_guidance(report: Mapping[str,Any],trade_plan: Mapping[str,Any],scores: Mapping[str,Any]) -> dict[str,Any]:
    available=[]; missing=[]
    for key in ("financials","analysts","earnings","news","political","ownership","technical"):
        section=report.get(key) or {}
        (available if section.get("status")=="available" else missing).append(key)
    verdict=str(report.get("committee_verdict") or "MONITOR").replace("_"," ").title()
    horizon=(trade_plan.get("horizon") or {}).get("primary","Research / Monitor")
    entry=str(trade_plan.get("entry_status") or "UNAVAILABLE").replace("_"," ").title()
    summary=(f"Atlas rates this stock {verdict} with an opportunity score of {scores.get('opportunity_score')} and confidence of {scores.get('confidence_pct')}%. "
             f"The primary horizon is {horizon}. The current price condition is {entry}. "
             f"Evidence is available for {', '.join(available) if available else 'no major sections'}.")
    if missing: summary+=f" Confidence is constrained because {', '.join(missing)} remain unavailable."
    atlas=trade_plan.get("atlas_target"); analyst=trade_plan.get("analyst_average_target")
    comparison={"atlas_target":atlas,"analyst_average_target":analyst,"difference":None,"interpretation":"Insufficient target data."}
    if atlas is not None and analyst is not None:
        diff=round(float(atlas)-float(analyst),2); comparison["difference"]=diff
        comparison["interpretation"]="Atlas is more bullish than Wall Street." if diff>0 else "Atlas is more conservative than Wall Street." if diff<0 else "Atlas is aligned with Wall Street."
    return {"summary":summary,"target_comparison":comparison,"available_sections":available,"missing_sections":missing,
            "educational_disclaimer":"Illustrative educational guidance only. Stops and targets are not guaranteed."}

__all__=["build_ai_guidance"]
