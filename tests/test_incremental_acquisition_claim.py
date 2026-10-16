import concurrent.futures
import json
import os
import pytest
from services.incremental_acquisition_claim import authorization_token, consume_claim, finalize_claim, scope_payload

def scope(**changes):
    values=dict(claim_id="oct15-2026-claim-0001",source_sha="a"*40,plan_sha256="b"*64,session="2026-10-15")
    values.update(changes); return scope_payload(**values)

def test_claim_is_bound_consumed_once_and_survives_restart(tmp_path):
    s=scope(); token=authorization_token(s); path=consume_claim(claims_root=tmp_path,scope=s,token=token)
    assert json.loads(path.read_text())["state"]=="CONSUMED"
    with pytest.raises(PermissionError,match="ALREADY_CONSUMED"): consume_claim(claims_root=tmp_path,scope=s,token=token)
    finalize_claim(path,outcome="FAILED_PROVIDER")
    with pytest.raises(PermissionError,match="ALREADY_CONSUMED"): consume_claim(claims_root=tmp_path,scope=s,token=token)

def test_concurrent_duplicate_has_exactly_one_winner(tmp_path):
    s=scope(); token=authorization_token(s)
    def run():
        try: consume_claim(claims_root=tmp_path,scope=s,token=token); return "OK"
        except PermissionError: return "REJECTED"
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:run(),range(2)))
    assert sorted(results)==["OK","REJECTED"]

@pytest.mark.parametrize("change",[{"source_sha":"c"*40},{"session":"2026-10-14"},{"membership_count":1297},{"max_requests":2747},{"automatic_retries":1}])
def test_incorrect_or_broadened_scope_rejected(tmp_path,change):
    s=scope(); altered={**s,**change}
    with pytest.raises(PermissionError): consume_claim(claims_root=tmp_path,scope=altered,token=authorization_token(s))

def test_interrupted_persistence_never_restores_claim(monkeypatch,tmp_path):
    s=scope(); token=authorization_token(s)
    monkeypatch.setattr(os,"fsync",lambda _fd: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError): consume_claim(claims_root=tmp_path,scope=s,token=token)
    assert (tmp_path/f"{s['claim_id']}.json").exists()
    with pytest.raises(PermissionError,match="ALREADY_CONSUMED"): consume_claim(claims_root=tmp_path,scope=s,token=token)

def test_closed_operation_rejected_before_claim(tmp_path,monkeypatch):
    monkeypatch.setenv("ATLAS_INCREMENTAL_MANUAL_ACQUIRE_ENABLED","false")
    assert not list(tmp_path.iterdir())
