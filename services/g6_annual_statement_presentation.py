"""Source-bound annual statement presentation contract.

The contract exposes retained facts without recomputing investment outputs.
Missing and ambiguous cells are explicit and field-specific.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Mapping

CONTRACT = "ATLAS_G6_ANNUAL_STATEMENT_PRESENTATION_V1"
STATEMENTS = ("INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW")

def _field_id(fact: Mapping[str, Any]) -> str:
    unit=fact["unit"]
    return "|".join((fact["statement"], fact["concept"], str(unit.get("canonical")), str(unit.get("original"))))

def build_statement_presentation(normalized: Mapping[str, Any], series: Mapping[str, Any]) -> dict[str, Any]:
    if normalized.get("contract") != "ATLAS_G6_ANNUAL_STATEMENT_NORMALIZATION_V1":
        raise ValueError("NORMALIZED_CONTRACT_MISMATCH")
    if series.get("contract") != "ATLAS_G6_ANNUAL_FINANCIAL_SERIES_V1" or series.get("ticker") != normalized.get("ticker"):
        raise ValueError("SERIES_CONTRACT_OR_TICKER_MISMATCH")
    selected_accessions={p["accession"] for p in series["periods"]}
    filings=[f for f in normalized["filings"] if f["identity"]["accessNumber"] in selected_accessions]
    filings.sort(key=lambda f: str(f["identity"]["endDate"]))
    periods=[{"fiscal_year":f["identity"]["year"],"fiscal_period_start":f["identity"]["startDate"],
              "fiscal_period_end":f["identity"]["endDate"],"filed_date":f["identity"]["filedDate"],
              "accepted_date":f["identity"]["acceptedDate"],"accession":f["identity"]["accessNumber"]} for f in filings]
    grouped: dict[str, dict[str, list[Mapping[str, Any]]]]=defaultdict(lambda:defaultdict(list))
    metadata={}
    for filing in filings:
        accession=filing["identity"]["accessNumber"]
        for fact in filing["facts"]:
            fid=_field_id(fact); grouped[fid][accession].append(fact)
            metadata.setdefault(fid,{"field_id":fid,"statement":fact["statement"],"concept":fact["concept"],
                                     "unit":fact["unit"],"observed_labels":set()})
            if fact.get("label"): metadata[fid]["observed_labels"].add(fact["label"])
    tables={statement:[] for statement in STATEMENTS}
    for fid,meta in sorted(metadata.items(),key=lambda x:(x[1]["statement"],x[1]["concept"],x[0])):
        cells=[]
        for period in periods:
            matches=grouped[fid].get(period["accession"],[])
            if not matches: cell={"status":"UNAVAILABLE","value":None,"reason":"FIELD_NOT_REPORTED_FOR_PERIOD"}
            elif len(matches)>1: cell={"status":"AMBIGUOUS","value":None,"reason":"MULTIPLE_FACTS_FOR_FIELD_PERIOD",
                                      "fact_ids":[x["fact_id"] for x in matches]}
            else:
                fact=matches[0]; cell={"status":"AVAILABLE","value":fact["value"],"fact_id":fact["fact_id"],
                                       "provenance":fact["provenance"]}
            cells.append({"accession":period["accession"],**cell})
        row={**meta,"observed_labels":sorted(meta["observed_labels"]),"cells":cells}
        tables[meta["statement"]].append(row)
    return {"contract":CONTRACT,"ticker":normalized["ticker"],"source_normalized_sha256":normalized["normalized_sha256"],
            "source_series_sha256":series.get("sha256"),"periods":periods,"statements":tables,
            "core_metrics":series["periods"],"trend_projections":series["projections"],
            "ratings_changed":False,"publications_changed":False}

__all__=["CONTRACT","STATEMENTS","build_statement_presentation"]
