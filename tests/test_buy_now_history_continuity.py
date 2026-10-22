import pytest
import json

from services.buy_now_history_continuity import (
    build_history_backfill_plan, validate_backfill_observation_set,
)
from services.finnhub_incremental_post_close import _digest
from services.operations_gateway import GatewayApproval, canonical_bytes, sha256, verify_scope
from scripts.plan_buy_now_history_backfill import membership_from_incremental_plan


def _plan(count=1298):
    symbols = [f"S{i:04d}" for i in range(count)]
    return build_history_backfill_plan(
        source_sha="a" * 40,
        symbols=symbols,
        missing_sessions=["2026-10-05", "2026-10-06"],
        membership_identity={
            "membership_count": count,
            "membership_sha256": _digest(symbols),
            "source_run_id": "37216506983",
        },
        retained_history_identity={
            "last_contiguous_session": "2026-10-02",
            "artifact_set_sha256": "b" * 64,
        },
    )


def test_backfill_plan_is_range_deduplicated_bounded_and_provider_free():
    plan = _plan()
    assert plan["request_count"] == plan["absolute_request_ceiling"] == 3894
    assert plan["provider_calls"] == plan["publication_writes"] == 0
    assert plan["automatic_retries"] == 0
    assert plan["range_start"] == "2026-10-05"
    assert plan["range_end"] == "2026-10-06"
    assert plan["endpoint_allowlist"] == [
        "/stock/candle", "/stock/split", "/stock/dividend",
    ]
    assert len(plan["request_keys"]) == len(set(plan["request_keys"]))
    assert len(plan["requests"]) == 3894
    assert [row["ordinal"] for row in plan["requests"]] == list(range(1, 3895))
    candle = next(row for row in plan["requests"] if row["capability"] == "historical_ohlcv")
    assert isinstance(candle["parameters"]["from"], int)
    assert isinstance(candle["parameters"]["to"], int)
    assert candle["parameters"]["resolution"] == "D"
    action = next(row for row in plan["requests"] if row["capability"] == "splits")
    assert action["parameters"]["from"] == "2026-10-05"
    assert plan["execution_policy"] == {
        "concurrency": 1, "rate_limit_rpm": 60, "retry_count": 0,
        "raw_persistence_before_inspection": True, "stop_on_http_429": True,
        "stop_on_entitlement_error": True, "stop_on_schema_error": True,
    }


def test_backfill_plan_is_accepted_by_registered_gateway_contract(tmp_path):
    plan = _plan()
    path = tmp_path / "backfill.json"
    path.write_text(__import__("json").dumps(plan, sort_keys=True, separators=(",", ":")))
    scope_sha = sha256(canonical_bytes(plan))
    approval = GatewayApproval.parse({
        "operation": "plan", "source_sha": "a" * 40,
        "scope_sha256": scope_sha, "max_provider_calls": 3894,
        "authorization_token": f"ATLAS_PLAN:{scope_sha}",
    })
    assert len(verify_scope(path, approval)["requests"]) == 3894


def test_backfill_plan_rejects_overlap_and_identity_mismatch():
    symbols = [f"S{i:04d}" for i in range(1298)]
    common = dict(
        source_sha="a" * 40, symbols=symbols,
        missing_sessions=["2026-10-05"],
        membership_identity={"membership_count": 1298, "membership_sha256": _digest(symbols)},
    )
    with pytest.raises(ValueError, match="OVERLAPS"):
        build_history_backfill_plan(
            **common, retained_history_identity={
                "last_contiguous_session": "2026-10-05", "artifact_set_sha256": "b" * 64,
            },
        )
    with pytest.raises(ValueError, match="MEMBERSHIP_DIGEST"):
        build_history_backfill_plan(
            **{**common, "membership_identity": {"membership_count": 1298, "membership_sha256": "c" * 64}},
            retained_history_identity={
                "last_contiguous_session": "2026-10-02", "artifact_set_sha256": "b" * 64,
            },
        )


def test_backfill_validation_requires_exact_sessions_ohlcv_lineage_and_actions():
    plan = _plan()
    tickers = sorted({key.split(":", 1)[0] for key in plan["request_keys"]})
    observations = {
        ticker: [
            {
                "session": session, "open": 1, "high": 2, "low": .5, "close": 1.5,
                "volume": 100, "raw_response_sha256": "d" * 64,
                "corporate_action_status": "NONE",
            }
            for session in plan["missing_sessions"]
        ]
        for ticker in tickers
    }
    result = validate_backfill_observation_set(plan=plan, observations=observations)
    assert result["observation_count"] == 1298 * 2
    assert result["provider_calls"] == result["publication_writes"] == 0
    observations["S0000"] = list(reversed(observations["S0000"]))
    with pytest.raises(ValueError, match="SESSION_SEQUENCE"):
        validate_backfill_observation_set(plan=plan, observations=observations)


def test_small_governed_incremental_plan_recovers_exact_membership(tmp_path):
    symbols = [f"S{i:04d}" for i in range(1298)]
    from services.finnhub_incremental_post_close import build_incremental_plan
    plan = build_incremental_plan(
        session="2026-10-15", customer_symbols=symbols,
        governed_membership={
            "membership_count": 1298, "membership_sha256": _digest(symbols),
            "source_run_id": "37216506983",
            "tickers": symbols,
        },
    )
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    recovered = membership_from_incremental_plan(path)
    assert recovered["tickers"] == symbols
    assert recovered["membership_sha256"] == _digest(symbols)
    plan["request_keys"] = plan["request_keys"][:-1]
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="SOURCE_PLAN_INVALID"):
        membership_from_incremental_plan(path)


@pytest.mark.parametrize("change", [
    {"raw_response_sha256": "not-a-digest"},
    {"raw_response_sha256": "z" * 64},
    {"corporate_action_status": "UNKNOWN"},
    {"corporate_action_status": True},
])
def test_certification_rejects_unverified_lineage_and_action_states(change):
    plan = {"missing_sessions": ["2026-10-06"], "request_keys": ["AAA:historical_ohlcv:x"]}
    row = {"session": "2026-10-06", "open": 1, "high": 2, "low": 1,
           "close": 2, "volume": 0, "raw_response_sha256": "a" * 64,
           "corporate_action_status": "NONE", **change}
    with pytest.raises(ValueError, match="LINEAGE_INCOMPLETE"):
        validate_backfill_observation_set(plan=plan, observations={"AAA": [row]})


def test_certification_accepts_valid_zero_volume_and_equal_price_bounds():
    plan = {"missing_sessions": ["2026-10-06"], "request_keys": ["AAA:historical_ohlcv:x"]}
    row = {"session": "2026-10-06", "open": 1, "high": 1, "low": 1,
           "close": 1, "volume": 0, "raw_response_sha256": "a" * 64,
           "corporate_action_status": "NONE"}
    assert validate_backfill_observation_set(plan=plan, observations={"AAA": [row]})["status"] == "COMPLETE"
