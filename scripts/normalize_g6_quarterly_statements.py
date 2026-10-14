from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.g6_annual_financial_normalization import canonical_bytes
from services.g6_quarterly_financial_normalization import EXPECTED_TICKERS,build_quarterly_series,normalize_files,validate_run_summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args()
    summary=json.loads((a.run_root/'run_summary.json').read_text());validate_run_summary(summary);a.output_root.mkdir(parents=True,exist_ok=True)
    results=[]
    for ordinal,ticker in enumerate(EXPECTED_TICKERS,1):
        stem=f'{ordinal:02d}-{ticker}-financials-reported';raw=a.run_root/'raw'/f'{stem}.json';meta=a.run_root/'raw'/f'{stem}.metadata.json'
        normalized=normalize_files(raw,meta);series=build_quarterly_series(normalized)
        (a.output_root/f'{ticker}.quarterly.normalized.json').write_bytes(canonical_bytes(normalized)+b'\n')
        (a.output_root/f'{ticker}.quarterly.series.json').write_bytes(canonical_bytes(series)+b'\n')
        results.append({'ticker':ticker,'filings':normalized['coverage']['filing_count'],'source_facts':normalized['coverage']['source_fact_count'],
                        'available_facts':normalized['coverage']['available_fact_count'],'unavailable_facts':normalized['coverage']['unavailable_fact_count'],
                        'selected_periods':len(series['periods']),'restatement_candidates':sum(p['restatement_candidates']-1 for p in series['periods']),
                        'discrete_available':sum(f['status']=='AVAILABLE' for p in series['periods'] for f in p['discrete_flow_facts']),
                        'discrete_unavailable':sum(f['status']=='UNAVAILABLE' for p in series['periods'] for f in p['discrete_flow_facts']),
                        'discrete_ambiguous':sum(f['status']=='AMBIGUOUS' for p in series['periods'] for f in p['discrete_flow_facts']),
                        'normalized_sha256':normalized['normalized_sha256'],'series_sha256':series['sha256']})
    output={'contract':'ATLAS_G6_QUARTERLY_NORMALIZATION_SUMMARY_V1','source_run_id':'38574271684','records':results,
            'totals':{key:sum(x[key] for x in results) for key in ('filings','source_facts','available_facts','unavailable_facts','selected_periods','restatement_candidates','discrete_available','discrete_unavailable','discrete_ambiguous')},
            'provider_calls_during_normalization':0,'ratings_changed':False,'publications_changed':False}
    (a.output_root/'quarterly_normalization_summary.json').write_bytes(canonical_bytes(output)+b'\n');print(json.dumps(output,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
