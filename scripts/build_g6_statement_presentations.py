"""Build presentation artifacts and immutable, inert acquisition manifests."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.g6_annual_financial_normalization import canonical_bytes
from services.g6_annual_statement_presentation import build_statement_presentation

def digest(x): return hashlib.sha256(canonical_bytes(x)).hexdigest()
def batches(symbols,size): return [symbols[i:i+size] for i in range(0,len(symbols),size)]

def build(normalized_root:Path,series_root:Path,population_path:Path,output:Path,batch_size:int=25):
    if batch_size<1 or batch_size>50: raise ValueError("BATCH_SIZE_OUT_OF_BOUNDS")
    normalized=sorted(normalized_root.glob("*.annual.normalized.json"));
    if len(normalized)!=11: raise ValueError("PILOT_COUNT_MISMATCH")
    output.mkdir(parents=True,exist_ok=True); tickers=[]
    for p in normalized:
        n=json.loads(p.read_text()); sp=series_root/f'{n["ticker"]}.annual.series.json'
        if not sp.is_file(): raise ValueError(f'SERIES_MISSING:{n["ticker"]}')
        view=build_statement_presentation(n,json.loads(sp.read_text())); view["sha256"]=digest(view)
        (output/f'{n["ticker"]}.annual.presentation.json').write_bytes(canonical_bytes(view)+b"\n");tickers.append(n["ticker"])
    quarterly={"contract":"ATLAS_G6_QUARTERLY_IMMUTABLE_BATCHES_V1","execution_authorized":False,"provider_calls":0,
               "endpoint":"/stock/financials-reported","frequency":"quarterly","batch_size":batch_size,
               "batches":[{"batch_id":i+1,"symbols":x} for i,x in enumerate(batches(sorted(tickers),batch_size))]}
    quarterly["sha256"]=digest(quarterly)
    pop=json.loads(population_path.read_text()); symbols=sorted({str(x).upper() for x in pop.get("symbols",[]) if x})
    if pop.get("count")!=len(symbols) or len(symbols)!=6033: raise ValueError("PUBLISHED_POPULATION_CONTRACT_MISMATCH")
    remaining=[x for x in symbols if x not in set(tickers)]
    expansion={"contract":"ATLAS_G6_PUBLISHED_POPULATION_EXPANSION_MANIFEST_V1","execution_authorized":False,"provider_calls":0,
               "source_population":{"count":6033,"universe_sha256":pop.get("universe_sha256"),"source_sha":pop.get("source_sha"),
                                    "candidate_digest":pop.get("candidate_digest")},
               "pilot_symbols":sorted(tickers),"remaining_symbol_count":len(remaining),"endpoint":"/stock/financials-reported",
               "frequency":"annual","batch_size":batch_size,"batches":[{"batch_id":i+1,"symbols":x} for i,x in enumerate(batches(remaining,batch_size))]}
    expansion["sha256"]=digest(expansion)
    (output/'quarterly_immutable_batches.json').write_bytes(canonical_bytes(quarterly)+b"\n")
    (output/'published_population_expansion_manifest.json').write_bytes(canonical_bytes(expansion)+b"\n")
    return {"presentations":len(tickers),"quarterly":quarterly,"expansion":expansion}

def main():
    p=argparse.ArgumentParser();p.add_argument('--normalized-root',type=Path,required=True);p.add_argument('--series-root',type=Path,required=True);p.add_argument('--population',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--batch-size',type=int,default=25);a=p.parse_args()
    print(json.dumps(build(a.normalized_root,a.series_root,a.population,a.output_root,a.batch_size),indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
