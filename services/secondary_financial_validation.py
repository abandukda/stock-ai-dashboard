"""Bounded FMP validation evidence for the nightly Twelve canonical pipeline.

FMP values remain independent cross-checks and never silently replace canonical
inputs. Provider failures are ticker-local.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
from typing import Any, Mapping, Sequence

from services.fmp_stable_client import FMPStableClient

VERSION="ATLAS_SECONDARY_FINANCIAL_VALIDATION_V1"
ENDPOINTS=("income-statement","balance-sheet-statement","cash-flow-statement","enterprise-values")


def _number(value: Any) -> float | None:
    try: return float(value) if value is not None else None
    except (TypeError,ValueError): return None


def _record(payload: Any) -> Mapping[str,Any]:
    return payload[0] if isinstance(payload,list) and payload and isinstance(payload[0],Mapping) else {}


def _evidence_id(ticker: str, endpoint: str, period: Any, fetched: str) -> str:
    value=f"FMP|{ticker}|{endpoint}|{period}|{fetched}"
    return "FMPVAL-"+hashlib.sha256(value.encode()).hexdigest()[:20]


def acquire_secondary_fmp_inputs(symbols: Sequence[str], *, api_key: str,
                                 max_workers: int=8, session: Any=None) -> dict[str,Any]:
    clean=tuple(dict.fromkeys(str(x).strip().upper() for x in symbols if str(x).strip()))
    if not api_key:
        return {"version":VERSION,"status":"SECONDARY_SOURCE_UNAVAILABLE","inputs":{},"provider_calls":0}
    def fetch(symbol: str):
        client=FMPStableClient(api_key,timeout_seconds=12,retries=1,session=session) if session is not None else FMPStableClient(api_key,timeout_seconds=12,retries=1)
        records={}; outcomes={}; calls=0
        for endpoint in ENDPOINTS:
            response=client.get(endpoint,{"symbol":symbol,"period":"annual","limit":2})
            calls+=response.attempts
            outcomes[endpoint]=response.outcome
            records[endpoint]=(_record(response.payload),response.fetched_at)
        income,income_at=records["income-statement"];balance,balance_at=records["balance-sheet-statement"]
        cash,cash_at=records["cash-flow-statement"];enterprise,enterprise_at=records["enterprise-values"]
        period=income.get("date") or income.get("fiscalDateEnding")
        def item(value,endpoint,raw_field,as_of,basis="GAAP",item_period=period):
            return {"value":_number(value),"source":"FMP","endpoint":endpoint,"raw_field":raw_field,
                    "period":item_period,"period_type":"ANNUAL","basis":basis,"as_of":as_of,
                    "evidence_id":_evidence_id(symbol,endpoint,item_period,as_of)}
        inputs={
            "revenue":item(income.get("revenue"),"income-statement","revenue",income_at),
            "operating_income":item(income.get("operatingIncome"),"income-statement","operatingIncome",income_at),
            "net_income":item(income.get("netIncome"),"income-statement","netIncome",income_at),
            "eps":item(income.get("epsdiluted") or income.get("epsDiluted"),"income-statement","epsDiluted",income_at),
            "ebitda":item(income.get("ebitda"),"income-statement","ebitda",income_at),
            "diluted_shares":item(income.get("weightedAverageShsOutDil"),"income-statement","weightedAverageShsOutDil",income_at),
            "cash":item(balance.get("cashAndCashEquivalents") or balance.get("cashAndShortTermInvestments"),"balance-sheet-statement","cashAndCashEquivalents",balance_at,item_period=balance.get("date")),
            "debt":item(balance.get("totalDebt"),"balance-sheet-statement","totalDebt",balance_at,item_period=balance.get("date")),
            "operating_cash_flow":item(cash.get("operatingCashFlow"),"cash-flow-statement","operatingCashFlow",cash_at,item_period=cash.get("date")),
            "capex":item(cash.get("capitalExpenditure"),"cash-flow-statement","capitalExpenditure",cash_at,item_period=cash.get("date")),
            "free_cash_flow":item(cash.get("freeCashFlow"),"cash-flow-statement","freeCashFlow",cash_at,item_period=cash.get("date")),
            "current_shares_outstanding":item(enterprise.get("numberOfShares"),"enterprise-values","numberOfShares",enterprise_at,basis="CURRENT",item_period=enterprise.get("date")),
        }
        return symbol,{key:value for key,value in inputs.items() if value["value"] is not None},outcomes,calls
    inputs={}; telemetry={}; calls=0
    with ThreadPoolExecutor(max_workers=max(1,int(max_workers))) as pool:
        futures=[pool.submit(fetch,symbol) for symbol in clean]
        for future in as_completed(futures):
            symbol,values,outcomes,count=future.result();inputs[symbol]=values;telemetry[symbol]=outcomes;calls+=count
    return {"version":VERSION,"status":"AVAILABLE" if inputs else "SECONDARY_SOURCE_UNAVAILABLE",
            "inputs":inputs,"provider_calls":calls,"symbol_coverage":sum(bool(x) for x in inputs.values()),
            "endpoint_outcomes":telemetry,"observed_at":datetime.now(timezone.utc).isoformat()}


__all__=["ENDPOINTS","VERSION","acquire_secondary_fmp_inputs"]
