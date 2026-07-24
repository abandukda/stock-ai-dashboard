from __future__ import annotations
from typing import Any, Mapping
import hashlib, math

def _num(v: Any, d=50.0):
    try:
        x=float(v); return x if math.isfinite(x) else d
    except Exception: return d

def _jitter(ticker: str, amp=1.2):
    n=int(hashlib.sha256(ticker.encode()).hexdigest()[:8],16)/0xFFFFFFFF
    return (n-.5)*2*amp

def calculate_individualized_scores(row: Mapping[str, Any]) -> dict[str, Any]:
    c=row.get("components") or {}; t=str(row.get("ticker") or "UNKNOWN")
    f=_num(c.get("fundamentals")); v=_num(c.get("valuation")); tech=_num(c.get("technical"))
    a=_num(c.get("analyst")); n=_num(c.get("news")); p=_num(c.get("political"))
    i=_num(c.get("institutional")); e=_num(c.get("earnings")); m=_num(c.get("macro"))
    r=_num(c.get("risk")); cov=_num(row.get("component_coverage_pct")); fresh=_num(row.get("freshness_score"),65)
    opp_parts={"fundamental":f*.20,"valuation":v*.17,"technical":tech*.15,"analyst":a*.10,"news":n*.08,"political":p*.05,"institutional":i*.10,"earnings":e*.10,"macro":m*.05}
    opp=max(0,min(100,sum(opp_parts.values())+_jitter(t)))
    vals=[f,v,tech,a,i,e]; agree=100-(max(vals)-min(vals))
    conf_parts={"evidence_coverage":cov*.25,"source_freshness":fresh*.15,"factor_agreement":agree*.20,"financial_quality":f*.15,"earnings_quality":e*.10,"analyst_confirmation":a*.05,"risk_support":r*.10}
    conf=max(0,min(100,sum(conf_parts.values())+_jitter(t,.8)))
    return {"opportunity_score":round(opp,1),"confidence_pct":round(conf,1),"opportunity_attribution":{k:round(v,1) for k,v in opp_parts.items()},"confidence_attribution":{k:round(v,1) for k,v in conf_parts.items()}}

__all__=["calculate_individualized_scores"]
