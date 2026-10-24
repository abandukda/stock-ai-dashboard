from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

import pytest

from services.licensed_research_private_execution import execute_private_capture
from services.licensed_research_private_execution import _run_bounded
from services.operations_gateway import canonical_bytes, sha256
from services.research_refresh_execution import request_parameters
from services.finnhub_enterprise_display_contract import display_authority


SOURCE = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
NOW = "2026-10-24T12:00:00+00:00"


def private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    return path


def package(tmp_path: Path):
    from datetime import date
    tmp_path.mkdir(parents=True, exist_ok=True)
    requests = []
    for ticker in ("NVDA", "SPY"):
        for capability in ("historical_ohlcv", "splits", "dividends"):
            requests.append({"ordinal": len(requests) + 1, "method": "GET", "ticker": ticker,
                             "capability": capability, "endpoint": display_authority(capability).endpoint,
                             "parameters": request_parameters(capability, ticker, as_of=date(2026, 10, 23))})
    scope = {"source_sha": SOURCE, "as_of": "2026-10-23",
             "execution_policy": {"rate_limit_rpm": 1, "concurrency": 1, "retry_count": 0},
             "requests": requests, "publication_authority": "NONE"}
    scope_sha = sha256(canonical_bytes(scope))
    approval = {"operation": "acquire", "source_sha": SOURCE, "scope_sha256": scope_sha,
                "max_provider_calls": 6, "authorization_token": f"ATLAS_ACQUIRE:{scope_sha}"}
    scope_path, approval_path = tmp_path / "scope.json", tmp_path / "approval.json"
    scope_path.write_text(json.dumps(scope)); approval_path.write_text(json.dumps(approval))
    return scope_path, approval_path, scope_sha


def fake_gateway(*, approval_path, scope_path, output, run_id):
    scope = json.loads(scope_path.read_text())
    scope_sha = sha256(canonical_bytes(scope))
    output.mkdir()
    raw_root = output / "raw"; raw_root.mkdir()
    telemetry = []
    for row in scope["requests"]:
        body = json.dumps({"fixture": row["ordinal"]}).encode()
        name = f"{row['ordinal']:05d}.json"
        (raw_root / name).write_bytes(body)
        metadata = {"ordinal": row["ordinal"], "ticker": row["ticker"], "endpoint": row["endpoint"],
                    "parameters": row["parameters"], "status": "PASS", "status_code": 200,
                    "attempt_count": 1, "retry_count": 0, "raw_complete": True,
                    "raw_capture": "COMPLETE", "raw_file": name, "raw_bytes": len(body),
                    "raw_sha256": hashlib.sha256(body).hexdigest(),
                    "attempt_started_at": NOW, "response_completed_at": NOW}
        telemetry.append(metadata)
        (raw_root / f"{row['ordinal']:05d}.metadata.json").write_text(json.dumps(metadata))
    summary = {"contract": "ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1", "source_sha": SOURCE,
               "scope_sha256": scope_sha, "run_id": run_id, "status": "PASS", "failure_code": None,
               "provider_calls": 6, "attempted_transport_calls": 6, "responses_received": 6,
               "automatic_redirects": False, "retry_count": 0, "capture_started_at": NOW,
               "capture_completed_at": NOW, "telemetry": telemetry}
    (output / "run_summary.json").write_text(json.dumps(summary))
    return summary


def kwargs(tmp_path):
    scope, approval, scope_sha = package(tmp_path)
    packet = {"schema": "ATLAS_LICENSED_RESEARCH_PRIVATE_EXECUTION_V1",
              "checkout_sha": SOURCE, "source_sha": SOURCE, "scope_sha256": scope_sha,
              "run_id": "pilot-001",
              "gateway_sha256": hashlib.sha256(Path("scripts/run_licensed_research_gateway.py").read_bytes()).hexdigest(),
              "wrapper_sha256": hashlib.sha256(Path("services/licensed_research_private_execution.py").read_bytes()).hexdigest(),
              "cli_sha256": hashlib.sha256(Path("scripts/run_private_licensed_research_capture.py").read_bytes()).hexdigest(),
              "execution_policy": {"rate_limit_rpm": 1, "concurrency": 1, "retry_count": 0},
              "execution_timeout_seconds": 900}
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True))
    return dict(approval_path=approval, scope_path=scope,
                entitlement_path=Path("config/report_card_g2_entitlement_20261014.json"),
                primary_root=private(tmp_path / "primary"), claim_root=private(tmp_path / "claims"),
                receipt_path=tmp_path / "sanitized" / "receipt.json", packet_path=packet_path,
                expected_packet_sha256=hashlib.sha256(packet_path.read_bytes()).hexdigest(),
                repository_root=Path.cwd(), gateway_executor=fake_gateway,
                clock=lambda: datetime(2026, 10, 24, 12, tzinfo=timezone.utc))


def test_live_gate_prevents_claim_or_execution(tmp_path):
    values = kwargs(tmp_path)
    with pytest.raises(PermissionError, match="LIVE_DISABLED"):
        execute_private_capture(**values)
    assert not list(values["claim_root"].iterdir())


def test_private_capture_claim_hashes_and_sanitized_receipt_without_backup(tmp_path):
    values = kwargs(tmp_path)
    receipt = execute_private_capture(**values, live_enabled=True)
    assert receipt["status"] == "PASS"
    assert receipt["backup_status"] == "UNVERIFIED_NOT_REQUIRED_FOR_CAPTURE_PROOF"
    assert receipt["backup_tree_sha256"] is None and receipt["raw_data_in_receipt"] is False
    assert len(list((values["primary_root"] / "pilot-001" / "raw").glob("*.json"))) == 12
    assert all(path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
               for path in (values["primary_root"] / "pilot-001").rglob("*"))
    serialized = values["receipt_path"].read_text()
    assert "parameters" not in serialized and "fixture" not in serialized
    with pytest.raises(FileExistsError):
        execute_private_capture(**values, live_enabled=True)


def test_optional_backup_is_hash_verified(tmp_path):
    values = kwargs(tmp_path)
    values["backup_root"] = private(tmp_path / "backup")
    receipt = execute_private_capture(**values, live_enabled=True)
    assert receipt["backup_status"] == "HASH_VERIFIED"
    assert receipt["primary_tree_sha256"] == receipt["backup_tree_sha256"]


def test_exact_identity_and_real_entitlement_are_required(tmp_path):
    values = kwargs(tmp_path)
    packet = json.loads(values["packet_path"].read_text()); packet["source_sha"] = "b" * 40
    values["packet_path"].write_text(json.dumps(packet, sort_keys=True))
    values["expected_packet_sha256"] = hashlib.sha256(values["packet_path"].read_bytes()).hexdigest()
    with pytest.raises(PermissionError, match="IMPLEMENTATION_IDENTITY"):
        execute_private_capture(**values, live_enabled=True)
    values = kwargs(tmp_path / "second")
    bad = tmp_path / "bad-entitlement.json"
    entitlement = json.loads(Path("config/report_card_g2_entitlement_20261014.json").read_text())
    entitlement["endpoint_evidence"]["agreement_appendix"].remove("/stock/dividend")
    bad.write_text(json.dumps(entitlement)); values["entitlement_path"] = bad
    with pytest.raises(PermissionError, match="ENTITLEMENT_SCOPE"):
        execute_private_capture(**values, live_enabled=True)


def test_raw_hash_mismatch_consumes_claim_and_emits_sanitized_failure_receipt(tmp_path):
    values = kwargs(tmp_path)
    def corrupt(**arguments):
        fake_gateway(**arguments)
        metadata = arguments["output"] / "raw" / "00001.metadata.json"
        value = json.loads(metadata.read_text()); value["raw_sha256"] = "0" * 64
        metadata.write_text(json.dumps(value))
    values["gateway_executor"] = corrupt
    with pytest.raises(ValueError, match="BINDING"):
        execute_private_capture(**values, live_enabled=True)
    assert len(list(values["claim_root"].iterdir())) == 1
    failure = json.loads(values["receipt_path"].read_text())
    assert failure["status"] == "FAIL" and failure["claim_retained"] is True
    assert failure["success_receipt_emitted"] is False and failure["raw_data_in_receipt"] is False


def test_packet_digest_checkout_hash_and_canonical_scope_are_bound(tmp_path):
    values = kwargs(tmp_path)
    values["expected_packet_sha256"] = "0" * 64
    with pytest.raises(PermissionError, match="PACKET_DIGEST"):
        execute_private_capture(**values, live_enabled=True)
    values = kwargs(tmp_path / "hash")
    packet = json.loads(values["packet_path"].read_text()); packet["wrapper_sha256"] = "0" * 64
    values["packet_path"].write_text(json.dumps(packet, sort_keys=True))
    values["expected_packet_sha256"] = hashlib.sha256(values["packet_path"].read_bytes()).hexdigest()
    with pytest.raises(PermissionError, match="IMPLEMENTATION_IDENTITY"):
        execute_private_capture(**values, live_enabled=True)
    values = kwargs(tmp_path / "symbol")
    scope = json.loads(values["scope_path"].read_text()); scope["requests"][0]["parameters"]["symbol"] = "MSFT"
    values["scope_path"].write_text(json.dumps(scope))
    new_scope_sha = sha256(canonical_bytes(scope))
    approval = json.loads(values["approval_path"].read_text())
    approval.update(scope_sha256=new_scope_sha, authorization_token=f"ATLAS_ACQUIRE:{new_scope_sha}")
    values["approval_path"].write_text(json.dumps(approval))
    packet = json.loads(values["packet_path"].read_text()); packet["scope_sha256"] = new_scope_sha
    values["packet_path"].write_text(json.dumps(packet, sort_keys=True))
    values["expected_packet_sha256"] = hashlib.sha256(values["packet_path"].read_bytes()).hexdigest()
    with pytest.raises(PermissionError, match="CANONICAL_REQUEST"):
        execute_private_capture(**values, live_enabled=True)


@pytest.mark.parametrize("rpm", [1, 60])
def test_supported_rate_is_exactly_bound_to_scope_and_packet(tmp_path, rpm):
    values = kwargs(tmp_path)
    scope = json.loads(values["scope_path"].read_text()); scope["execution_policy"]["rate_limit_rpm"] = rpm
    values["scope_path"].write_text(json.dumps(scope))
    scope_sha = sha256(canonical_bytes(scope))
    approval = json.loads(values["approval_path"].read_text())
    approval.update(scope_sha256=scope_sha, authorization_token=f"ATLAS_ACQUIRE:{scope_sha}")
    values["approval_path"].write_text(json.dumps(approval))
    packet = json.loads(values["packet_path"].read_text())
    packet["scope_sha256"] = scope_sha; packet["execution_policy"]["rate_limit_rpm"] = rpm
    values["packet_path"].write_text(json.dumps(packet, sort_keys=True))
    values["expected_packet_sha256"] = hashlib.sha256(values["packet_path"].read_bytes()).hexdigest()
    receipt = execute_private_capture(**values, live_enabled=True)
    assert receipt["status"] == "PASS"


def test_scope_policy_cannot_differ_from_approved_packet(tmp_path):
    values = kwargs(tmp_path)
    scope = json.loads(values["scope_path"].read_text()); scope["execution_policy"]["rate_limit_rpm"] = 2
    values["scope_path"].write_text(json.dumps(scope))
    scope_sha = sha256(canonical_bytes(scope))
    approval = json.loads(values["approval_path"].read_text())
    approval.update(scope_sha256=scope_sha, authorization_token=f"ATLAS_ACQUIRE:{scope_sha}")
    values["approval_path"].write_text(json.dumps(approval))
    packet = json.loads(values["packet_path"].read_text()); packet["scope_sha256"] = scope_sha
    values["packet_path"].write_text(json.dumps(packet, sort_keys=True))
    values["expected_packet_sha256"] = hashlib.sha256(values["packet_path"].read_bytes()).hexdigest()
    with pytest.raises(PermissionError, match="SESSION_OR_POLICY"):
        execute_private_capture(**values, live_enabled=True)


def test_gateway_receives_owned_snapshots_not_mutable_originals(tmp_path):
    values = kwargs(tmp_path)
    original_scope, original_approval = values["scope_path"], values["approval_path"]
    observed = {}
    def inspect(**arguments):
        observed.update(arguments)
        assert arguments["scope_path"] != original_scope
        assert arguments["approval_path"] != original_approval
        assert arguments["scope_path"].parent.name.startswith(".inputs-")
        original_scope.write_text("{}")
        original_approval.write_text("{}")
        return fake_gateway(**arguments)
    values["gateway_executor"] = inspect
    receipt = execute_private_capture(**values, live_enabled=True)
    assert receipt["status"] == "PASS"
    assert json.loads(observed["scope_path"].read_text())["source_sha"] == SOURCE


def test_partial_gateway_failure_is_hardened_fsynced_and_sanitized(tmp_path, monkeypatch):
    values = kwargs(tmp_path)
    fsync_calls = []
    real_fsync = __import__("os").fsync
    monkeypatch.setattr("services.licensed_research_private_execution.os.fsync",
                        lambda descriptor: (fsync_calls.append(descriptor), real_fsync(descriptor))[1])
    def partial(**arguments):
        arguments["output"].mkdir()
        raw = arguments["output"] / "raw"; raw.mkdir()
        (raw / "00001.incomplete").write_bytes(b"partial-safe-prefix")
        (raw / "00001.metadata.json").write_text(json.dumps({"status": "FAIL"}))
        raise RuntimeError("fixture interruption details must not leak")
    values["gateway_executor"] = partial
    with pytest.raises(RuntimeError):
        execute_private_capture(**values, live_enabled=True)
    output = values["primary_root"] / "pilot-001"
    assert all(path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
               for path in output.rglob("*"))
    assert len(fsync_calls) >= 8
    failure_text = values["receipt_path"].read_text()
    assert "fixture interruption" not in failure_text and "partial-safe-prefix" not in failure_text
    assert json.loads(failure_text)["failure_class"] == "RuntimeError"
    assert len(list(values["claim_root"].iterdir())) == 1


def test_hard_execution_timeout_retains_claim_and_failure_receipt(tmp_path, monkeypatch):
    values = kwargs(tmp_path)
    packet = json.loads(values["packet_path"].read_text()); packet["execution_timeout_seconds"] = 60
    values["packet_path"].write_text(json.dumps(packet, sort_keys=True))
    values["expected_packet_sha256"] = hashlib.sha256(values["packet_path"].read_bytes()).hexdigest()
    def timeout(_executor, *, timeout_seconds, arguments):
        raise TimeoutError("synthetic hard timeout")
    monkeypatch.setattr("services.licensed_research_private_execution._run_bounded", timeout)
    with pytest.raises(TimeoutError):
        execute_private_capture(**values, live_enabled=True)
    failure = json.loads(values["receipt_path"].read_text())
    assert failure["failure_class"] == "TimeoutError" and failure["claim_retained"] is True


def test_finalized_run_fsyncs_its_containing_primary_directory(tmp_path, monkeypatch):
    values = kwargs(tmp_path)
    opened = []
    real_open = __import__("os").open
    def recording_open(path, flags, *args):
        opened.append(Path(path).absolute())
        return real_open(path, flags, *args)
    monkeypatch.setattr("services.licensed_research_private_execution.os.open", recording_open)
    receipt = execute_private_capture(**values, live_enabled=True)
    assert receipt["status"] == "PASS"
    assert values["primary_root"].absolute() in opened
    assert (values["primary_root"] / "pilot-001").absolute() in opened


def test_real_main_thread_alarm_interrupts_sleeping_operation_quickly():
    def sleeping(**_arguments):
        time.sleep(1)
        return {}
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="HARD_TIMEOUT"):
        _run_bounded(sleeping, timeout_seconds=0.02, arguments={})
    assert time.monotonic() - started < 0.5
