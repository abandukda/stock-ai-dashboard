"""Build annual research series, completeness, and a no-execution quarterly manifest."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.g6_annual_financial_normalization import canonical_bytes
from services.g6_annual_financial_series import build_annual_series

def digest(x): return hashlib.sha256(canonical_bytes(x)).hexdigest()

def build(root: Path, output: Path) -> dict:
    paths=sorted(root.glob("*.annual.normalized.json"))
    if len(paths)!=11: raise ValueError(f"NORMALIZED_RESPONSE_COUNT_MISMATCH:{len(paths)}")
    output.mkdir(parents=True,exist_ok=True); series=[]
    for p in paths:
        item=build_annual_series(json.loads(p.read_text())); item["sha256"]=digest(item)
        (output/f'{item["ticker"]}.annual.series.json').write_bytes(canonical_bytes(item)+b"\n"); series.append(item)
    keys=("revenue","operating_income","operating_margin","operating_cash_flow","capital_expenditure","free_cash_flow","total_debt")
    coverage={}
    for item in series:
        counts={k:sum(p["metrics"][k]["status"]=="AVAILABLE" for p in item["periods"]) for k in keys}
        currencies=sorted({m["unit"].get("currency") for p in item["periods"] for m in p["metrics"].values()
                           if m.get("status")=="AVAILABLE" and isinstance(m.get("unit"),dict) and m["unit"].get("currency")})
        coverage[item["ticker"]]={"periods":len(item["periods"]), **counts,
                                  "missing_periods":{k:len(item["periods"])-v for k,v in counts.items()},
                                  "currencies":currencies,
                                  "restated_periods":sum(p["restatement_candidates"]>1 for p in item["periods"]),
                                  "mechanical_projections_available":sum(v["status"]=="AVAILABLE" for v in item["projections"].values())}
    report={"contract":"ATLAS_G6_ANNUAL_SERIES_COMPLETENESS_V1","ticker_count":11,"coverage":coverage,
            "ratings_changed":False,"publications_changed":False,"provider_calls":0}; report["sha256"]=digest(report)
    manifest={"contract":"ATLAS_G6_QUARTERLY_ACQUISITION_MANIFEST_V1","execution_authorized":False,"provider_calls":0,
              "requests":[{"ticker":x["ticker"],"endpoint":"/stock/financials-reported","parameters":{"symbol":x["ticker"],"freq":"quarterly"}} for x in series]}
    manifest["sha256"]=digest(manifest)
    (output/'completeness_report.json').write_bytes(canonical_bytes(report)+b"\n")
    (output/'quarterly_acquisition_manifest.json').write_bytes(canonical_bytes(manifest)+b"\n")
    return {"report":report,"manifest":manifest}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--normalized-root',type=Path,required=True); ap.add_argument('--output-root',type=Path,required=True); a=ap.parse_args()
    result=build(a.normalized_root,a.output_root); print(json.dumps(result,indent=2,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
