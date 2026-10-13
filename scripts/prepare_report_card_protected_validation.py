#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from services.report_card_protected_readonly import prepare_protected_validation

def mount(path: Path):
    values=subprocess.check_output(["findmnt","-T",str(path),"-n","-o","UUID,SOURCE,FSTYPE,TARGET"],text=True).strip().split(maxsplit=3)
    if len(values)!=4: raise RuntimeError("MOUNT_METADATA_INCOMPLETE")
    return dict(zip(("uuid","source","fstype","target"),values), device=path.stat().st_dev)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,required=True); p.add_argument("--backup-root",type=Path,required=True)
    p.add_argument("--calendar",type=Path,required=True); p.add_argument("--publication-evidence",type=Path)
    p.add_argument("--source-sha",required=True); p.add_argument("--output",type=Path,required=True)
    p.add_argument("--kill-switch",type=Path,required=True)
    a=p.parse_args(); evidence=[] if not a.publication_evidence else json.loads(a.publication_evidence.read_text())
    result=prepare_protected_validation(ledger_path=a.ledger,backup_root=a.backup_root,
        calendar=json.loads(a.calendar.read_text()),source_sha=a.source_sha,publication_rows=evidence,
        workspace=Path(os.environ["GITHUB_WORKSPACE"]) if os.environ.get("GITHUB_WORKSPACE") else ROOT,
        mount_probe=mount,kill_switch_path=a.kill_switch)
    a.output.parent.mkdir(parents=True,exist_ok=True); pending=a.output.with_suffix(a.output.suffix+".pending")
    pending.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); os.replace(pending,a.output); return 0
if __name__=="__main__": raise SystemExit(main())
