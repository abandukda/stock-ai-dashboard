"""Immutable, point-in-time ATLAS recommendation performance foundation."""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping, Sequence

VERSION="ATLAS_PERFORMANCE_SNAPSHOT_V1"
HORIZONS=(1,5,20,63,126,252)
ACTION_STARS={"BUY_NOW":5.0,"ACCUMULATE":4.5,"WAIT_FOR_BETTER_ENTRY":4.0,"WAIT_FOR_CONFIRMATION":3.5,"DATA_LIMITED":2.5,"AVOID":1.0}

def _num(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def build_snapshot(row: Mapping[str,Any]) -> dict[str,Any]:
    e=dict(row.get("canonical_investment_evaluation") or {}); v=dict((e.get("atlas_valuation") or {}).get("professional_valuation_v2") or {}); g=dict(e.get("guidance") or {}); market=dict(e.get("market_snapshot") or {}); trade=dict(e.get("trade_plan") or {})
    pillars={k:(e.get(k) or {}).get("score") for k in ("technical_quality","fundamental_quality","valuation_quality","risk_quality","entry_quality","volume_quality")}
    action=g.get("state")
    payload={"version":VERSION,"ticker":row.get("ticker") or row.get("symbol"),"timestamp":e.get("evaluated_at"),"action":action,"action_stars":ACTION_STARS.get(action),"opportunity_thesis":g.get("opportunity_thesis") or e.get("opportunity_thesis"),"opportunity":e.get("opportunity"),"decision_confidence":e.get("decision_confidence"),"coverage":e.get("component_coverage"),"six_pillars":pillars,"price":market.get("price") or row.get("current_price") or row.get("price"),"base_fair_value":v.get("atlas_base_fair_value"),"fair_value_low":v.get("atlas_fair_value_low"),"fair_value_high":v.get("atlas_fair_value_high"),"entry_low":trade.get("entry_low"),"entry_high":trade.get("entry_high"),"stop":trade.get("stop") or trade.get("stop_loss"),"technical_target":trade.get("target_1") or trade.get("target"),"technical_state":(e.get("technical_confirmation") or {}).get("state"),"valuation_confidence":v.get("valuation_confidence"),"methodology_version":e.get("methodology_version"),"valuation_methodology_version":v.get("valuation_methodology_version"),"registry_version":e.get("methodology_registry_version"),"market_regime":((e.get("technical_confirmation") or {}).get("evidence") or {}).get("market_regime"),"return_policy":{"price_basis":"unadjusted_close_unless_canonical_adjustment_is_published","dividends":"excluded_until_canonical_total_return_series_is_available","transaction_costs":"excluded","benchmark":"optional_observational_context","horizons":"completed_trading_sessions"}}
    payload["snapshot_id"]=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()[:24]
    return payload

def append_snapshots(path: Path, snapshots: Sequence[Mapping[str,Any]]) -> int:
    path.parent.mkdir(parents=True,exist_ok=True); existing=set(); points={}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                prior=json.loads(line);existing.add(prior["snapshot_id"])
                points[(prior.get("ticker"),prior.get("timestamp"))]=prior["snapshot_id"]
            except Exception: continue
    fresh=[]
    for raw in snapshots:
        s=dict(raw);point=(s.get("ticker"),s.get("timestamp"));prior_id=points.get(point)
        if prior_id and prior_id!=s.get("snapshot_id"):
            raise ValueError("IMMUTABLE_SNAPSHOT_CONFLICT")
        if s.get("snapshot_id") not in existing:
            fresh.append(s);existing.add(s.get("snapshot_id"));points[point]=s.get("snapshot_id")
    if fresh:
        with path.open("a",encoding="utf-8") as handle:
            for item in fresh: handle.write(json.dumps(item,sort_keys=True)+"\n")
    return len(fresh)

def mature_snapshot(snapshot: Mapping[str,Any], bars: Sequence[Mapping[str,Any]], benchmark_bars: Sequence[Mapping[str,Any]]=()) -> list[dict[str,Any]]:
    start=_num(snapshot.get("price")); stamp=str(snapshot.get("timestamp") or "")
    def after_snapshot(item):
        observed=str(item.get("timestamp") or item.get("date") or item.get("datetime") or "")
        return not observed or not stamp or observed>stamp
    future=[x for x in bars if after_snapshot(x) and _num(x.get("close")) is not None]
    prices=[_num(x.get("close")) for x in future]
    bench=[_num(x.get("close")) for x in benchmark_bars if after_snapshot(x)]; bench=[x for x in bench if x is not None]
    if not start:return []
    out=[]
    for h in HORIZONS:
        if len(prices)<h: continue
        window=prices[:h]; bar_window=future[:h]; ret=window[-1]/start-1; peak=start; draw=0
        for p in window: peak=max(peak,p);draw=min(draw,p/peak-1)
        mfe=max(window)/start-1;mae=min(window)/start-1
        bret=(bench[h-1]/bench[0]-1) if len(bench)>=h and bench[0] else None
        target=_num(snapshot.get("technical_target"));stop=_num(snapshot.get("stop"));entry_low=_num(snapshot.get("entry_low"));entry_high=_num(snapshot.get("entry_high"))
        target_day=next((i for i,b in enumerate(bar_window,1) if target is not None and (_num(b.get("high")) or _num(b.get("close")))>=target),None)
        stop_day=next((i for i,b in enumerate(bar_window,1) if stop is not None and (_num(b.get("low")) or _num(b.get("close")))<=stop),None)
        entry_day=next((i for i,b in enumerate(bar_window,1) if entry_low is not None and entry_high is not None and (_num(b.get("low")) or _num(b.get("close")))<=entry_high and (_num(b.get("high")) or _num(b.get("close")))>=entry_low),None)
        target_before_stop=(target_day<stop_day if target_day and stop_day else True if target_day else False if stop_day else None)
        outcome="TARGET_REACHED" if target_day and (not stop_day or target_day<stop_day) else "STOP_REACHED" if stop_day else "POSITIVE" if ret>0 else "NEGATIVE" if ret<0 else "FLAT"
        dimensions={"action":snapshot.get("action"),"opportunity_thesis":snapshot.get("opportunity_thesis"),"opportunity":snapshot.get("opportunity"),"decision_confidence":snapshot.get("decision_confidence"),"valuation_confidence":snapshot.get("valuation_confidence"),"technical_quality":(snapshot.get("six_pillars") or {}).get("technical_quality"),"fundamental_quality":(snapshot.get("six_pillars") or {}).get("fundamental_quality")}
        out.append({"snapshot_id":snapshot["snapshot_id"],"ticker":snapshot["ticker"],"horizon_sessions":h,"price_return":ret,"benchmark_return":bret,"benchmark_relative_return":ret-bret if bret is not None else None,"max_drawdown":draw,"mfe":mfe,"mae":mae,"time_to_mfe":window.index(max(window))+1,"time_to_mae":window.index(min(window))+1,"entry_reached":entry_day is not None,"entry_reached_session":entry_day,"target_reached":target_day is not None,"target_reached_session":target_day,"stop_reached":stop_day is not None,"stop_reached_session":stop_day,"target_before_stop":target_before_stop,"holding_period_outcome":outcome,"time_to_first_material_outcome":min(x for x in (target_day,stop_day) if x is not None) if target_day or stop_day else None,**dimensions})
    return out

def aggregate(records: Sequence[Mapping[str,Any]], key="action") -> list[dict[str,Any]]:
    groups={}
    for r in records:
        if _num(r.get("price_return")) is not None: groups.setdefault(r.get(key) or "UNKNOWN",[]).append(r)
    return [{key:k,"sample_count":len(v),"average_return":mean(x["price_return"] for x in v),"median_return":median(x["price_return"] for x in v),"win_rate":mean(x["price_return"]>0 for x in v),"average_relative_return":mean(x["benchmark_relative_return"] for x in v if x.get("benchmark_relative_return") is not None) if any(x.get("benchmark_relative_return") is not None for x in v) else None,"worst_drawdown":min(x["max_drawdown"] for x in v)} for k,v in groups.items()]

def confidence_bucket(value: Any) -> str:
    number=_num(value)
    return "UNAVAILABLE" if number is None else "HIGH" if number>=85 else "MODERATE" if number>=70 else "LOW"

__all__=["VERSION","HORIZONS","ACTION_STARS","aggregate","append_snapshots","build_snapshot","confidence_bucket","mature_snapshot"]
