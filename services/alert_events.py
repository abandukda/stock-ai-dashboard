"""Deterministic alert event foundation; delivery is intentionally out of scope."""
from __future__ import annotations
from typing import Any,Mapping
EVENT_TYPES=("BUY_NOW_NEW","BUILD_NEW","ACTION_UPGRADE","ACTION_DOWNGRADE","HIGH_VOLUME","BREAKOUT_CONFIRMED","VALUATION_CHANGE_MATERIAL","ESTIMATE_REVISION_MATERIAL")
def event(event_type:str,ticker:str,as_of:str,evidence:Mapping[str,Any]) -> dict[str,Any]:
    if event_type not in EVENT_TYPES: raise ValueError("UNREGISTERED_ALERT_EVENT")
    return {"version":"ATLAS_ALERT_EVENT_V1","event_type":event_type,"ticker":ticker,"as_of":as_of,"evidence":dict(evidence),"delivery_status":"NOT_SENT"}
__all__=["EVENT_TYPES","event"]
