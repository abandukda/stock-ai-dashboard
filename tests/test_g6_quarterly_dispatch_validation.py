import copy,hashlib,json
import pytest
from services.g6_quarterly_dispatch_validation import EXPECTED_TICKERS,canonical_bytes,validate_dispatch

def inputs():
    manifest={"contract":"ATLAS_G6_QUARTERLY_IMMUTABLE_BATCHES_V1","execution_authorized":False,"provider_calls":0,
              "endpoint":"/stock/financials-reported","frequency":"quarterly","batch_size":25,"batches":[{"batch_id":1,"symbols":list(EXPECTED_TICKERS)}]}
    manifest["sha256"]=hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    approval={"execution_authorized":False,"request_manifest_sha256":manifest["sha256"],"request_count":11,"sha256":"a"*64,
              "request_contract":{"method":"GET","endpoint":"/stock/financials-reported","parameters":{"symbol":"<EXACT_MANIFEST_SYMBOL>","freq":"quarterly"},"symbol_order":list(EXPECTED_TICKERS)},
              "rate_contract":{"original_request_ceiling":11,"absolute_provider_attempt_ceiling":11,"automatic_retry_ceiling_per_request":0,"scope":"SINGLE_GLOBAL_ACCOUNT_LEVEL_LIMITER"}}
    return approval,manifest

def test_exact_scope_is_dispatch_ready_but_remains_inert():
    a,m=inputs();r=validate_dispatch(a,m)
    assert r["status"]=="READY_FOR_EXPLICIT_OWNER_AUTHORIZATION" and r["execution_authorized"] is False and r["provider_calls"]==0
    assert set(r["checks"].values())=={"PASS"}

@pytest.mark.parametrize("mutation,error",[("symbol","ALLOWLIST"),("freq","PARAMETER"),("calls","CEILING"),("active","INERT")])
def test_scope_mutations_fail_closed(mutation,error):
    a,m=inputs()
    if mutation=="symbol":a["request_contract"]["symbol_order"][0]="BAD"
    elif mutation=="freq":a["request_contract"]["parameters"]["freq"]="annual"
    elif mutation=="calls":a["rate_contract"]["absolute_provider_attempt_ceiling"]=12
    else:a["execution_authorized"]=True
    with pytest.raises(ValueError,match=error):validate_dispatch(a,m)
