import json
from pathlib import Path

import pytest

from services.operations_gateway import GatewayApproval, canonical_bytes, execution_envelope, resolve_bounded_path, sha256, verify_environment_preflight, verify_scope


SOURCE = "a" * 40


def scope():
    return {"source_sha": SOURCE, "requests": [{"ordinal": 1, "method": "GET", "endpoint": "/stock/financials-reported", "parameters": {"symbol": "NVDA", "freq": "annual"}}]}


def approval(value, operation="plan", calls=1, digest=None):
    digest = digest or sha256(canonical_bytes(value))
    return GatewayApproval.parse({"operation": operation, "source_sha": SOURCE, "scope_sha256": digest, "max_provider_calls": calls, "authorization_token": f"ATLAS_{operation.upper()}:{digest}"})


def test_scope_and_envelope_are_identity_bound(tmp_path: Path):
    value = scope(); path = tmp_path / "scope.json"; path.write_text(json.dumps(value))
    approved = approval(value)
    verified = verify_scope(path, approved)
    envelope = execution_envelope(approval=approved, scope=verified, run_id="42")
    assert envelope["request_count"] == 1
    assert envelope["code_trust_root"] == "REGISTERED_DEFAULT_BRANCH"
    assert envelope["authorization_manifest"]["token_value_exposed"] is False


@pytest.mark.parametrize("mutation", ["digest", "source", "budget", "endpoint", "secret", "nested_secret", "order", "duplicate"])
def test_scope_fails_closed(tmp_path: Path, mutation: str):
    value = scope(); approved = approval(value)
    if mutation == "digest":
        value["extra"] = True
    elif mutation == "source":
        value["source_sha"] = "b" * 40
    elif mutation == "budget":
        approved = approval(value, calls=0)
    elif mutation == "endpoint":
        value["requests"][0]["endpoint"] = "/arbitrary"
        approved = approval(value)
    elif mutation == "secret":
        value["requests"][0]["parameters"]["token"] = "secret"
        approved = approval(value)
    elif mutation == "nested_secret":
        value["requests"][0]["parameters"]["headers"] = {"Authorization": "secret"}
        approved = approval(value)
    elif mutation == "order":
        value["requests"][0]["ordinal"] = 2
        approved = approval(value)
    elif mutation == "duplicate":
        value["requests"].append({**value["requests"][0], "ordinal": 2})
        approved = approval(value, calls=2)
    path = tmp_path / "scope.json"; path.write_text(json.dumps(value))
    with pytest.raises(PermissionError):
        verify_scope(path, approved)


def test_wrong_authorization_token_rejected():
    value = scope(); digest = sha256(canonical_bytes(value))
    with pytest.raises(PermissionError, match="AUTHORIZATION_TOKEN"):
        GatewayApproval.parse({"operation": "acquire", "source_sha": SOURCE, "scope_sha256": digest, "max_provider_calls": 1, "authorization_token": "wrong"})


def test_report_card_readonly_envelope_verifies_nested_self_hashed_plan(tmp_path):
    plan = {"schema_version": "ATLAS_REPORT_CARD_MARKET_EVIDENCE_V1", "source_sha": SOURCE,
            "request_manifest": [
                {"capability": "historical_ohlcv", "ticker": "SPY",
                 "parameters": {"resolution": "D", "from": "2026-10-08", "to": "2026-10-13"}},
                {"capability": "splits", "ticker": "ABBV",
                 "parameters": {"from": "2026-10-08", "to": "2026-10-13"}},
                {"capability": "dividends", "ticker": "ABBV",
                 "parameters": {"from": "2026-10-08", "to": "2026-10-13"}},
            ]}
    digest = sha256(canonical_bytes(plan)); plan["artifact_sha256"] = digest
    envelope = {"schema_version": "ATLAS_REPORT_CARD_PROTECTED_READONLY_V1",
                "source_sha": SOURCE, "canonical_plan": plan,
                "canonical_plan_sha256": digest, "ledger": {"sha256": "evidence"}}
    path = tmp_path / "protected_validation.json"; path.write_text(json.dumps(envelope))
    verified = verify_scope(path, approval(envelope, calls=3, digest=digest))
    assert [row["endpoint"] for row in verified["requests"]] == [
        "/stock/candle", "/stock/split", "/stock/dividend2"]
    assert verified["requests"][0]["parameters"]["symbol"] == "SPY"


def test_report_card_readonly_envelope_rejects_binding_or_content_change(tmp_path):
    plan = {"schema_version": "ATLAS_REPORT_CARD_MARKET_EVIDENCE_V1",
            "source_sha": SOURCE, "request_manifest": []}
    digest = sha256(canonical_bytes(plan)); plan["artifact_sha256"] = digest
    envelope = {"schema_version": "ATLAS_REPORT_CARD_PROTECTED_READONLY_V1",
                "canonical_plan": plan, "canonical_plan_sha256": "0" * 64}
    path = tmp_path / "protected_validation.json"; path.write_text(json.dumps(envelope))
    with pytest.raises(PermissionError, match="GATEWAY_REPORT_CARD_PLAN_BINDING_MISMATCH"):
        verify_scope(path, approval(envelope, calls=0, digest=digest))
    envelope["canonical_plan_sha256"] = digest
    envelope["canonical_plan"]["source_sha"] = "b" * 40
    path.write_text(json.dumps(envelope))
    with pytest.raises(PermissionError, match="GATEWAY_SCOPE_DIGEST_MISMATCH"):
        verify_scope(path, approval(envelope, calls=0, digest=digest))


def test_scope_path_is_bounded_to_download_root(tmp_path):
    root=tmp_path/"download"; root.mkdir(); inside=root/"scope.json"; inside.write_text("{}")
    outside=tmp_path/"outside.json"; outside.write_text("{}")
    assert resolve_bounded_path(root,"scope.json")==inside.resolve()
    with pytest.raises(PermissionError,match="PATH_INVALID"):
        resolve_bounded_path(root,"../outside.json")


def test_environment_preflight_binds_default_branch_exact_code_and_credentials():
    result=verify_environment_preflight(gateway="research",operation="acquire",ref_name="main",
        default_branch="main",checked_out_sha=SOURCE,expected_code_sha=SOURCE,
        credential_present=True,kill_switch_open=True)
    assert result["environment"]=="atlas-licensed-research-acquisition"
    with pytest.raises(PermissionError,match="CODE_TRUST"):
        verify_environment_preflight(gateway="research",operation="acquire",ref_name="feature",
            default_branch="main",checked_out_sha=SOURCE,expected_code_sha=SOURCE,
            credential_present=True,kill_switch_open=True)
    with pytest.raises(PermissionError,match="CREDENTIAL_SCOPE"):
        verify_environment_preflight(gateway="report_card",operation="validate",ref_name="main",
            default_branch="main",checked_out_sha=SOURCE,expected_code_sha=SOURCE,
            credential_present=True,kill_switch_open=False)
