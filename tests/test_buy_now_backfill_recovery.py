import json
from pathlib import Path

from scripts.prepare_buy_now_backfill_recovery import build_recovery
from services.buy_now_history_backfill_execution import atomic_json, digest, file_sha256
from tests.test_buy_now_history_continuity import _plan


def test_recovery_package_contains_only_never_attempted_requests(tmp_path: Path):
    plan = _plan()
    failed = plan["requests"][2847]
    failed["ticker"] = "QRVO"
    failed["parameters"]["symbol"] = "QRVO"
    plan["plan_sha256"] = "a" * 64
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"backfill_plan": plan}))
    claim_id = "original"
    scope_sha = "f" * 64
    claim = tmp_path / "state/history_backfill_claims/original"
    raw = tmp_path / "raw/history_backfill/original"
    atomic_json(claim / "claim.json", {"scope": {"claim_id": claim_id,
        "claim_scope_sha256": scope_sha, "plan_sha256": plan["plan_sha256"]},
        "state": "CONSUMED", "execution_id": "live"})
    for request in plan["requests"][:2848]:
        ordinal = request["ordinal"]
        atomic_json(claim / "intents" / f"{ordinal:05d}.json",
                    {"request_sha256": digest(request)})
        body = b'{"s":"no_data"}' if ordinal == 2848 else b'[]'
        import base64, hashlib
        envelope = {"request_sha256": digest(request), "status_code": 200,
                    "headers": {}, "body_base64": base64.b64encode(body).decode(),
                    "body_sha256": hashlib.sha256(body).hexdigest()}
        atomic_json(raw / f"{ordinal:05d}.json", envelope)
        if ordinal < 2848:
            atomic_json(claim / "receipts" / f"{ordinal:05d}.json",
                        {"request_sha256": digest(request),
                         "envelope_sha256": file_sha256(raw / f"{ordinal:05d}.json")})
    result = build_recovery(package=package, state_root=tmp_path/"state",
        raw_root=tmp_path/"raw", claim_id=claim_id,
        claim_scope_sha256=scope_sha, registered_source_sha="b"*40,
        recovery_claim_id="recovery-01")
    assert result["status"] == "PROVIDER_FREE_RECOVERY_VERIFIED"
    recovery = result["recovery_plan"]
    assert recovery["request_count"] == recovery["absolute_request_ceiling"] == 1046
    assert recovery["preserved_completed_receipts"] == 2847
    assert recovery["preserved_terminal_unavailable"][0]["ticker"] == "QRVO"
    assert recovery["requests"][0]["ordinal"] == 2849
    assert recovery["requests"][-1]["ordinal"] == 3894
    assert result["provider_calls"] == result["publication_writes"] == 0
    assert result["authorization_status"] == "OWNER_APPROVAL_REQUIRED_NOT_CONSUMED"
