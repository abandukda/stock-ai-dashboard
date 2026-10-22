import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from scripts.run_licensed_research_gateway import MAX_RESPONSE_BYTES, RESPONSE_CHUNK_BYTES, run
from services.operations_gateway import canonical_bytes, sha256


class StreamResponse:
    def __init__(self, status_code=200, chunks=(b'{"data":[]}',), failure=None):
        self.status_code = status_code
        self.chunks = chunks
        self.failure = failure
        self.closed = False
        self.reads = 0

    @property
    def content(self):
        raise AssertionError('Unbounded content access is forbidden')

    def iter_content(self, *, chunk_size):
        assert chunk_size == RESPONSE_CHUNK_BYTES
        for chunk in self.chunks:
            self.reads += 1
            yield chunk
        if self.failure:
            raise self.failure

    def close(self):
        self.closed = True


def package(tmp_path: Path, *, operation="acquire", requests_rows=None, budget=None, policy=None):
    rows = requests_rows if requests_rows is not None else [{"ordinal":1,"method":"GET","endpoint":"/stock/financials-reported","ticker":"NVDA","parameters":{"symbol":"NVDA","freq":"annual"}}]
    scope={"source_sha":"a"*40,"execution_policy":policy or {"rate_limit_rpm":60,"concurrency":1,"retry_count":0},"requests":rows}
    digest=sha256(canonical_bytes(scope)); sp=tmp_path/"scope.json"; sp.write_text(json.dumps(scope))
    approval={"operation":operation,"source_sha":"a"*40,"scope_sha256":digest,"max_provider_calls":len(rows) if budget is None else budget,"authorization_token":f"ATLAS_{operation.upper()}:{digest}"}
    ap=tmp_path/"approval.json"; ap.write_text(json.dumps(approval)); return ap,sp


def execute(tmp_path, session, **kwargs):
    ap,sp=package(tmp_path, **kwargs)
    return run(approval_path=ap,scope_path=sp,output=tmp_path/"out",run_id="7")


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv('FINNHUB_API_KEY','PRIVATE_MOCK_KEY_NEVER_LOG')
    with patch('scripts.run_licensed_research_gateway.requests.Session') as session_cls:
        yield session_cls.return_value


def terminal(tmp_path):
    return json.loads((tmp_path/'out/run_summary.json').read_text())


def test_raw_first_single_streamed_request_closes_resources_and_never_redirects(session,tmp_path):
    response=StreamResponse(chunks=(b'{"data":', b'[]}', b''))
    session.get.return_value=response
    result=execute(tmp_path,session)
    assert result['provider_calls']==1 and result['status']=='PASS'
    assert result['responses_received']==1
    assert (tmp_path/'out/raw/00001.json').read_bytes()==b'{"data":[]}'
    assert result['telemetry'][0]['raw_sha256']==hashlib.sha256(b'{"data":[]}').hexdigest()
    assert result['telemetry'][0]['raw_complete'] is True
    assert response.closed
    session.close.assert_called_once()
    assert session.get.call_args.kwargs['stream'] is True
    assert session.get.call_args.kwargs['allow_redirects'] is False
    assert session.get.call_args.kwargs['timeout']==30
    assert session.mount.call_args.args[1].max_retries.total==0
    assert 'PRIVATE_MOCK_KEY_NEVER_LOG' not in (tmp_path/'out/run_summary.json').read_text()


@pytest.mark.parametrize('status,code', [(429,'RATE_LIMIT_STOP'),(401,'ENTITLEMENT_STOP'),(403,'ENTITLEMENT_STOP'),(302,'REDIRECT_STOP'),(307,'REDIRECT_STOP'),(500,'HTTP_STOP:500')])
def test_http_error_writes_terminal_receipt_and_stops_without_next_request(session,tmp_path,status,code):
    response=StreamResponse(status_code=status,chunks=(b'{}',))
    session.get.return_value=response
    rows=[{'ordinal':i,'method':'GET','endpoint':'/stock/earnings','ticker':ticker,'parameters':{'symbol':ticker}} for i,ticker in enumerate(('NVDA','MSFT'),1)]
    with pytest.raises(RuntimeError,match=code): execute(tmp_path,session,requests_rows=rows)
    result=terminal(tmp_path)
    assert result['status']=='FAIL' and result['provider_calls']==1
    assert result['retry_count']==0 and len(result['telemetry'])==1
    assert result['telemetry'][0]['raw_complete'] is True
    assert response.closed
    session.get.assert_called_once()
    session.close.assert_called_once()


def test_oversized_stream_is_incomplete_and_not_given_complete_hash(session,tmp_path):
    chunks=[b'x'*RESPONSE_CHUNK_BYTES]*(MAX_RESPONSE_BYTES//RESPONSE_CHUNK_BYTES+2)
    response=StreamResponse(chunks=chunks)
    session.get.return_value=response
    with pytest.raises(RuntimeError,match='RESPONSE_SIZE_STOP'): execute(tmp_path,session)
    result=terminal(tmp_path); record=result['telemetry'][0]
    assert record['raw_complete'] is False and record['raw_sha256'] is None
    prefix=(tmp_path/'out/raw/00001.incomplete').read_bytes()
    assert len(prefix)==MAX_RESPONSE_BYTES
    assert record['raw_prefix_sha256']==hashlib.sha256(prefix).hexdigest()
    assert not (tmp_path/'out/raw/00001.json').exists()
    assert response.reads==MAX_RESPONSE_BYTES//RESPONSE_CHUNK_BYTES+1
    assert response.closed
    session.close.assert_called_once()


def test_exact_size_complete_body_does_not_trip_bound(session,tmp_path):
    response=StreamResponse(chunks=(b'['+b' '*(MAX_RESPONSE_BYTES-2)+b']',))
    session.get.return_value=response
    result=execute(tmp_path,session)
    assert result['status']=='PASS'
    assert result['telemetry'][0]['raw_bytes']==MAX_RESPONSE_BYTES
    assert result['telemetry'][0]['raw_complete'] is True


def test_transport_timeout_counts_attempt_and_sanitizes_credential_url(session,tmp_path):
    session.get.side_effect=requests.Timeout('https://finnhub.io/api/v1/quote?token=PRIVATE_MOCK_KEY_NEVER_LOG')
    with pytest.raises(RuntimeError,match='TRANSPORT_STOP') as exc: execute(tmp_path,session)
    assert 'PRIVATE_MOCK_KEY_NEVER_LOG' not in str(exc.value)
    result=terminal(tmp_path)
    assert result['attempted_transport_calls']==1 and result['responses_received']==0
    assert result['telemetry'][0]['raw_sha256'] is None
    assert result['telemetry'][0]['raw_capture']=='NO_RESPONSE'
    assert 'PRIVATE_MOCK_KEY_NEVER_LOG' not in (tmp_path/'out/run_summary.json').read_text()
    session.close.assert_called_once()


def test_partial_transport_failure_never_receives_complete_hash(session,tmp_path):
    response=StreamResponse(chunks=(b'{"data":',),failure=requests.ConnectionError('secret URL PRIVATE_MOCK_KEY_NEVER_LOG'))
    session.get.return_value=response
    with pytest.raises(RuntimeError,match='TRANSPORT_STOP'): execute(tmp_path,session)
    record=terminal(tmp_path)['telemetry'][0]
    assert record['raw_sha256'] is None and record['raw_complete'] is False
    assert record['raw_capture']=='INCOMPLETE_STREAM_FAILURE'
    assert (tmp_path/'out/raw/00001.incomplete').read_bytes()==b'{"data":'
    assert record['raw_prefix_sha256']==hashlib.sha256(b'{"data":').hexdigest()
    assert (tmp_path/'out/raw/00001.metadata.json').is_file()
    assert not (tmp_path/'out/raw/00001.json').exists()
    assert response.closed
    session.close.assert_called_once()


@pytest.mark.parametrize('payload', [b'not json',b'"scalar"',b'\xff'])
def test_schema_failure_keeps_raw_receipt_without_retry(session,tmp_path,payload):
    response=StreamResponse(chunks=(payload,))
    session.get.return_value=response
    with pytest.raises(RuntimeError,match='SCHEMA_STOP'): execute(tmp_path,session)
    assert terminal(tmp_path)['status']=='FAIL'
    assert (tmp_path/'out/raw/00001.json').read_bytes()==payload
    assert response.closed and session.get.call_count==1


def test_untrusted_ticker_never_becomes_a_path(session,tmp_path):
    session.get.return_value=StreamResponse()
    rows=[{'ordinal':1,'method':'GET','endpoint':'/stock/earnings','ticker':'../../outside','parameters':{'symbol':'NVDA'}}]
    execute(tmp_path,session,requests_rows=rows)
    assert sorted(path.name for path in (tmp_path/'out/raw').iterdir())==['00001.json','00001.metadata.json']
    assert not (tmp_path/'outside.json').exists()


def test_provider_credential_echo_is_not_persisted_even_as_raw_response(session,tmp_path):
    response=StreamResponse(status_code=403,chunks=(b'{"error":"PRIVATE_MOCK_KEY_NEVER_LOG"}',))
    session.get.return_value=response
    with pytest.raises(RuntimeError,match='CREDENTIAL_ECHO_STOP'): execute(tmp_path,session)
    assert terminal(tmp_path)['telemetry'][0]['raw_capture']=='REJECTED_CREDENTIAL_ECHO'
    for path in (tmp_path/'out').rglob('*'):
        if path.is_file(): assert b'PRIVATE_MOCK_KEY_NEVER_LOG' not in path.read_bytes()
    assert response.closed


@pytest.mark.parametrize('kwargs,code', [({'operation':'validate'},'ACQUIRE_TOKEN_REQUIRED'),({'budget':0},'BUDGET_EXCEEDED'),({'policy':{'rate_limit_rpm':60,'concurrency':1,'retry_count':1}},'EXECUTION_POLICY_INVALID')])
def test_existing_authorization_and_budget_gates_precede_any_transport(session,tmp_path,kwargs,code):
    with pytest.raises(PermissionError,match=code): execute(tmp_path,session,**kwargs)
    session.get.assert_not_called()
    assert not (tmp_path/'out').exists()


def test_later_transport_failure_counts_every_attempt_and_does_not_repeat(session,tmp_path,monkeypatch):
    monkeypatch.setattr('scripts.run_licensed_research_gateway.time.sleep',lambda _:None)
    first=StreamResponse()
    session.get.side_effect=[first,requests.ConnectionError('PRIVATE_MOCK_KEY_NEVER_LOG')]
    rows=[{'ordinal':i,'method':'GET','endpoint':'/stock/earnings','ticker':ticker,'parameters':{'symbol':ticker}} for i,ticker in enumerate(('NVDA','MSFT'),1)]
    with pytest.raises(RuntimeError,match='TRANSPORT_STOP'): execute(tmp_path,session,requests_rows=rows)
    summary=terminal(tmp_path)
    assert summary['provider_calls']==2 and summary['responses_received']==1
    assert len(summary['telemetry'])==2 and session.get.call_count==2
    assert first.closed
    assert summary['telemetry'][0]['status']=='PASS'
    assert summary['telemetry'][1]['status']=='FAIL'


def test_credential_in_scope_value_stops_before_transport_or_metadata(session,tmp_path):
    rows=[{'ordinal':1,'method':'GET','endpoint':'/stock/earnings','ticker':'PRIVATE_MOCK_KEY_NEVER_LOG','parameters':{'symbol':'NVDA'}}]
    with pytest.raises(RuntimeError,match='SCOPE_CREDENTIAL_STOP'): execute(tmp_path,session,requests_rows=rows)
    session.get.assert_not_called()
    summary=terminal(tmp_path)
    assert summary['provider_calls']==0 and summary['telemetry']==[]
    assert 'PRIVATE_MOCK_KEY_NEVER_LOG' not in (tmp_path/'out/run_summary.json').read_text()


def test_session_close_failure_is_terminal_failure_not_success(session,tmp_path):
    response=StreamResponse()
    session.get.return_value=response
    session.close.side_effect=RuntimeError('PRIVATE_MOCK_KEY_NEVER_LOG')
    with pytest.raises(RuntimeError,match='SESSION_CLOSE_STOP'): execute(tmp_path,session)
    assert terminal(tmp_path)['status']=='FAIL'
    assert response.closed
    assert 'PRIVATE_MOCK_KEY_NEVER_LOG' not in (tmp_path/'out/run_summary.json').read_text()
