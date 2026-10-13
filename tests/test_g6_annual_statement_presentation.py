import json
from pathlib import Path
import pytest
from services.g6_annual_statement_presentation import build_statement_presentation
from scripts.build_g6_statement_presentations import batches, build

def fixture():
    fact={"fact_id":"a:ic:0:Revenue","statement":"INCOME_STATEMENT","concept":"Revenue","label":"Revenue","value":10,
          "unit":{"canonical":"USD","original":"usd","currency":"USD","kind":"CURRENCY"},"provenance":{"raw_sha256":"a"*64}}
    filing={"identity":{"year":2024,"startDate":"2024-01-01","endDate":"2024-12-31","filedDate":"2025-02-01","acceptedDate":"2025-02-01","accessNumber":"a"},"facts":[fact]}
    norm={"contract":"ATLAS_G6_ANNUAL_STATEMENT_NORMALIZATION_V1","ticker":"ABC","normalized_sha256":"n"*64,"filings":[filing]}
    series={"contract":"ATLAS_G6_ANNUAL_FINANCIAL_SERIES_V1","ticker":"ABC","sha256":"s"*64,
            "periods":[{"accession":"a","metrics":{}}],"projections":{}}
    return norm,series

def test_presentation_preserves_dates_units_and_provenance():
    n,s=fixture();x=build_statement_presentation(n,s);row=x["statements"]["INCOME_STATEMENT"][0]
    assert x["periods"][0]["fiscal_period_end"]=="2024-12-31"
    assert row["unit"]["canonical"]=="USD" and row["cells"][0]["provenance"]["raw_sha256"]=="a"*64

def test_missing_field_is_period_specific_unavailable():
    n,s=fixture(); f=dict(n["filings"][0]);f["identity"]=dict(f["identity"],year=2025,endDate="2025-12-31",accessNumber="b");f["facts"]=[];n["filings"].append(f);s["periods"].append({"accession":"b","metrics":{}})
    cells=build_statement_presentation(n,s)["statements"]["INCOME_STATEMENT"][0]["cells"]
    assert cells[1]=={"accession":"b","status":"UNAVAILABLE","value":None,"reason":"FIELD_NOT_REPORTED_FOR_PERIOD"}

def test_duplicate_field_is_ambiguous_not_silently_selected():
    n,s=fixture();n["filings"][0]["facts"].append(dict(n["filings"][0]["facts"][0],fact_id="second",value=20))
    cell=build_statement_presentation(n,s)["statements"]["INCOME_STATEMENT"][0]["cells"][0]
    assert cell["status"]=="AMBIGUOUS" and cell["value"] is None

def test_contract_and_ticker_mismatch_fail_closed():
    n,s=fixture();s["ticker"]="OTHER"
    with pytest.raises(ValueError,match="SERIES_CONTRACT_OR_TICKER_MISMATCH"):build_statement_presentation(n,s)

def test_batches_are_bounded_and_deterministic():
    assert batches(["A","B","C"],2)==[["A","B"],["C"]]


def test_full_universe_is_never_labeled_published(tmp_path: Path):
    source=Path(__file__).resolve().parents[1]/"scripts"/"build_g6_statement_presentations.py"
    text=source.read_text()
    assert "ATLAS_G6_FULL_UNIVERSE_EXPANSION_MANIFEST_V1" in text
    assert "GOVERNED_FULL_UNIVERSE_NOT_CUSTOMER_PUBLISHED" in text
    assert "BLOCKED_AUTHORITATIVE_PUBLISHED_SYMBOL_IDENTITY_REQUIRED" in text


def test_quarterly_approval_is_inert_bounded_and_globally_governed():
    text=(Path(__file__).resolve().parents[1]/"scripts"/"build_g6_statement_presentations.py").read_text()
    assert '"execution_authorized":False' in text
    assert '"scope":"SINGLE_GLOBAL_ACCOUNT_LEVEL_LIMITER"' in text
    assert '"requests_per_minute":500' in text
    assert '"burst_requests_per_second_ceiling":20' in text
    assert '"HTTP_429"' in text and '"RAW_DIGEST_FAILURE"' in text
    assert '"absolute_provider_attempt_ceiling":len(tickers)*3' in text
