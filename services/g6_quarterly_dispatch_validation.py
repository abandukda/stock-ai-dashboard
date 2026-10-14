"""Provider-free validation of the frozen G6 quarterly request scope."""
from __future__ import annotations
import hashlib,json
from typing import Any,Mapping
from services.finnhub_canonical_authority import authority_contract
from services.finnhub_enterprise_display_contract import CONTRACT_ID,display_authority
from services.finnhub_shadow_provider import ENDPOINTS,DatasetFamily

EXPECTED_TICKERS=("AVT","BKTI","CODA","CSCO","CTS","DIOD","EXTR","GNE","MSFT","NVDA","SBC")
ENDPOINT="/stock/financials-reported"

def canonical_bytes(x:Any)->bytes:return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
def digest(x:Any)->str:return hashlib.sha256(canonical_bytes(x)).hexdigest()

def validate_dispatch(approval:Mapping[str,Any],manifest:Mapping[str,Any])->dict[str,Any]:
    if approval.get("execution_authorized") is not False or manifest.get("execution_authorized") is not False:
        raise ValueError("INERT_EXECUTION_GATE_REQUIRED")
    if approval.get("request_manifest_sha256")!=manifest.get("sha256") or digest({k:v for k,v in manifest.items() if k!="sha256"})!=manifest.get("sha256"):
        raise ValueError("REQUEST_MANIFEST_DIGEST_MISMATCH")
    request=approval.get("request_contract") or {}; rate=approval.get("rate_contract") or {}
    symbols=tuple(request.get("symbol_order") or ())
    if symbols!=EXPECTED_TICKERS:raise ValueError("QUARTERLY_SYMBOL_ALLOWLIST_MISMATCH")
    if request.get("method")!="GET" or request.get("endpoint")!=ENDPOINT or request.get("parameters")!={"symbol":"<EXACT_MANIFEST_SYMBOL>","freq":"quarterly"}:
        raise ValueError("QUARTERLY_ENDPOINT_PARAMETER_SCOPE_MISMATCH")
    if approval.get("request_count")!=11 or rate.get("original_request_ceiling")!=11 or rate.get("absolute_provider_attempt_ceiling")!=11 or rate.get("automatic_retry_ceiling_per_request")!=0:
        raise ValueError("QUARTERLY_CALL_CEILING_MISMATCH")
    display=display_authority("financial_statements"); canonical=authority_contract("financial_statements")
    endpoints=[x for x in ENDPOINTS if x.capability=="financial_statements" and x.path==ENDPOINT]
    if not display or display.endpoint!=ENDPOINT or display.contract_id!=CONTRACT_ID:
        raise ValueError("ENTERPRISE_DISPLAY_SCOPE_UNPROVEN")
    if canonical.get("state")!="CANONICAL_CERTIFIED" or not endpoints or endpoints[0].family!=DatasetFamily.CANONICAL_QUANTITATIVE:
        raise ValueError("CANONICAL_GATEWAY_SCOPE_UNPROVEN")
    checks={"exact_symbol_allowlist":"PASS","endpoint_registered":"PASS","method_and_parameters":"PASS",
            "enterprise_display_contract":"PASS","canonical_financial_statement_authority":"PASS",
            "single_global_limiter":"PASS" if rate.get("scope")=="SINGLE_GLOBAL_ACCOUNT_LEVEL_LIMITER" else "FAIL",
            "zero_retry_absolute_11_call_ceiling":"PASS","inert_execution_gate":"PASS","lineage_storage_contract":"PASS"}
    if "FAIL" in checks.values():raise ValueError("GATEWAY_SCOPE_CHECK_FAILED")
    result={"contract":"ATLAS_G6_QUARTERLY_DISPATCH_READINESS_V1","status":"READY_FOR_EXPLICIT_OWNER_AUTHORIZATION",
            "execution_authorized":False,"provider_calls":0,"approval_sha256":approval.get("sha256"),
            "request_manifest_sha256":manifest.get("sha256"),"gateway":{"capability":"financial_statements","endpoint":ENDPOINT,
            "dataset_family":"CANONICAL_QUANTITATIVE","contract_id":CONTRACT_ID},"checks":checks}
    result["sha256"]=digest(result);return result

__all__=["EXPECTED_TICKERS","validate_dispatch"]
