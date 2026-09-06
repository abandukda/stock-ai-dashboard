"""Completed-session volume discovery reconciled to canonical ATLAS actions."""
from __future__ import annotations
from typing import Any,Mapping,Sequence

VERSION="ATLAS_VOLUME_SCREENER_V1"
def build_volume_screener(rows: Sequence[Mapping[str,Any]]) -> list[dict[str,Any]]:
    out=[]
    for row in rows:
        e=dict(row.get("canonical_investment_evaluation") or {}); volume=dict(e.get("volume_intelligence") or {}); tech=dict(e.get("technical_confirmation") or {}); rvol=volume.get("relative_volume")
        if volume.get("status")!="AVAILABLE" or rvol is None: continue
        confirmed=tech.get("state")=="BREAKOUT_CONFIRMED" and volume.get("volume_confirmed") is True
        if confirmed: state="BREAKOUT_CONFIRMED"
        elif tech.get("state")=="FAILED_BREAKOUT": state="FAILED_BREAKOUT"
        elif tech.get("state")=="NEAR_BREAKOUT": state="NEAR_BREAKOUT"
        elif float(rvol)>=1.4: state="VOLUME_SURGE"
        elif float(rvol)>=1.15: state="HIGH_VOLUME_NO_ACTION"
        else: continue
        v=dict((e.get("atlas_valuation") or {}).get("professional_valuation_v2") or {});g=dict(e.get("guidance") or {});trade=dict(e.get("trade_plan") or {})
        catalysts=row.get("recent_catalysts") or e.get("recent_catalysts") or []
        risks=e.get("risk_factors") or row.get("risk_factors") or row.get("risk_tags") or []
        action=g.get("state")
        stars={"BUY_NOW":5.0,"ACCUMULATE":4.5,"WAIT_FOR_BETTER_ENTRY":4.0,"WAIT_FOR_CONFIRMATION":3.5,"DATA_LIMITED":2.5,"AVOID":1.0}.get(action)
        out.append({"ticker":row.get("ticker"),"company":row.get("company") or row.get("company_name"),"volume_state":state,"relative_volume":rvol,"dollar_volume":volume.get("average_dollar_volume") or row.get("dollar_volume"),"technical_state":tech.get("state"),"action":action,"action_stars":stars,"opportunity_thesis":g.get("opportunity_thesis"),"opportunity":e.get("opportunity"),"confidence":e.get("decision_confidence"),"price":(e.get("market_snapshot") or {}).get("price") or row.get("price"),"entry_low":trade.get("entry_low"),"entry_high":trade.get("entry_high"),"base_fair_value":v.get("atlas_base_fair_value"),"expected_return":v.get("atlas_expected_return"),"valuation_confidence":v.get("valuation_confidence"),"primary_risk":risks[0] if isinstance(risks,list) and risks else None,"latest_catalyst":catalysts[0] if isinstance(catalysts,list) and catalysts else None,"volume_evidence_id":volume.get("evidence_id"),"as_of":volume.get("as_of")})
    return sorted(out,key=lambda x:(-float(x["relative_volume"]),str(x["ticker"])))

__all__=["VERSION","build_volume_screener"]
