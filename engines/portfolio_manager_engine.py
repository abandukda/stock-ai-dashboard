"""
Atlas V101.2 — Institutional Portfolio Manager
Read-only portfolio construction with confidence calibration, smart money,
government/policy support, policymaker disclosures, freshness, concentration
controls, and cash optimization.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any, Iterable, Mapping
import math

@dataclass(frozen=True)
class PortfolioConfig:
    max_positions: int = 10
    max_position_pct: float = 12.0
    starter_position_pct: float = 4.0
    min_cash_pct: float = 10.0
    max_cash_pct: float = 40.0
    max_sector_pct: float = 30.0
    max_industry_pct: float = 18.0
    minimum_candidate_score: float = 55.0
    minimum_confidence_pct: float = 45.0
    freshness_warning_days: int = 14
    freshness_penalty_days: int = 30

def _num(v: Any, d=None):
    try:
        if v is None: return d
        x=float(v)
        return x if math.isfinite(x) else d
    except Exception:
        return d

def _text(v: Any, d=""):
    if v is None: return d
    s=str(v).strip()
    return s or d

def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))

def _first(row: Mapping[str,Any], *keys, default=None):
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k)
    return default

def _signal_score(row, direct_keys, text_keys):
    direct=_num(_first(row,*direct_keys))
    if direct is not None:
        return _clamp(direct)
    text=" ".join(_text(_first(row,k),"") for k in text_keys).lower()
    if not text.strip(): return None
    if any(w in text for w in ("strong","positive","buying","accumulation","support","tailwind","approved","awarded")):
        return 80.0
    if any(w in text for w in ("negative","selling","distribution","headwind","investigation","restriction","risk")):
        return 30.0
    return 55.0

def _freshness_days(row, key):
    return _num(_first(row,f"{key}_freshness_days",f"{key}_age_days",f"{key.title()} Freshness Days"))

def _freshness_factor(days, config):
    if days is None: return 0.90
    if days <= config.freshness_warning_days: return 1.00
    if days <= config.freshness_penalty_days: return 0.85
    return 0.65

def calibrate_confidence(row: Mapping[str,Any], *, config: PortfolioConfig|None=None):
    config=config or PortfolioConfig()
    opportunity=_clamp(_num(_first(row,"opportunity_score","Opportunity Score"),0) or 0)
    completeness=_clamp(_num(_first(row,"research_completeness_pct","Research Completeness","component_coverage_pct"),50) or 50)
    pillar_pct=_num(_first(row,"required_pillars_passed_pct","pillar_pass_pct"))
    if pillar_pct is None:
        passed=_num(_first(row,"required_pillars_passed"))
        total=_num(_first(row,"required_pillars_total"))
        pillar_pct=passed/total*100 if passed is not None and total else 50
    pillar_pct=_clamp(pillar_pct)
    technical=_clamp(_num(_first(row,"technical_score","Technical Score"),50) or 50)
    fundamentals=_clamp(_num(_first(row,"quality_score","Quality","financial_health_score","Financial Health"),50) or 50)
    smart=_signal_score(row,("smart_money_score","institutional_score","Smart Money Score"),("institutional_activity","institutional_summary","smart_money"))
    policy=_signal_score(row,("government_policy_score","policy_support_score","political_score","Government Policy Score"),("government_contracts","policy_context","political_support","government_policy_summary"))
    policymaker=_signal_score(row,("policymaker_disclosure_score","congressional_trading_score","Political Buying Score"),("policymaker_disclosure_summary","congressional_trading_summary","political_buying_summary"))
    smart=50.0 if smart is None else smart
    policy=50.0 if policy is None else policy
    policymaker=50.0 if policymaker is None else policymaker
    freshness={
        "fundamentals":_freshness_days(row,"fundamentals"),
        "institutional":_freshness_days(row,"institutional"),
        "government_policy":_freshness_days(row,"government_policy"),
        "policymaker_disclosure":_freshness_days(row,"policymaker_disclosure"),
        "news":_freshness_days(row,"news"),
    }
    fresh_factor=sum(_freshness_factor(v,config) for v in freshness.values())/len(freshness)
    base=(opportunity*.20+completeness*.20+pillar_pct*.20+technical*.12+
          fundamentals*.12+smart*.08+policy*.05+policymaker*.03)
    penalties=[]
    for condition, reason, points in [
        (completeness<60,"Research completeness below 60%",8),
        (technical<45,"Weak technical confirmation",7),
        (pillar_pct<60,"Too few required pillars passed",8),
        (policy<40,"Adverse government or policy environment",5),
        (smart<40,"Weak institutional support",5),
    ]:
        if condition: penalties.append({"reason":reason,"points":float(points)})
    confidence=_clamp(base*fresh_factor-sum(p["points"] for p in penalties),0,98)
    band=("Exceptional" if confidence>=92 else "High" if confidence>=85 else
          "Strong" if confidence>=75 else "Moderate" if confidence>=65 else
          "Limited" if confidence>=55 else "Low")
    return {
        "confidence_pct":round(confidence,1),
        "confidence_band":band,
        "freshness_factor":round(fresh_factor,3),
        "penalties":penalties,
        "inputs":{
            "opportunity":opportunity,
            "research_completeness":completeness,
            "required_pillars_passed_pct":pillar_pct,
            "technical":technical,
            "fundamentals":fundamentals,
            "smart_money":smart,
            "government_policy":policy,
            "policymaker_disclosure":policymaker,
        },
        "freshness_days":freshness,
    }

def _strength(row, confidence):
    opportunity=_num(_first(row,"opportunity_score","Opportunity Score"),0) or 0
    expected=_num(_first(row,"expected_return_pct","Target Upside %"),0) or 0
    return _clamp(opportunity*.60+confidence*.30+_clamp(50+expected)*.10)

def build_portfolio_plan(candidates: Iterable[Mapping[str,Any]], config: PortfolioConfig|None=None):
    config=config or PortfolioConfig()
    rows=[]
    for raw in candidates:
        row=dict(raw)
        conf=calibrate_confidence(row,config=config)
        row["_confidence"]=conf
        row["_strength"]=_strength(row,conf["confidence_pct"])
        rows.append(row)
    eligible=[r for r in rows if (_num(_first(r,"opportunity_score","Opportunity Score"),0) or 0)>=config.minimum_candidate_score and r["_confidence"]["confidence_pct"]>=config.minimum_confidence_pct]
    eligible.sort(key=lambda r:(r["_strength"],r["_confidence"]["confidence_pct"]),reverse=True)
    eligible=eligible[:config.max_positions]
    if not eligible:
        return {"version":"V101.2","read_only":True,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"config":asdict(config),"portfolio_quality_score":0.0,"recommended_cash_pct":100.0,"allocations":[],"sector_exposure":{},"industry_exposure":{},"warnings":["No candidates met portfolio eligibility thresholds."]}
    avg_conf=sum(r["_confidence"]["confidence_pct"] for r in eligible)/len(eligible)
    elite=sum(1 for r in eligible if (_num(_first(r,"opportunity_score","Opportunity Score"),0) or 0)>=90 and r["_confidence"]["confidence_pct"]>=80)
    target_cash=max(config.min_cash_pct,min(config.max_cash_pct,config.max_cash_pct-elite*4-max(0,avg_conf-70)*.35))
    investable=100-target_cash
    total_strength=sum(r["_strength"] for r in eligible) or 1
    allocations=[]
    sector_totals=defaultdict(float)
    industry_totals=defaultdict(float)
    deferred=[]
    for r in eligible:
        ticker=_text(_first(r,"ticker","Ticker"),"UNKNOWN").upper()
        sector=_text(_first(r,"sector","Sector"),"Unknown")
        industry=_text(_first(r,"industry","Industry"),sector)
        raw_alloc=r["_strength"]/total_strength*investable
        alloc=max(config.starter_position_pct,min(config.max_position_pct,raw_alloc))
        alloc=min(alloc,max(0,config.max_sector_pct-sector_totals[sector]),max(0,config.max_industry_pct-industry_totals[industry]))
        if alloc<=0:
            deferred.append({"ticker":ticker,"reason":"Sector or industry concentration limit reached."})
            continue
        alloc=round(alloc,1)
        conf=r["_confidence"]
        reasons=[f"Opportunity score: {_num(_first(r,'opportunity_score','Opportunity Score'),0):.1f}",f"Calibrated confidence: {conf['confidence_pct']:.1f}%"]
        if conf["inputs"]["smart_money"]>=70: reasons.append("Strong institutional / smart-money support.")
        if conf["inputs"]["government_policy"]>=70: reasons.append("Favorable government and policy support.")
        if conf["inputs"]["policymaker_disclosure"]>=70: reasons.append("Positive disclosed policymaker activity used as a low-weight support signal.")
        allocations.append({
            "ticker":ticker,"sector":sector,"industry":industry,
            "opportunity_score":_num(_first(r,"opportunity_score","Opportunity Score"),0),
            "confidence_pct":conf["confidence_pct"],"confidence_band":conf["confidence_band"],
            "recommended_allocation_pct":alloc,
            "starter_position_pct":config.starter_position_pct,
            "maximum_position_pct":config.max_position_pct,
            "portfolio_strength":round(r["_strength"],1),
            "smart_money_score":conf["inputs"]["smart_money"],
            "government_policy_score":conf["inputs"]["government_policy"],
            "policymaker_disclosure_score":conf["inputs"]["policymaker_disclosure"],
            "freshness_factor":conf["freshness_factor"],
            "confidence_penalties":conf["penalties"],
            "reasons":reasons,
        })
        sector_totals[sector]+=alloc
        industry_totals[industry]+=alloc
    invested=round(sum(a["recommended_allocation_pct"] for a in allocations),1)
    cash=round(100-invested,1)
    quality=(sum(a["portfolio_strength"]*a["recommended_allocation_pct"] for a in allocations)/invested if invested else 0)
    warnings=[]
    for s,e in sector_totals.items():
        if e>=config.max_sector_pct: warnings.append(f"{s} exposure reached the {config.max_sector_pct:.0f}% limit.")
    for i,e in industry_totals.items():
        if e>=config.max_industry_pct: warnings.append(f"{i} exposure reached the {config.max_industry_pct:.0f}% limit.")
    if deferred: warnings.append(f"{len(deferred)} candidate(s) were deferred by concentration controls.")
    return {
        "version":"V101.2","read_only":True,"generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "config":asdict(config),"portfolio_quality_score":round(quality,1),
        "recommended_cash_pct":cash,"average_confidence_pct":round(avg_conf,1),
        "allocations":allocations,
        "sector_exposure":{k:round(v,1) for k,v in sector_totals.items()},
        "industry_exposure":{k:round(v,1) for k,v in industry_totals.items()},
        "deferred_candidates":deferred,"warnings":warnings,
    }

def validate_portfolio_contract(model: Mapping[str,Any]):
    errs=[]
    if model.get("read_only") is not True: errs.append("Portfolio model must remain read-only.")
    allocs=model.get("allocations") or []
    cash=_num(model.get("recommended_cash_pct"),0) or 0
    total=round(sum(_num(a.get("recommended_allocation_pct"),0) or 0 for a in allocs)+cash,1)
    if abs(total-100)>0.2: errs.append("Allocation total does not equal 100%.")
    for a in allocs:
        c=_num(a.get("confidence_pct"))
        if c is None or not 0<=c<=98: errs.append(f"{a.get('ticker','UNKNOWN')} has invalid confidence.")
    return errs

__all__=["PortfolioConfig","calibrate_confidence","build_portfolio_plan","validate_portfolio_contract"]
