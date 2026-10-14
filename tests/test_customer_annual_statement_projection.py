import copy
import pytest
from services.customer_annual_statement_projection import project_customer_annual_statements

def fixture():
    periods=[{"fiscal_period_end":f"20{x}-12-31","accession":str(x)} for x in range(20,26)]
    cells=[{"accession":str(x),"status":"AVAILABLE","value":x,"fact_id":str(x),"provenance":{"raw_sha256":"a"*64}} for x in range(20,26)]
    return {"contract":"ATLAS_G6_ANNUAL_STATEMENT_PRESENTATION_V1","ticker":"ABC","sha256":"p"*64,
            "source_normalized_sha256":"n"*64,"periods":periods,"statements":{"INCOME_STATEMENT":[{"field_id":"f","concept":"Revenue","observed_labels":["Revenue"],"unit":{"canonical":"USD"},"cells":cells}],"BALANCE_SHEET":[],"CASH_FLOW":[]},
            "core_metrics":[{"period":x} for x in range(20,26)],"trend_projections":{},"ratings_changed":False,"publications_changed":False}

def test_projection_is_recent_source_bound_and_read_only():
    x=project_customer_annual_statements(fixture())
    assert x["retained_period_count"]==6 and x["visible_period_count"]==5
    assert x["visible_periods"][0]["accession"]=="21"
    assert x["cell_coverage"]=={"available":5,"unavailable":0,"ambiguous":0}
    assert x["rating_authority"]=="UNCHANGED" and x["publication_authority"]=="UNCHANGED"
    assert x["statements"]["BALANCE_SHEET"]["empty_reason"]=="NO_RETAINED_STATEMENT_FIELDS"

def test_missing_and_ambiguous_never_become_zero():
    p=fixture();p["statements"]["INCOME_STATEMENT"][0]["cells"][-2:] = [
        {"accession":"24","status":"UNAVAILABLE","value":None,"reason":"FIELD_NOT_REPORTED_FOR_PERIOD"},
        {"accession":"25","status":"AMBIGUOUS","value":None,"reason":"MULTIPLE_FACTS_FOR_FIELD_PERIOD"}]
    x=project_customer_annual_statements(p)
    assert x["cell_coverage"]["unavailable"]==1 and x["cell_coverage"]["ambiguous"]==1
    assert [c["value"] for c in x["statements"]["INCOME_STATEMENT"]["rows"][0]["cells"][-2:]]==[None,None]

def test_protected_output_change_fails_closed():
    p=fixture();p["ratings_changed"]=True
    with pytest.raises(ValueError,match="PROTECTED_OUTPUT"):project_customer_annual_statements(p)
