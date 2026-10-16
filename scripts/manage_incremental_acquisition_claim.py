#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from services.incremental_acquisition_claim import consume_claim, finalize_claim, scope_payload

def main() -> int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="action",required=True)
    c=sub.add_parser("consume")
    for name in ("claim-id","source-sha","plan-sha256","session","claim-scope-sha256","authorization-token"):
        c.add_argument(f"--{name}",required=True)
    c.add_argument("--claims-root",type=Path,required=True)
    f=sub.add_parser("finalize"); f.add_argument("--claim-file",type=Path,required=True); f.add_argument("--outcome",required=True)
    a=p.parse_args()
    if a.action=="finalize": finalize_claim(a.claim_file,outcome=a.outcome); return 0
    scope=scope_payload(claim_id=a.claim_id,source_sha=a.source_sha,plan_sha256=a.plan_sha256,session=a.session)
    if scope["claim_scope_sha256"] != a.claim_scope_sha256: raise PermissionError("INCREMENTAL_CLAIM_SCOPE_DIGEST_INVALID")
    path=consume_claim(claims_root=a.claims_root,scope=scope,token=a.authorization_token)
    print(json.dumps({"status":"CLAIM_CONSUMED","claim_file":str(path),**scope},sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
