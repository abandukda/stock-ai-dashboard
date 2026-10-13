"""Fail-closed contracts shared by ATLAS operational gateways.

The registered default-branch workflow is the trust root.  Candidate SHAs are
identities to validate; they are never used to load code into a job holding
provider or protected-ledger credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
RESEARCH_ENDPOINTS = frozenset(
    {
        "/stock/financials-reported",
        "/stock/financials",
        "/stock/candle",
        "/stock/split",
        "/stock/dividend2",
        "/stock/recommendation",
        "/stock/price-target",
        "/calendar/earnings",
        "/stock/earnings",
        "/company-news",
        "/stock/profile2",
    }
)
OPERATIONS = frozenset({"plan", "acquire", "validate", "append"})
SECRET_KEY_RE = re.compile(r"(?:token|secret|password|api[_-]?key|authorization|credential)", re.I)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def resolve_bounded_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate == root or not candidate.is_relative_to(root) or not candidate.is_file():
        raise PermissionError("GATEWAY_SCOPE_PATH_INVALID")
    return candidate


def _contains_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(SECRET_KEY_RE.search(str(key)) or _contains_secret(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item) for item in value)
    return False


@dataclass(frozen=True)
class GatewayApproval:
    operation: str
    source_sha: str
    scope_sha256: str
    max_provider_calls: int
    authorization_token: str

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "GatewayApproval":
        approval = cls(
            operation=str(value.get("operation") or ""),
            source_sha=str(value.get("source_sha") or ""),
            scope_sha256=str(value.get("scope_sha256") or ""),
            max_provider_calls=int(value.get("max_provider_calls", -1)),
            authorization_token=str(value.get("authorization_token") or ""),
        )
        if approval.operation not in OPERATIONS:
            raise PermissionError("GATEWAY_OPERATION_NOT_ALLOWED")
        if not SHA_RE.fullmatch(approval.source_sha):
            raise PermissionError("GATEWAY_SOURCE_SHA_INVALID")
        if not DIGEST_RE.fullmatch(approval.scope_sha256):
            raise PermissionError("GATEWAY_SCOPE_SHA_INVALID")
        if approval.max_provider_calls < 0:
            raise PermissionError("GATEWAY_CALL_BUDGET_INVALID")
        expected = f"ATLAS_{approval.operation.upper()}:{approval.scope_sha256}"
        if approval.authorization_token != expected:
            raise PermissionError("GATEWAY_AUTHORIZATION_TOKEN_MISMATCH")
        return approval


def verify_scope(path: Path, approval: GatewayApproval) -> dict[str, Any]:
    scope = json.loads(path.read_text(encoding="utf-8"))
    actual = sha256(canonical_bytes(scope))
    if actual != approval.scope_sha256:
        raise PermissionError("GATEWAY_SCOPE_DIGEST_MISMATCH")
    if scope.get("source_sha") != approval.source_sha:
        raise PermissionError("GATEWAY_SCOPE_SOURCE_MISMATCH")
    requests = list(scope.get("requests") or ())
    if len(requests) > approval.max_provider_calls:
        raise PermissionError("GATEWAY_PROVIDER_BUDGET_EXCEEDED")
    ordinals = [row.get("ordinal") for row in requests]
    if ordinals != list(range(1, len(requests) + 1)):
        raise PermissionError("GATEWAY_REQUEST_ORDER_INVALID")
    fingerprints: set[str] = set()
    for row in requests:
        if row.get("method") != "GET" or row.get("endpoint") not in RESEARCH_ENDPOINTS:
            raise PermissionError("GATEWAY_ENDPOINT_NOT_ALLOWED")
        if _contains_secret(row.get("parameters") or {}):
            raise PermissionError("GATEWAY_SCOPE_MUST_NOT_CONTAIN_SECRET")
        fingerprint = sha256(canonical_bytes({"method": row.get("method"), "endpoint": row.get("endpoint"),
                                              "parameters": row.get("parameters") or {}}))
        if fingerprint in fingerprints:
            raise PermissionError("GATEWAY_DUPLICATE_REQUEST")
        fingerprints.add(fingerprint)
    return scope


def execution_envelope(*, approval: GatewayApproval, scope: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    envelope = {
        "contract": "ATLAS_STABLE_OPERATIONS_GATEWAY_V1",
        "operation": approval.operation,
        "source_sha": approval.source_sha,
        "scope_sha256": approval.scope_sha256,
        "max_provider_calls": approval.max_provider_calls,
        "request_count": len(scope.get("requests") or ()),
        "run_id": str(run_id),
        "fail_closed": True,
        "code_trust_root": "REGISTERED_DEFAULT_BRANCH",
    }
    envelope["envelope_sha256"] = sha256(canonical_bytes(envelope))
    return envelope
