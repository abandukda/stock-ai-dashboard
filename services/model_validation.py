"""Internal-only observational validation over immutable ATLAS snapshots."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from typing import Any,Mapping,Sequence
from services.performance_tracking import aggregate,confidence_bucket
from services.performance_tracking import mature_snapshot

VERSION="ATLAS_MODEL_VALIDATION_V1"
MIN_SAMPLE=20
CUSTOMER_PERFORMANCE_ENABLED=False

def score_bucket(value:Any)->str:
    return confidence_bucket(value)

def enrich_buckets(records:Sequence[Mapping[str,Any]])->list[dict[str,Any]]:
    out=[]
    for raw in records:
        row=dict(raw)
        for source,target in (("opportunity","opportunity_bucket"),("decision_confidence","decision_confidence_bucket"),("valuation_confidence","valuation_confidence_bucket"),("technical_quality","technical_quality_bucket"),("fundamental_quality","fundamental_quality_bucket")):
            row[target]=score_bucket(row.get(source))
        out.append(row)
    return out

def governed_aggregate(records:Sequence[Mapping[str,Any]],key:str,minimum:int=MIN_SAMPLE)->list[dict[str,Any]]:
    results=[]
    for row in aggregate(enrich_buckets(records),key=key):
        row["publication_status"]="OBSERVATIONAL" if row["sample_count"]>=minimum else "INSUFFICIENT_MATURED_SAMPLE"
        if row["publication_status"]!="OBSERVATIONAL":
            for metric in ("average_return","median_return","win_rate","average_relative_return","worst_drawdown"):row[metric]=None
        results.append(row)
    return results

def validation_report(snapshots:Sequence[Mapping[str,Any]],records:Sequence[Mapping[str,Any]])->dict[str,Any]:
    enriched=enrich_buckets(records);horizons=Counter(r.get("horizon_sessions") for r in enriched);observed={r.get("snapshot_id") for r in enriched};unobserved=[s for s in snapshots if s.get("snapshot_id") not in observed]
    keys=("action","opportunity_thesis","opportunity_bucket","decision_confidence_bucket","valuation_confidence_bucket","technical_quality_bucket","fundamental_quality_bucket")
    return {"version":VERSION,"customer_performance_enabled":False,"minimum_sample":MIN_SAMPLE,"total_snapshots":len(snapshots),"matured_records":len(enriched),"matured_snapshots":len(observed),"unobserved_snapshot_count":len(unobserved),"unobserved_tickers":sorted({str(s.get('ticker')) for s in unobserved}),"sample_size_by_horizon":{str(h):horizons.get(h,0) for h in (1,5,20,63,126,252)},"aggregations":{key:governed_aggregate(enriched,key) for key in keys},"target_stop":{"target_reached":sum(bool(r.get('target_reached')) for r in enriched),"stop_reached":sum(bool(r.get('stop_reached')) for r in enriched),"target_before_stop":sum(r.get('target_before_stop') is True for r in enriched),"entry_reached":sum(bool(r.get('entry_reached')) for r in enriched)},"missing_price_observations":sum(r.get('price_return') is None for r in enriched)+len(unobserved)}

def lifecycle(snapshots:Sequence[Mapping[str,Any]],records:Sequence[Mapping[str,Any]])->list[dict[str,Any]]:
    outcomes={r.get("snapshot_id"):r for r in sorted(records,key=lambda x:x.get("horizon_sessions") or 0)};groups={}
    for item in sorted(snapshots,key=lambda x:str(x.get("timestamp") or "")):groups.setdefault(item.get("ticker"),[]).append(item)
    result=[]
    order={"AVOID":0,"DATA_LIMITED":1,"WAIT_FOR_CONFIRMATION":2,"WAIT_FOR_BETTER_ENTRY":3,"ACCUMULATE":4,"BUY_NOW":5}
    for ticker,items in groups.items():
        initial=items[0];actions=[x.get("action") for x in items];changes=[]
        for before,after in zip(items,items[1:]):
            if before.get("action")!=after.get("action"):changes.append({"timestamp":after.get("timestamp"),"from":before.get("action"),"to":after.get("action"),"direction":"UPGRADE" if order.get(after.get("action"),-1)>order.get(before.get("action"),-1) else "DOWNGRADE"})
        related=[outcomes[x.get("snapshot_id")] for x in items if x.get("snapshot_id") in outcomes];latest=related[-1] if related else {}
        result.append({"ticker":ticker,"initial_snapshot_id":initial.get("snapshot_id"),"initial_action":initial.get("action"),"latest_action":items[-1].get("action"),"action_changes":changes,"thesis_invalidated":any(x.get("holding_period_outcome")=="STOP_REACHED" for x in related),"entry_reached":any(x.get("entry_reached") for x in related),"stop_reached":any(x.get("stop_reached") for x in related),"target_reached":any(x.get("target_reached") for x in related),"time_to_first_material_outcome":latest.get("time_to_first_material_outcome")})
    return result

def regression_alerts(report:Mapping[str,Any])->list[dict[str,Any]]:
    alerts=[];aggs=report.get("aggregations") or {}
    def published(key):return {x.get(key):x for x in aggs.get(key) or [] if x.get("publication_status")=="OBSERVATIONAL"}
    actions=published("action")
    if actions.get("BUY_NOW") and actions.get("ACCUMULATE") and actions["BUY_NOW"]["average_relative_return"] is not None and actions["ACCUMULATE"]["average_relative_return"] is not None and actions["BUY_NOW"]["average_relative_return"]+0.05<actions["ACCUMULATE"]["average_relative_return"]:alerts.append({"type":"BUY_NOW_UNDERPERFORMS_BUILD","action":"REVIEW_ONLY"})
    confidence=published("decision_confidence_bucket")
    if confidence.get("HIGH") and confidence.get("LOW") and confidence["HIGH"]["average_return"]<=confidence["LOW"]["average_return"]:alerts.append({"type":"CONFIDENCE_CALIBRATION_INVERSION","action":"REVIEW_ONLY"})
    for row in published("opportunity_thesis").values():
        if row.get("average_relative_return") is not None and row["average_relative_return"]<-.05:alerts.append({"type":"THESIS_PERSISTENT_UNDERPERFORMANCE","thesis":row.get("opportunity_thesis"),"action":"REVIEW_ONLY"})
    if any(r.get("worst_drawdown") is not None and r["worst_drawdown"]<-.30 for r in actions.values()):alerts.append({"type":"REALIZED_DRAWDOWN_EXCEEDS_EXPECTED_RISK","action":"REVIEW_ONLY"})
    return alerts

def read_jsonl(path:Path)->list[dict[str,Any]]:
    if not path.exists():return []
    out=[]
    for line in path.read_text().splitlines():
        try:out.append(json.loads(line))
        except Exception:continue
    return out

def append_outcomes(path:Path,records:Sequence[Mapping[str,Any]])->int:
    existing={(r.get("snapshot_id"),r.get("horizon_sessions")):r for r in read_jsonl(path)};fresh=[]
    for raw in records:
        row=dict(raw);key=(row.get("snapshot_id"),row.get("horizon_sessions"));prior=existing.get(key)
        if prior and prior!=row:raise ValueError("IMMUTABLE_OUTCOME_CONFLICT")
        if not prior:fresh.append(row);existing[key]=row
    if fresh:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("a",encoding="utf-8") as handle:
            for row in fresh:handle.write(json.dumps(row,sort_keys=True)+"\n")
    return len(fresh)

def mature_store(snapshots:Sequence[Mapping[str,Any]],bars_by_ticker:Mapping[str,Sequence[Mapping[str,Any]]],benchmark_bars:Sequence[Mapping[str,Any]]=())->list[dict[str,Any]]:
    return [record for snapshot in snapshots for record in mature_snapshot(snapshot,bars_by_ticker.get(str(snapshot.get("ticker")),()),benchmark_bars)]

__all__=["CUSTOMER_PERFORMANCE_ENABLED","MIN_SAMPLE","VERSION","append_outcomes","enrich_buckets","governed_aggregate","lifecycle","mature_store","read_jsonl","regression_alerts","score_bucket","validation_report"]
