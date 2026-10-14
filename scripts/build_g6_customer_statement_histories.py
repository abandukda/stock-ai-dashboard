from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.customer_statement_history_projection import project_customer_statement_history
from services.g6_annual_financial_normalization import canonical_bytes
from services.g6_quarterly_financial_normalization import EXPECTED_TICKERS

def main():
    p=argparse.ArgumentParser();p.add_argument('--annual-root',type=Path,required=True);p.add_argument('--quarterly-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();a.output_root.mkdir(parents=True,exist_ok=True)
    records=[]
    for ticker in EXPECTED_TICKERS:
        annual=json.loads((a.annual_root/f'{ticker}.annual.presentation.json').read_text())
        quarterly=json.loads((a.quarterly_root/f'{ticker}.quarterly.normalized.json').read_text())
        series=json.loads((a.quarterly_root/f'{ticker}.quarterly.series.json').read_text())
        result=project_customer_statement_history(annual,quarterly,series)
        (a.output_root/f'{ticker}.customer.statement-history.json').write_bytes(canonical_bytes(result)+b'\n')
        records.append({'ticker':ticker,'annual_periods':result['annual']['retained_period_count'],
                        'quarterly_periods':result['quarterly']['retained_period_count'],
                        'annual_visible_cells':sum(result['annual']['cell_coverage'].values()),
                        'quarterly_visible_cells':sum(result['quarterly']['cell_coverage'].values()),
                        'quarterly_available_cells':result['quarterly']['cell_coverage']['available'],
                        'diluted_eps_available_periods':sum(x['diluted_eps']['status']=='AVAILABLE' for x in result['per_share_credibility']['records']),
                        'unverified_share_basis_periods':sum(x['share_basis']['status']=='PROVIDER_REPORTED_SHARE_BASIS_UNVERIFIED' for x in result['per_share_credibility']['records']),
                        'share_basis_discontinuities':sum(x['share_basis']['discontinuity_from_prior_period'] for x in result['per_share_credibility']['records'])})
    summary={'contract':'ATLAS_G6_CUSTOMER_STATEMENT_HISTORY_SUMMARY_V1','records':records,
             'totals':{key:sum(x[key] for x in records) for key in ('annual_periods','quarterly_periods','annual_visible_cells','quarterly_visible_cells','quarterly_available_cells','diluted_eps_available_periods','unverified_share_basis_periods','share_basis_discontinuities')},
             'provider_calls':0,'rating_authority':'UNCHANGED','publication_authority':'UNCHANGED'}
    (a.output_root/'customer_statement_history_summary.json').write_bytes(canonical_bytes(summary)+b'\n');print(json.dumps(summary,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
