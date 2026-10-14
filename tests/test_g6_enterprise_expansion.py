import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.plan_g6_enterprise_expansion import build_plan, digest, published_tickers, request_key


POLICY = json.loads(Path("config/g6_enterprise_expansion_policy.json").read_text())
GATEWAY = json.loads(Path("config/finnhub_financials_gateway_v1.json").read_text())
STAGE0 = json.loads(Path("output/joint/r2_reconciliation/g6_stage0_approval.json").read_text())
STAGE0_SHA = "3ca088a01a2fb220d08761df764ccacc3d605a217e510d599905864df0f3ea2b"


def records():
    stage0 = [row["ticker"] for row in STAGE0["manifest"]["requests"]]
    tickers = stage0 + [f"X{i:04d}" for i in range(1298 - len(stage0))]
    return [{"ticker": t, "publication_certification": {
        "ticker": t, "customer_publication_allowed": True}} for t in tickers]


def plan():
    tickers = published_tickers(records())
    policy = copy.deepcopy(POLICY)
    policy["published_scope"]["ticker_scope_sha256"] = digest(tickers)
    return build_plan(tickers, policy, GATEWAY, STAGE0, scope_sha256="a" * 64)


def test_stage0_package_remains_exact_and_separately_authorized():
    assert STAGE0["manifest_sha256"] == STAGE0_SHA
    assert STAGE0["authorization_token"] == f"AUTHORIZE_G6_STAGE0:{STAGE0_SHA}"
    result = plan()
    assert result["authorization_note"].startswith("Stage 0 authorization does not authorize")
    assert all(not b["required_authorization_token"].startswith("AUTHORIZE_G6_STAGE0") for b in result["batches"])


def test_exact_1298_scope_is_deduplicated_against_stage0_and_batched():
    result = plan()
    assert result["provider_calls_performed"] == 0
    assert result["coverage"] == {
        "target_symbol_frequency_pairs": 2596,
        "stage0_pairs_deduplicated": 11,
        "expansion_request_count": 2585,
        "frequencies": ["annual", "quarterly"]
    }
    assert result["batch_count"] == 52
    assert [len(b["manifest"]["requests"]) for b in result["batches"][:-1]] == [50] * 51
    assert len(result["batches"][-1]["manifest"]["requests"]) == 35
    keys = [request_key(r) for b in result["batches"] for r in b["manifest"]["requests"]]
    assert len(keys) == len(set(keys)) == 2585


def test_manifests_and_tokens_are_deterministic_and_hash_bound():
    first, second = plan(), plan()
    assert first == second
    for batch in first["batches"]:
        assert batch["manifest_sha256"] == digest(batch["manifest"])
        assert batch["required_authorization_token"].endswith(batch["manifest_sha256"])
        assert batch["manifest"]["state"] == "AWAITING_EXACT_OWNER_AUTHORIZATION"


def test_scope_and_gateway_drift_fail_closed():
    with pytest.raises(ValueError, match="COUNT_MISMATCH"):
        build_plan(["A"], POLICY, GATEWAY, STAGE0, scope_sha256="a" * 64)
    bad = copy.deepcopy(GATEWAY); bad["pacing"]["retry_count"] = 1
    policy = copy.deepcopy(POLICY)
    policy["published_scope"]["ticker_scope_sha256"] = digest(published_tickers(records()))
    with pytest.raises(ValueError, match="PACING_DRIFT"):
        build_plan(published_tickers(records()), policy, bad, STAGE0, scope_sha256="a" * 64)


def test_published_scope_rejects_duplicate_or_mismatched_identity():
    row = {"ticker": "A", "publication_certification": {"ticker": "B", "customer_publication_allowed": True}}
    with pytest.raises(ValueError, match="IDENTITY_INVALID"):
        published_tickers([row])
    good = {"ticker": "A", "publication_certification": {"ticker": "A", "customer_publication_allowed": True}}
    with pytest.raises(ValueError, match="DUPLICATE"):
        published_tickers([good, good])


def test_gateway_contract_has_permanent_safe_execution_controls():
    assert GATEWAY["pacing"] == {"concurrency": 1, "minimum_inter_request_seconds": 1.0,
                                  "rate_limit_rpm": 60, "retry_count": 0}
    assert GATEWAY["raw_persistence"]["required_before_inspection"] is True
    assert set(GATEWAY["allowed_frequencies"]) == {"annual", "quarterly"}
    assert {"ENTITLEMENT_OR_AUTH_HTTP_FAILURE", "RAW_PERSISTENCE_FAILURE",
            "RATE_LIMIT_EXHAUSTED", "REQUEST_SCOPE_DRIFT"} <= set(GATEWAY["stop_conditions"])
