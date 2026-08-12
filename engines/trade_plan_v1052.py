from __future__ import annotations
from typing import Any, Mapping
import math

from engines.semantic_fields import scanner_trade_plan

def _num(v: Any, d=None):
    try:
        if v is None or v == "": return d
        x=float(str(v).replace("$","").replace(",","").replace("%","").strip())
        return x if math.isfinite(x) else d
    except Exception:
        return d

def classify_horizon(row: Mapping[str, Any]) -> dict[str, Any]:
    c=row.get("components") or {}
    f=_num(c.get("fundamentals"),50); t=_num(c.get("technical"),50)
    v=_num(c.get("valuation"),50); r=_num(c.get("risk"),50)
    g=_num(row.get("revenue_growth_pct") or (row.get("financials") or {}).get("revenue_growth_pct"),0)
    items=[]
    if t>=68: items.append({"label":"Swing","range":"2–8 weeks"})
    if t>=58 and v>=55: items.append({"label":"Position","range":"3–12 months"})
    if f>=70 and r>=58 and g>=8: items.append({"label":"Long-Term","range":"3–5 years"})
    if not items: items=[{"label":"Research / Monitor","range":"No active horizon"}]
    primary="Long-Term" if any(x["label"]=="Long-Term" for x in items) else items[0]["label"]
    return {"primary":primary,"eligible_horizons":items}

def build_trade_plan(row: Mapping[str, Any], quote: Mapping[str, Any]) -> dict[str, Any]:
    p=_num(quote.get("price"))
    if not p or p<=0:
        return {"status":"UNAVAILABLE","actionable":False,"reason":"Valid current price required.","quote":dict(quote)}
    persisted = scanner_trade_plan(row)
    if all(persisted.get(key) is not None for key in ("entry_low", "entry_high", "stop_loss", "trade_target_1", "trade_target_2")):
        entry_low = persisted["entry_low"]
        entry_high = persisted["entry_high"]
        stop = persisted["stop_loss"]
        target_1 = persisted["trade_target_1"]
        target_2 = persisted["trade_target_2"]
        return {
            "status":"CURRENT","actionable":True,"educational_only":True,
            "source":"Persisted scanner trade plan",
            "current_price":round(p,2),"entry_low":entry_low,"entry_high":entry_high,
            "stop_loss":stop,"target_1":target_1,"target_2":target_2,
            "stretch_target":None,"atlas_target":None,"analyst_average_target":None,
            "risk_per_share":round(max(p-stop,0.01),2),
            "risk_reward_target_1":persisted["risk_reward"],
            "risk_reward_target_2":round((target_2-p)/max(p-stop,0.01),2),
            "entry_status":"IN_ENTRY_ZONE" if entry_low<=p<=entry_high else "BELOW_ENTRY_ZONE" if p<entry_low else "ABOVE_PREFERRED_ENTRY",
            "horizon":classify_horizon(row),"quote":dict(quote),
            "education":{
                "target_1":"Consider trimming part of the position and reducing risk.",
                "target_2":"Consider another partial sale or raising the stop.",
                "stop_loss":"Risk-control level, not a guaranteed execution price.",
            },
        }
    tech=row.get("technical") or {}
    atr=_num(row.get("atr") or tech.get("atr"),p*0.025)
    support=_num(row.get("support") or tech.get("support"),p-atr)
    resistance=_num(row.get("resistance") or tech.get("resistance"))
    atlas=_num(row.get("validated_fair_value") or row.get("atlas_fair_value"))
    analysts=row.get("analysts") or {}
    raw=row.get("raw") or {}
    analyst=_num(row.get("analyst_target_mean") or analysts.get("analyst_target_mean") or raw.get("Analyst Target"))
    entry_low=max(0.01,support-0.20*atr)
    entry_high=max(entry_low+0.10*atr,min(p+0.15*atr,support+0.55*atr))
    stop=max(0.01,min(support-0.65*atr,entry_low-0.75*atr))
    risk=max(entry_high-stop,0.01)
    t1=resistance if resistance and resistance>entry_high else entry_high+1.5*risk
    credible=[x for x in (atlas,analyst) if x and x>entry_high]
    t2=max(t1,min(credible) if credible else entry_high+2.5*risk)
    stretch=max(t2,max(credible) if credible else entry_high+3*risk)
    chase=max(entry_high+0.5*atr,t1-0.5*risk)
    status=("IN_ENTRY_ZONE" if entry_low<=p<=entry_high else "BELOW_ENTRY_ZONE" if p<entry_low else "DO_NOT_CHASE" if p>chase else "ABOVE_PREFERRED_ENTRY")
    return {
        "status":"CURRENT","actionable":True,"educational_only":True,
        "current_price":round(p,2),"entry_low":round(entry_low,2),"entry_high":round(entry_high,2),
        "do_not_chase":round(chase,2),"stop_loss":round(stop,2),"target_1":round(t1,2),
        "target_2":round(t2,2),"stretch_target":round(stretch,2),
        "atlas_target":round(atlas,2) if atlas else None,
        "analyst_average_target":round(analyst,2) if analyst else None,
        "risk_per_share":round(risk,2),
        "risk_reward_target_1":round((t1-entry_high)/risk,2),
        "risk_reward_target_2":round((t2-entry_high)/risk,2),
        "entry_status":status,"horizon":classify_horizon(row),"quote":dict(quote),
        "education":{
            "target_1":"Consider trimming part of the position and reducing risk.",
            "target_2":"Consider another partial sale or raising the stop.",
            "stretch_target":"Reserve for a smaller runner while the thesis remains intact.",
            "stop_loss":"Risk-control level, not a guaranteed execution price."
        }
    }

def validate_trade_plan(plan: Mapping[str, Any]) -> list[str]:
    if not plan.get("actionable"): return []
    a,b,s,t1,t2=[_num(plan.get(k)) for k in ("entry_low","entry_high","stop_loss","target_1","target_2")]
    if None in (a,b,s,t1,t2): return ["Required plan values are missing."]
    return [] if s<a<=b<t1<=t2 else ["Trade-plan levels are not logically ordered."]

__all__=["build_trade_plan","classify_horizon","validate_trade_plan"]
