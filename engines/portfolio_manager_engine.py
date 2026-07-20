"""
Atlas V101 — AI Portfolio Manager Engine

Read-only portfolio construction engine.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Mapping, Iterable
import math

@dataclass(frozen=True)
class PortfolioConfig:
    max_position_pct: float = 12.0
    starter_position_pct: float = 4.0
    target_tech_exposure_pct: float = 30.0
    min_cash_pct: float = 10.0

def _num(v, d=None):
    try:
        if v is None: return d
        x=float(v)
        return x if math.isfinite(x) else d
    except Exception:
        return d

def build_portfolio_plan(candidates: Iterable[Mapping[str,Any]], config: PortfolioConfig|None=None):
    config=config or PortfolioConfig()
    rows=[dict(r) for r in candidates]
    rows.sort(key=lambda r:_num(r.get("opportunity_score"),0), reverse=True)
    total=sum(max(_num(r.get("opportunity_score"),0),0) for r in rows[:10]) or 1
    allocations=[]
    invested=0.0
    for r in rows[:10]:
        score=max(_num(r.get("opportunity_score"),0),0)
        raw=score/total*100
        alloc=max(config.starter_position_pct,min(config.max_position_pct,raw))
        invested+=alloc
        allocations.append({
            "ticker":r.get("ticker") or r.get("Ticker"),
            "opportunity_score":score,
            "recommended_allocation_pct":round(alloc,1),
            "starter_position_pct":config.starter_position_pct,
            "maximum_position_pct":config.max_position_pct,
            "reason":"Higher opportunity score and portfolio diversification."
        })
    cash=max(config.min_cash_pct, round(100-invested,1))
    scale=(100-cash)/invested if invested>0 else 0
    invested=0
    for a in allocations:
        a["recommended_allocation_pct"]=round(a["recommended_allocation_pct"]*scale,1)
        invested+=a["recommended_allocation_pct"]
    cash=round(100-invested,1)
    return {
      "version":"V101",
      "read_only":True,
      "config":asdict(config),
      "portfolio_quality_score": round(sum(a["recommended_allocation_pct"] for a in allocations),1),
      "recommended_cash_pct":cash,
      "allocations":allocations
    }

def validate_portfolio_contract(model):
    errs=[]
    if model.get("read_only") is not True: errs.append("not read only")
    s=round(sum(a["recommended_allocation_pct"] for a in model["allocations"])+model["recommended_cash_pct"],1)
    if abs(s-100)>0.2: errs.append("allocation total !=100")
    return errs
