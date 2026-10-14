import copy
import json
from pathlib import Path

import pytest

from scripts.run_ws3_batch import run, validate_package

PACKAGE=Path("output/joint/ws3_expansion/WS3-B0001-approval.json")
SOURCE="aa12ff9e89c1ac72e20aadad41decfba9a3d774d"


def package():return json.loads(PACKAGE.read_text())


@pytest.mark.parametrize("mutation",["token","source","cap","pacing","endpoint","duplicate","secret","digest"])
def test_package_fails_closed(mutation):
    p=package();token=p["required_authorization_token"];source=SOURCE
    if mutation=="token":token="wrong"
    elif mutation=="source":source="b"*40
    elif mutation=="cap":p["request_cap"]=26
    elif mutation=="pacing":p["pacing"]["retry_count"]=1
    elif mutation=="endpoint":p["endpoint"]="/arbitrary"
    elif mutation=="duplicate":p["tickers"][1]=p["tickers"][0]
    elif mutation=="secret":p["frequency"]="annual&token=bad"
    elif mutation=="digest":p["tickers"][0]="ZZZ"
    with pytest.raises(PermissionError):validate_package(p,token,source)


class Response:
    def __init__(self,status=200,body=b'{}'):self.status_code=status;self.content=body
class Session:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def get(self,url,params,timeout):self.calls.append((url,params,timeout));return self.responses.pop(0)


def test_raw_is_persisted_before_http_stop(tmp_path,monkeypatch):
    p=package();p["tickers"]=p["tickers"][:1];p["request_count"]=1;p["request_cap"]=25
    from scripts.run_ws3_batch import _manifest
    from scripts.plan_g6_enterprise_expansion import digest
    p["immutable_batch_manifest_sha256"]=digest(_manifest(p));p["required_authorization_token"]=f"AUTHORIZE_WS3_BATCH:{p['batch_id']}:{p['immutable_batch_manifest_sha256']}"
    local=tmp_path/"package.json";local.write_text(json.dumps(p));monkeypatch.setenv("FINNHUB_API_KEY","secret")
    with pytest.raises(RuntimeError,match="HTTP_429"):
        run(package_path=local,output=tmp_path/"out",authorization_token=p["required_authorization_token"],source_sha=SOURCE,session=Session([Response(429,b'{"error":"rate"}')]),sleep=lambda _:None,monotonic=lambda:1.0)
    raw=tmp_path/"out/raw/00001-A.json";meta=tmp_path/"out/raw/00001-A.metadata.json"
    assert raw.read_bytes()==b'{"error":"rate"}' and json.loads(meta.read_text())["status_code"]==429


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, b'{"error":"unauthorized"}', "AUTH_OR_ENTITLEMENT"),
        (500, b'{"error":"temporary"}', "HTTP_STOP:500"),
        (200, b'not-json', "SCHEMA_STOP"),
    ],
)
def test_non_retryable_failures_persist_once_then_stop(tmp_path,monkeypatch,status,body,error):
    p=package();p["tickers"]=p["tickers"][:1];p["request_count"]=1;p["request_cap"]=25
    from scripts.run_ws3_batch import _manifest
    from scripts.plan_g6_enterprise_expansion import digest
    p["immutable_batch_manifest_sha256"]=digest(_manifest(p));p["required_authorization_token"]=f"AUTHORIZE_WS3_BATCH:{p['batch_id']}:{p['immutable_batch_manifest_sha256']}"
    local=tmp_path/"package.json";local.write_text(json.dumps(p));monkeypatch.setenv("FINNHUB_API_KEY","secret")
    session=Session([Response(status,body)])
    with pytest.raises(RuntimeError,match=error):
        run(package_path=local,output=tmp_path/"out",authorization_token=p["required_authorization_token"],source_sha=SOURCE,session=session,sleep=lambda _:None,monotonic=lambda:1.0)
    assert len(session.calls)==1
    assert (tmp_path/"out/raw/00001-A.json").read_bytes()==body


def test_success_has_exact_call_cap_no_secret_telemetry(tmp_path,monkeypatch):
    p=package();monkeypatch.setenv("FINNHUB_API_KEY","secret");session=Session([Response() for _ in range(25)])
    summary=run(package_path=PACKAGE,output=tmp_path/"out",authorization_token=p["required_authorization_token"],source_sha=SOURCE,session=session,sleep=lambda _:None,monotonic=lambda:1.0)
    assert summary["provider_calls"]==25 and summary["retry_count"]==0 and len(session.calls)==25
    assert all(call[1]["token"]=="secret" for call in session.calls)
    assert "secret" not in (tmp_path/"out/run_summary.json").read_text()


def test_workflow_uses_protected_environment_and_registered_code():
    text=Path(".github/workflows/atlas_ws3_research_batch.yml").read_text()
    assert "environment: atlas-licensed-research-acquisition" in text
    assert 'ref: ${{ github.sha }}' in text and "persist-credentials: false" in text
    assert "WS3-B0001" in text and "run_ws3_batch.py" in text
