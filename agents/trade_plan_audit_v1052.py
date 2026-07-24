from __future__ import annotations
from typing import Any, Mapping
from engines.trade_plan_v1052 import validate_trade_plan

def audit_trade_plan(plan: Mapping[str,Any]) -> dict[str,Any]:
    findings=[]
    for error in validate_trade_plan(plan):
        findings.append({"severity":"CRITICAL","issue":error})
    quote=plan.get("quote") or {}
    for field in ("price","price_as_of","quote_source"):
        if not quote.get(field):
            findings.append({"severity":"HIGH","issue":f"Quote field missing: {field}"})
    if plan.get("actionable") and not plan.get("educational_only"):
        findings.append({"severity":"HIGH","issue":"Plan is not labeled educational-only."})
    rr=plan.get("risk_reward_target_1")
    try:
        if float(rr)<1.25:
            findings.append({"severity":"MEDIUM","issue":"Target 1 risk/reward is below 1.25."})
    except Exception:
        findings.append({"severity":"HIGH","issue":"Risk/reward is unavailable."})
    return {"version":"V105.2","status":"PASS" if not findings else "NEEDS_ATTENTION","findings":findings}

__all__=["audit_trade_plan"]
