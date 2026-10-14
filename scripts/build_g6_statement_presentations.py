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
    output.mkdir(parents=True,exist_ok=True); tickers=[]; readiness_records=[]
    for p in normalized:
        n=json.loads(p.read_text()); sp=series_root/f'{n["ticker"]}.annual.series.json'
        if not sp.is_file(): raise ValueError(f'SERIES_MISSING:{n["ticker"]}')
        view=build_statement_presentation(n,json.loads(sp.read_text())); view["sha256"]=digest(view)
        (output/f'{n["ticker"]}.annual.presentation.json').write_bytes(canonical_bytes(view)+b"\n");tickers.append(n["ticker"])
        rows=sum(len(x) for x in view["statements"].values()); statuses={"AVAILABLE":0,"UNAVAILABLE":0,"AMBIGUOUS":0}
        for statement_rows in view["statements"].values():
            for row in statement_rows:
                for cell in row["cells"]: statuses[cell["status"]]+=1
        readiness_records.append({"ticker":n["ticker"],"period_count":len(view["periods"]),"statement_row_count":rows,
                                  "cell_status":statuses,"presentation_sha256":view["sha256"]})
    quarterly={"contract":"ATLAS_G6_QUARTERLY_IMMUTABLE_BATCHES_V1","execution_authorized":False,"provider_calls":0,
               "endpoint":"/stock/financials-reported","frequency":"quarterly","batch_size":batch_size,
               "batches":[{"batch_id":i+1,"symbols":x} for i,x in enumerate(batches(sorted(tickers),batch_size))]}
    quarterly["sha256"]=digest(quarterly)
    approval={"contract":"ATLAS_G6_QUARTERLY_ACQUISITION_APPROVAL_PACKAGE_V1",
              "status":"AWAITING_EXPLICIT_EXECUTION_AUTHORIZATION","execution_authorized":False,
              "request_manifest_sha256":quarterly["sha256"],"request_count":len(tickers),
              "request_contract":{"method":"GET","endpoint":"/stock/financials-reported",
                                  "parameters":{"symbol":"<EXACT_MANIFEST_SYMBOL>","freq":"quarterly"},
                                  "symbol_order":sorted(tickers)},
              "rate_contract":{"scope":"SINGLE_GLOBAL_ACCOUNT_LEVEL_LIMITER","requests_per_minute":500,
                               "burst_requests_per_second_ceiling":20,"workers":1,
                               "original_request_ceiling":len(tickers),"automatic_retry_ceiling_per_request":0,
                               "absolute_provider_attempt_ceiling":len(tickers),"retry_policy":"NO_AUTOMATIC_RETRIES"},
              "stop_conditions":["HTTP_429","AUTHENTICATION_ERROR","DETERMINISTIC_4XX","UNAPPROVED_5XX",
                                 "CONNECT_OR_READ_TIMEOUT","CONNECTION_RESET","SCHEMA_OR_CONTRACT_ERROR","MALFORMED_RESPONSE",
                                 "RATE_BUDGET_VIOLATION","DUPLICATE_OR_UNEXPECTED_SYMBOL","RAW_DIGEST_FAILURE"],
              "lineage_storage":{"raw":"raw/{ordinal:02d}-{ticker}-financials-reported.json",
                                 "metadata":"raw/{ordinal:02d}-{ticker}-financials-reported.metadata.json",
                                 "run_summary":"run_summary.json","required_metadata":["endpoint","parameters","ticker",
                                 "status_code","response_headers","raw_bytes","raw_sha256","requested_at","completed_at",
                                 "latency_ms","attempt_count","retry_count"]},
              "normalization_next_contract":"ATLAS_G6_ANNUAL_STATEMENT_NORMALIZATION_V1_REQUIRES_QUARTERLY_EXTENSION",
              "provider_calls_during_package_build":0}
    approval["sha256"]=digest(approval)
    pop=json.loads(population_path.read_text()); symbols=sorted({str(x).upper() for x in pop.get("symbols",[]) if x})
    if pop.get("count")!=len(symbols) or len(symbols)!=6033: raise ValueError("PUBLISHED_POPULATION_CONTRACT_MISMATCH")
    remaining=[x for x in symbols if x not in set(tickers)]
    expansion={"contract":"ATLAS_G6_FULL_UNIVERSE_EXPANSION_MANIFEST_V1","population_classification":"GOVERNED_FULL_UNIVERSE_NOT_CUSTOMER_PUBLISHED",
               "execution_authorized":False,"provider_calls":0,
               "source_population":{"count":6033,"universe_sha256":pop.get("universe_sha256"),"source_sha":pop.get("source_sha"),
                                    "candidate_digest":pop.get("candidate_digest")},
               "pilot_symbols":sorted(tickers),"remaining_symbol_count":len(remaining),"endpoint":"/stock/financials-reported",
               "frequency":"annual","batch_size":batch_size,"batches":[{"batch_id":i+1,"symbols":x} for i,x in enumerate(batches(remaining,batch_size))]}
    expansion["sha256"]=digest(expansion)
    published_blocked={"contract":"ATLAS_G6_PUBLISHED_POPULATION_EXPANSION_BLOCK_V1",
                       "status":"BLOCKED_AUTHORITATIVE_PUBLISHED_SYMBOL_IDENTITY_REQUIRED",
                       "known_expected_count":1298,"symbols":None,"batches":[],"execution_authorized":False,"provider_calls":0,
                       "reason":"LOCAL_PUBLICATION_MANIFEST_HAS_COUNT_ONLY_NO_IMMUTABLE_SYMBOL_MEMBERSHIP"}
    published_blocked["sha256"]=digest(published_blocked)
    readiness={"contract":"ATLAS_G6_CUSTOMER_STATEMENT_READINESS_V1","status":"ANNUAL_PRESENTATION_CONTRACT_READY_UI_INTEGRATION_PENDING",
               "pilot_count":len(tickers),"records":readiness_records,"quarterly_evidence_status":"NOT_ACQUIRED",
               "quarterly_approval_sha256":approval["sha256"],"field_specific_unavailable_states":True,
               "ratings_changed":False,"publications_changed":False,"provider_calls":0}
    readiness["sha256"]=digest(readiness)
    (output/'quarterly_immutable_batches.json').write_bytes(canonical_bytes(quarterly)+b"\n")
    (output/'quarterly_acquisition_approval_package.json').write_bytes(canonical_bytes(approval)+b"\n")
    (output/'full_universe_expansion_manifest.json').write_bytes(canonical_bytes(expansion)+b"\n")
    (output/'published_population_expansion_blocked.json').write_bytes(canonical_bytes(published_blocked)+b"\n")
    (output/'customer_statement_readiness.json').write_bytes(canonical_bytes(readiness)+b"\n")
    return {"presentations":len(tickers),"quarterly":quarterly,"quarterly_approval":approval,"full_universe_expansion":expansion,
            "published_population_expansion":published_blocked,"customer_statement_readiness":readiness}

def main():
    p=argparse.ArgumentParser();p.add_argument('--normalized-root',type=Path,required=True);p.add_argument('--series-root',type=Path,required=True);p.add_argument('--population',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--batch-size',type=int,default=25);a=p.parse_args()
    print(json.dumps(build(a.normalized_root,a.series_root,a.population,a.output_root,a.batch_size),indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
