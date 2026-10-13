#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from services.report_card_automation_gates import decide_gate,decision_artifact,validate_shared_gateway

def main():
    p=argparse.ArgumentParser(); p.add_argument("--gate",choices=("G2","G3","G4"),required=True)
    p.add_argument("--authorization",required=True); p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--gateway-contract",type=Path); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); evidence=json.loads(a.evidence.read_text())
    if a.gate=="G2":
        if not a.gateway_contract: raise ValueError("G2_GATEWAY_CONTRACT_REQUIRED")
        evidence["gateway_compatible"]=validate_shared_gateway(json.loads(a.gateway_contract.read_text()))["status"]=="COMPATIBLE"
    result=decision_artifact(decide_gate(gate=a.gate,authorization=a.authorization,evidence=evidence))
    a.output.parent.mkdir(parents=True,exist_ok=True); pending=a.output.with_suffix(a.output.suffix+".pending")
    pending.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); os.replace(pending,a.output)
    return 0 if result["allowed"] else 2
if __name__=="__main__": raise SystemExit(main())
