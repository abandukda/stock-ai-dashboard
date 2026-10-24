"""Private, consume-once wrapper around the existing licensed Research gateway."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
from typing import Any, Callable, Mapping

from services.operations_gateway import GatewayApproval, canonical_bytes, verify_scope
from services.report_card_operational_controls import validate_entitlement
from services.report_card_exchange_calendar import build_xnys_calendar
from services.research_refresh_execution import request_parameters


SCHEMA = "ATLAS_LICENSED_RESEARCH_PRIVATE_EXECUTION_V1"
GATEWAY_SHA256 = "a9b9404d4458ef023552c18bca8790b1ccdf2c2c2c49aff504454a254ffa9f5a"
REQUIRED_CAPABILITIES = frozenset({"historical_ohlcv", "splits", "dividends"})
REQUIRED_ENDPOINTS = frozenset({"/stock/candle", "/stock/split", "/stock/dividend"})


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("PRIVATE_EXECUTION_JSON_OBJECT_REQUIRED")
    return value


def _private_root(path: Path) -> Path:
    path = path.absolute()
    if not path.exists() or path.is_symlink():
        raise PermissionError("PRIVATE_EXECUTION_PREEXISTING_ROOT_REQUIRED")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError("PRIVATE_EXECUTION_ROOT_PERMISSIONS_INVALID")
    return path


def _write_all(path: Path, body: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        offset = 0
        while offset < len(body):
            written = os.write(descriptor, body[offset:])
            if not isinstance(written, int) or written <= 0:
                raise OSError("PRIVATE_EXECUTION_WRITE_INCOMPLETE")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    persisted = path.read_bytes()
    if persisted != body:
        raise OSError("PRIVATE_EXECUTION_WRITE_VERIFY_FAILED")
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(persisted).hexdigest()


def _verify_entitlement(value: Mapping[str, Any]) -> str:
    validated = validate_entitlement(value)
    evidence = value.get("endpoint_evidence")
    if (validated.get("status") != "ENTITLEMENT_EVIDENCE_VALID"
            or not isinstance(evidence, Mapping)
            or evidence.get("adapter_exact_match") is not True
            or not REQUIRED_ENDPOINTS.issubset(set(evidence.get("agreement_appendix") or ()))):
        raise PermissionError("PRIVATE_EXECUTION_ENTITLEMENT_SCOPE_INVALID")
    return str(validated["evidence_sha256"])


def _gateway_digest(repository_root: Path) -> str:
    path = repository_root / "scripts" / "run_licensed_research_gateway.py"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != GATEWAY_SHA256:
        raise PermissionError("PRIVATE_EXECUTION_GATEWAY_IDENTITY_INVALID")
    return digest


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_execution_packet(packet_path: Path, *, expected_packet_sha256: str,
                             repository_root: Path) -> dict[str, Any]:
    body = packet_path.read_bytes()
    if (not re.fullmatch(r"[0-9a-f]{64}", expected_packet_sha256)
            or hashlib.sha256(body).hexdigest() != expected_packet_sha256):
        raise PermissionError("PRIVATE_EXECUTION_PACKET_DIGEST_INVALID")
    packet = _load(packet_path)
    required = {"schema", "checkout_sha", "source_sha", "scope_sha256", "run_id",
                "gateway_sha256", "wrapper_sha256", "cli_sha256", "execution_policy",
                "execution_timeout_seconds"}
    if set(packet) != required or packet.get("schema") != SCHEMA:
        raise ValueError("PRIVATE_EXECUTION_PACKET_SCHEMA_INVALID")
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository_root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise PermissionError("PRIVATE_EXECUTION_CHECKOUT_IDENTITY_UNAVAILABLE") from None
    hashes = {
        "gateway_sha256": _gateway_digest(repository_root),
        "wrapper_sha256": _file_digest(repository_root / "services" / "licensed_research_private_execution.py"),
        "cli_sha256": _file_digest(repository_root / "scripts" / "run_private_licensed_research_capture.py"),
    }
    if (packet.get("checkout_sha") != head or packet.get("source_sha") != head
            or any(packet.get(key) != value for key, value in hashes.items())):
        raise PermissionError("PRIVATE_EXECUTION_IMPLEMENTATION_IDENTITY_INVALID")
    policy = packet.get("execution_policy")
    if (not isinstance(policy, Mapping) or set(policy) != {"rate_limit_rpm", "concurrency", "retry_count"}
            or type(policy.get("rate_limit_rpm")) is not int or not 1 <= policy["rate_limit_rpm"] <= 60
            or policy.get("concurrency") != 1 or policy.get("retry_count") != 0):
        raise PermissionError("PRIVATE_EXECUTION_PACKET_POLICY_INVALID")
    if (type(packet.get("execution_timeout_seconds")) is not int
            or not 60 <= packet["execution_timeout_seconds"] <= 7200):
        raise PermissionError("PRIVATE_EXECUTION_PACKET_TIMEOUT_INVALID")
    return packet


def _verify_current_scope(scope: Mapping[str, Any], *, policy: Mapping[str, Any], now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("PRIVATE_EXECUTION_CLOCK_INVALID")
    recent = (now.astimezone(timezone.utc).date() - timedelta(days=10)).isoformat()
    finalized = build_xnys_calendar(start_date=recent, as_of=now)["finalized_session"]
    if scope.get("as_of") != finalized or scope.get("execution_policy") != dict(policy):
        raise PermissionError("PRIVATE_EXECUTION_SESSION_OR_POLICY_INVALID")
    finalized_day = datetime.fromisoformat(finalized).date()
    for row in scope.get("requests") or ():
        ticker, capability = row.get("ticker"), row.get("capability")
        parameters = row.get("parameters")
        if (not isinstance(ticker, str) or not isinstance(capability, str)
                or not isinstance(parameters, Mapping) or parameters.get("symbol") != ticker
                or parameters != request_parameters(capability, ticker, as_of=finalized_day)):
            raise PermissionError("PRIVATE_EXECUTION_CANONICAL_REQUEST_INVALID")


def _inventory(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PermissionError("PRIVATE_EXECUTION_SYMLINK_OUTPUT_FORBIDDEN")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _finalize_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PermissionError("PRIVATE_EXECUTION_SYMLINK_OUTPUT_FORBIDDEN")
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
        if path.is_file():
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    os.chmod(root, 0o700)
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory_path in sorted(directories, key=lambda item: len(item.parts), reverse=True) + [root]:
        descriptor = os.open(directory_path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    parent_descriptor = os.open(root.parent, os.O_RDONLY)
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _run_bounded(executor: Callable[..., dict[str, Any]], *, timeout_seconds: int,
                 arguments: Mapping[str, Any]) -> dict[str, Any]:
    if not hasattr(signal, "setitimer"):
        raise RuntimeError("PRIVATE_EXECUTION_HARD_TIMEOUT_UNAVAILABLE")
    prior_handler = signal.getsignal(signal.SIGALRM)
    def stop(_signum, _frame):
        raise TimeoutError("PRIVATE_EXECUTION_HARD_TIMEOUT")
    signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return executor(**dict(arguments))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)


def _verify_gateway_output(root: Path, *, source_sha: str, scope_sha256: str,
                           run_id: str, request_count: int) -> tuple[dict[str, Any], dict[str, str]]:
    summary = _load(root / "run_summary.json")
    if (summary.get("contract") != "ATLAS_LICENSED_RESEARCH_GATEWAY_RUN_V1"
            or summary.get("source_sha") != source_sha or summary.get("scope_sha256") != scope_sha256
            or summary.get("run_id") != run_id or summary.get("status") != "PASS"
            or summary.get("failure_code") is not None or summary.get("provider_calls") != request_count
            or summary.get("attempted_transport_calls") != request_count
            or summary.get("responses_received") != request_count
            or summary.get("automatic_redirects") is not False or summary.get("retry_count") != 0):
        raise ValueError("PRIVATE_EXECUTION_GATEWAY_SUMMARY_INVALID")
    telemetry = summary.get("telemetry")
    if not isinstance(telemetry, list) or len(telemetry) != request_count:
        raise ValueError("PRIVATE_EXECUTION_GATEWAY_TELEMETRY_INVALID")
    raw_root = root / "raw"
    for index, row in enumerate(telemetry, 1):
        raw_name = row.get("raw_file")
        if (row.get("ordinal") != index or row.get("status") != "PASS"
                or row.get("raw_complete") is not True or row.get("raw_capture") != "COMPLETE"
                or not isinstance(raw_name, str) or not re.fullmatch(r"\d{5}\.json", raw_name)):
            raise ValueError("PRIVATE_EXECUTION_GATEWAY_TELEMETRY_INVALID")
        raw_path = raw_root / raw_name
        if (not raw_path.is_file() or raw_path.is_symlink()
                or row.get("raw_bytes") != raw_path.stat().st_size
                or row.get("raw_sha256") != hashlib.sha256(raw_path.read_bytes()).hexdigest()):
            raise ValueError("PRIVATE_EXECUTION_RAW_BINDING_INVALID")
        metadata_path = raw_root / f"{index:05d}.metadata.json"
        if _load(metadata_path) != row:
            raise ValueError("PRIVATE_EXECUTION_METADATA_BINDING_INVALID")
    return summary, _inventory(root)


def execute_private_capture(
    *, approval_path: Path, scope_path: Path, entitlement_path: Path,
    primary_root: Path, claim_root: Path, receipt_path: Path, backup_root: Path | None = None,
    packet_path: Path, expected_packet_sha256: str,
    repository_root: Path, live_enabled: bool = False,
    gateway_executor: Callable[..., dict[str, Any]] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Run the existing gateway once, only after exact private preflight."""
    if live_enabled is not True:
        raise PermissionError("PRIVATE_EXECUTION_LIVE_DISABLED")
    primary, claims = map(_private_root, (primary_root, claim_root))
    backup = _private_root(backup_root) if backup_root is not None else None
    snapshot_root = primary / f".inputs-{expected_packet_sha256}"
    snapshot_root.mkdir(mode=0o700)
    snapshot_paths = {}
    for name, source in (("approval", approval_path), ("scope", scope_path),
                         ("entitlement", entitlement_path), ("packet", packet_path)):
        destination = snapshot_root / f"{name}.json"
        _write_all(destination, source.read_bytes())
        snapshot_paths[name] = destination
    _finalize_tree(snapshot_root)
    packet = _verify_execution_packet(snapshot_paths["packet"],
        expected_packet_sha256=expected_packet_sha256, repository_root=repository_root)
    run_id = str(packet["run_id"])
    expected_source_sha = str(packet["source_sha"])
    expected_scope_sha256 = str(packet["scope_sha256"])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise ValueError("PRIVATE_EXECUTION_RUN_ID_INVALID")
    approval = GatewayApproval.parse(_load(snapshot_paths["approval"]))
    if (approval.operation != "acquire" or approval.source_sha != expected_source_sha
            or approval.scope_sha256 != expected_scope_sha256):
        raise PermissionError("PRIVATE_EXECUTION_APPROVAL_IDENTITY_INVALID")
    scope = verify_scope(snapshot_paths["scope"], approval)
    _verify_current_scope(
        scope, policy=packet["execution_policy"],
        now=(clock or (lambda: datetime.now(timezone.utc)))(),
    )
    requests = list(scope.get("requests") or ())
    if len(requests) != 6 or approval.max_provider_calls != 6:
        raise PermissionError("PRIVATE_EXECUTION_SIX_REQUEST_SCOPE_REQUIRED")
    actual_pairs = {(row.get("ticker"), row.get("endpoint")) for row in requests}
    expected_pairs = {(ticker, endpoint) for ticker in ("NVDA", "SPY") for endpoint in REQUIRED_ENDPOINTS}
    if actual_pairs != expected_pairs:
        raise PermissionError("PRIVATE_EXECUTION_PILOT_SCOPE_INVALID")
    entitlement_sha = _verify_entitlement(_load(snapshot_paths["entitlement"]))
    gateway_sha = _gateway_digest(repository_root)
    resolved = tuple(path.resolve() for path in (primary, claims, *((backup,) if backup else ())))
    if (len(set(resolved)) != len(resolved)
            or any(left.is_relative_to(right) or right.is_relative_to(left)
                   for index, left in enumerate(resolved) for right in resolved[index + 1:])):
        raise PermissionError("PRIVATE_EXECUTION_INDEPENDENT_ROOTS_REQUIRED")
    output = primary / run_id
    backup_output = backup / run_id if backup else None
    if output.exists() or (backup_output is not None and backup_output.exists()):
        raise FileExistsError("PRIVATE_EXECUTION_OUTPUT_ALREADY_EXISTS")
    claim = claims / f".{expected_scope_sha256}.consumed"
    claim_body = canonical_bytes({
        "schema": SCHEMA, "classification": "LIVE_ACQUISITION_AUTHORIZATION_CONSUMED",
        "run_id": run_id, "source_sha": expected_source_sha,
        "scope_sha256": expected_scope_sha256, "gateway_sha256": gateway_sha,
        "entitlement_sha256": entitlement_sha,
    }) + b"\n"
    claim_sha = _write_all(claim, claim_body)
    executor = gateway_executor
    if executor is None:
        from scripts.run_licensed_research_gateway import run as executor
    try:
        _run_bounded(executor, timeout_seconds=packet["execution_timeout_seconds"], arguments={
            "approval_path": snapshot_paths["approval"], "scope_path": snapshot_paths["scope"],
            "output": output, "run_id": run_id,
        })
        _finalize_tree(output)
        summary, primary_inventory = _verify_gateway_output(
            output, source_sha=expected_source_sha, scope_sha256=expected_scope_sha256,
            run_id=run_id, request_count=6,
        )
        backup_inventory = None
        if backup_output is not None:
            shutil.copytree(output, backup_output, copy_function=shutil.copy2)
            _finalize_tree(backup_output)
            backup_inventory = _inventory(backup_output)
            if backup_inventory != primary_inventory:
                raise OSError("PRIVATE_EXECUTION_BACKUP_VERIFY_FAILED")
    except BaseException as exc:
        _finalize_tree(output)
        failure = {
            "schema": SCHEMA, "status": "FAIL", "run_id": run_id,
            "source_sha": expected_source_sha, "scope_sha256": expected_scope_sha256,
            "gateway_sha256": gateway_sha, "entitlement_sha256": entitlement_sha,
            "claim_sha256": claim_sha, "failure_class": type(exc).__name__,
            "raw_data_in_receipt": False, "publication_authority": "NONE",
            "claim_retained": True, "success_receipt_emitted": False,
        }
        failure["receipt_sha256"] = _digest(failure)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        _write_all(receipt_path, canonical_bytes(failure) + b"\n")
        raise
    receipt = {
        "schema": SCHEMA, "status": "PASS", "run_id": run_id,
        "source_sha": expected_source_sha, "scope_sha256": expected_scope_sha256,
        "gateway_sha256": gateway_sha, "entitlement_sha256": entitlement_sha,
        "claim_sha256": claim_sha, "request_count": 6,
        "capture_started_at": summary.get("capture_started_at"),
        "capture_completed_at": summary.get("capture_completed_at"),
        "primary_tree_sha256": _digest(primary_inventory),
        "backup_status": "HASH_VERIFIED" if backup_inventory is not None else "UNVERIFIED_NOT_REQUIRED_FOR_CAPTURE_PROOF",
        "backup_tree_sha256": _digest(backup_inventory) if backup_inventory is not None else None,
        "raw_data_in_receipt": False, "publication_authority": "NONE",
        "request_timeout_seconds": 30,
        "execution_timeout_seconds": packet["execution_timeout_seconds"],
    }
    receipt["receipt_sha256"] = _digest(receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    _write_all(receipt_path, canonical_bytes(receipt) + b"\n")
    return receipt


__all__ = ["GATEWAY_SHA256", "SCHEMA", "execute_private_capture"]
