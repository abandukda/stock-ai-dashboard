"""Fail-closed, provider-free binding for a source-current G2 decision package."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from services.report_card_operational_controls import digest


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_RE = re.compile(r"^[0-9a-f]{40}$")


def _require_sha(value: object, *, source: bool = False) -> str:
    text = str(value or "")
    if not (SOURCE_RE if source else SHA256_RE).fullmatch(text):
        raise PermissionError("G2_RELEASE_IDENTITY_INVALID")
    return text


def build_g2_release_binding(*, protected_validation: Mapping[str, Any],
                             entitlement: Mapping[str, Any], release_source_sha: str,
                             validation_run_id: str, validation_artifact: str) -> dict[str, Any]:
    """Bind current protected facts without granting acquisition authority.

    The returned document is deliberately a decision package, not an executable
    token. A fresh owner authorization must quote its package digest.
    """
    source = _require_sha(release_source_sha, source=True)
    if protected_validation.get("schema_version") != "ATLAS_REPORT_CARD_PROTECTED_READONLY_V1":
        raise PermissionError("G2_PROTECTED_VALIDATION_SCHEMA_INVALID")
    if protected_validation.get("source_sha") != source:
        raise PermissionError("G2_RELEASE_SOURCE_MISMATCH")
    if protected_validation.get("provider_calls") != 0 or protected_validation.get("ledger_mutations") != 0:
        raise PermissionError("G2_PROVIDER_FREE_INVARIANT_FAILED")
    sentinel = protected_validation.get("kill_switch_evidence", {})
    if not (sentinel.get("state") == "CLOSED" and sentinel.get("mode") == "0o600"
            and sentinel.get("owner") == "atlasrunner" and sentinel.get("safe_for_live_calls") is False):
        raise PermissionError("G2_CLOSED_SENTINEL_PROOF_INVALID")
    mounts = protected_validation.get("mounts", {})
    if mounts.get("isolated") is not True:
        raise PermissionError("G2_STORAGE_ISOLATION_UNPROVEN")
    ledger = protected_validation.get("ledger", {})
    ledger_sha = _require_sha(ledger.get("sha256"))
    backups = protected_validation.get("backup_root", {}).get("verified_backups", [])
    if not backups:
        raise PermissionError("G2_INDEPENDENT_BACKUP_UNPROVEN")
    backup_hashes = sorted({_require_sha(row.get("sha256")) for row in backups})
    plan = protected_validation.get("canonical_plan", {})
    plan_sha = _require_sha(protected_validation.get("canonical_plan_sha256"))
    if plan.get("artifact_sha256") != plan_sha:
        raise PermissionError("G2_CANONICAL_PLAN_BINDING_INVALID")
    if int(protected_validation.get("planned_calls", -1)) != 61:
        raise PermissionError("G2_CALL_BUDGET_NOT_61")
    if len(protected_validation.get("due_tickers", [])) != 20:
        raise PermissionError("G2_DUE_TICKER_SCOPE_NOT_20")
    entitlement_sha = digest(dict(entitlement))
    _require_sha(entitlement_sha)
    if entitlement.get("status") != "APPROVED":
        raise PermissionError("G2_ENTITLEMENT_NOT_APPROVED")
    required = {"historical_ohlcv", "splits", "dividends"}
    if not required.issubset(set(entitlement.get("capabilities", []))):
        raise PermissionError("G2_ENTITLEMENT_CAPABILITY_MISSING")
    result = {
        "schema_version": "atlas.report-card.g2-release-binding.v1",
        "status": "OWNER_AUTHORIZATION_REQUIRED_NOT_EXECUTABLE",
        "release_source_sha": source,
        "validation_run_id": str(validation_run_id),
        "validation_artifact": str(validation_artifact),
        "protected_validation_package_sha256": _require_sha(protected_validation.get("package_sha256")),
        "canonical_plan_sha256": plan_sha,
        "entitlement_sha256": entitlement_sha,
        "ledger_identity": {"sha256": ledger_sha, "tip": ledger.get("tip")},
        "independent_backup_sha256": backup_hashes,
        "sentinel": {"state": "CLOSED", "mode": "0600", "owner": "atlasrunner"},
        "scope": {"due_ticker_count": 20, "benchmark": "SPY", "maximum_provider_calls": 61,
                  "automatic_retries": 0, "ledger_writes": 0, "customer_publication": False},
        "authorization_contract": {
            "required_token_prefix": "REPORT_CARD_ACQUIRE_ONCE",
            "one_time_claim_required": True,
            "token_issued": False,
            "sentinel_transition": "CLOSED_TO_OPEN_TO_CLOSED_AT_EXECUTION_ONLY",
        },
    }
    result["package_sha256"] = digest(result)
    return result


def monitoring_configuration_preflight(*, owner_email: str, cronitor_url: str) -> dict[str, Any]:
    """Validate configuration identity without sending telemetry or retaining secrets."""
    from services.release_operational_closure import EMAIL_RE
    from services.operational_heartbeat import CronitorHeartbeatAdapter

    if not EMAIL_RE.fullmatch(owner_email or ""):
        raise RuntimeError("RELEASE_MONITOR_OWNER_EMAIL_MISSING_OR_INVALID")
    CronitorHeartbeatAdapter(cronitor_url)  # validates HTTPS host/path only; no I/O
    result = {
        "schema_version": "atlas.monitoring.configuration-preflight.v1",
        "status": "CONFIGURED_DELIVERY_NOT_PROVEN",
        "owner_email_sha256": hashlib.sha256(owner_email.lower().encode()).hexdigest(),
        "cronitor_destination_sha256": hashlib.sha256(cronitor_url.encode()).hexdigest(),
        "network_request_performed": False,
        "delivery_proven": False,
        "required_delivery_proofs": ["SUCCESS", "FAILURE", "MISSED_HEARTBEAT"],
    }
    result["result_sha256"] = digest(result)
    return result


__all__ = ["build_g2_release_binding", "monitoring_configuration_preflight"]
