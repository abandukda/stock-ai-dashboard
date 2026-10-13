"""Pure, provider-free G2/G3/G4 preflight contracts."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib, json
from typing import Any, Mapping

VERSION="ATLAS_REPORT_CARD_AUTOMATION_GATES_V1"
TOKENS={"G2":"REPORT_CARD_ACQUIRE_ONCE","G3":"REPORT_CARD_APPEND_ONCE","G4":"REPORT_CARD_AUTOMATION_OPERATE"}
CONCURRENCY_GROUP="atlas-report-card-daily-ledger-mutation"

@dataclass(frozen=True)
class GateDecision:
    gate: str
    allowed: bool
    reason: str
    evidence_sha256: str

def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def validate_shared_gateway(contract: Mapping[str,Any]) -> dict[str,Any]:
    """Accept batch gateway artifacts without coupling Report Card to a vendor client."""
    required={"historical_ohlcv","splits","dividends"}
    valid=(contract.get("interface_version")=="ATLAS_PROVIDER_GATEWAY_V1"
           and contract.get("mode")=="BATCH_EOD"
           and contract.get("provider_neutral") is True
           and contract.get("single_owner") is True
           and required <= set(contract.get("capabilities") or ()))
    if not valid:
        raise ValueError("SHARED_GATEWAY_CONTRACT_INCOMPATIBLE")
    return {"status":"COMPATIBLE","contract_sha256":_digest(contract),"capabilities":sorted(required)}

def decide_gate(*, gate: str, authorization: str, evidence: Mapping[str,Any]) -> GateDecision:
    if gate not in TOKENS or authorization != TOKENS.get(gate):
        return GateDecision(gate,False,"AUTHORIZATION_INVALID",_digest(evidence))
    common=(evidence.get("environment")=="atlas-internal-report-card"
            and evidence.get("kill_switch_checked") is True
            and evidence.get("alert_destination_healthy") is True)
    if not common:
        return GateDecision(gate,False,"COMMON_PREFLIGHT_INCOMPLETE",_digest(evidence))
    if gate=="G2":
        required=(evidence.get("plan_hash_verified") is True
                  and evidence.get("entitlement_verified") is True
                  and evidence.get("gateway_compatible") is True
                  and evidence.get("ledger_read_only") is True)
        reason="G2_PREFLIGHT_PASS" if required else "G2_EVIDENCE_INCOMPLETE"
    elif gate=="G3":
        required=(evidence.get("provider_calls")==0 and evidence.get("bundle_hash_verified") is True
                  and evidence.get("disposable_append_pass") is True
                  and evidence.get("backup_restore_pass") is True
                  and evidence.get("single_writer") is True)
        reason="G3_PREFLIGHT_PASS" if required else "G3_EVIDENCE_INCOMPLETE"
    else:
        required=(evidence.get("concurrency_group")==CONCURRENCY_GROUP
                  and evidence.get("cancel_in_progress") is False
                  and evidence.get("independent_dead_man_pass") is True
                  and evidence.get("second_cycle_pass") is True
                  and evidence.get("scheduler_enabled") is False)
        reason="G4_REVIEW_READY_INERT" if required else "G4_EVIDENCE_INCOMPLETE"
    return GateDecision(gate,bool(required),reason,_digest(evidence))

def decision_artifact(decision: GateDecision) -> dict[str,Any]:
    result={"version":VERSION,**asdict(decision),"provider_calls":0,"ledger_mutations":0,
            "schedule_activated":False}
    result["artifact_sha256"]=_digest(result)
    return result

__all__=["CONCURRENCY_GROUP","GateDecision","TOKENS","decide_gate","decision_artifact","validate_shared_gateway"]
