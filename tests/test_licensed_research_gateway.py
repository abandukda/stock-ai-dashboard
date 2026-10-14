import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.run_licensed_research_gateway import run
from services.operations_gateway import canonical_bytes, sha256


def package(tmp_path: Path, *, operation="acquire"):
    scope={"source_sha":"a"*40,"execution_policy":{"rate_limit_rpm":60,"concurrency":1,"retry_count":0},"requests":[{"ordinal":1,"method":"GET","endpoint":"/stock/financials-reported","ticker":"NVDA","parameters":{"symbol":"NVDA","freq":"annual"}}]}
    digest=sha256(canonical_bytes(scope)); sp=tmp_path/"scope.json"; sp.write_text(json.dumps(scope))
    approval={"operation":operation,"source_sha":"a"*40,"scope_sha256":digest,"max_provider_calls":1,"authorization_token":f"ATLAS_{operation.upper()}:{digest}"}
    ap=tmp_path/"approval.json"; ap.write_text(json.dumps(approval)); return ap,sp


@patch.dict("os.environ", {"FINNHUB_API_KEY":"secret"})
@patch("scripts.run_licensed_research_gateway.requests.Session")
def test_raw_first_single_request(session_cls, tmp_path):
    response=Mock(status_code=200,content=b'{"data":[]}'); session_cls.return_value.get.return_value=response
    ap,sp=package(tmp_path); result=run(approval_path=ap,scope_path=sp,output=tmp_path/"out",run_id="7")
    assert result["provider_calls"]==1
    assert (tmp_path/"out/raw/00001-NVDA.json").read_bytes()==response.content


@patch.dict("os.environ", {"FINNHUB_API_KEY":"secret"})
@patch("scripts.run_licensed_research_gateway.requests.Session")
def test_429_stops_without_retry(session_cls,tmp_path):
    session_cls.return_value.get.return_value=Mock(status_code=429,content=b'{}')
    ap,sp=package(tmp_path)
    with pytest.raises(RuntimeError,match="RATE_LIMIT_STOP"): run(approval_path=ap,scope_path=sp,output=tmp_path/"out",run_id="7")
    assert session_cls.return_value.get.call_count==1
