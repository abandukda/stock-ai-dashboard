from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.g6_quarterly_dispatch_validation import canonical_bytes,validate_dispatch

def main():
    p=argparse.ArgumentParser();p.add_argument('--approval',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=validate_dispatch(json.loads(a.approval.read_text()),json.loads(a.manifest.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_bytes(result)+b"\n");print(json.dumps(result,indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
