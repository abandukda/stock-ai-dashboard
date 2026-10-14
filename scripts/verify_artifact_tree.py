#!/usr/bin/env python3
"""Verify a deterministic SHA-256 over a downloaded artifact tree."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from services.operations_gateway import canonical_bytes

def tree_identity(root: Path) -> dict:
    root=root.resolve(); rows=[]
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append({"path":path.relative_to(root).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size})
    if not rows: raise ValueError("ARTIFACT_TREE_EMPTY")
    return {"files":rows,"tree_sha256":hashlib.sha256(canonical_bytes(rows)).hexdigest()}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--expected-sha256",required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); result=tree_identity(a.root)
    if result["tree_sha256"]!=a.expected_sha256: raise PermissionError("ARTIFACT_TREE_SHA256_MISMATCH")
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
if __name__=="__main__": main()
