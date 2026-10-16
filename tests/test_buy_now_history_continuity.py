import pytest

from services.buy_now_history_continuity import (
    build_history_backfill_plan, validate_backfill_observation_set,
)
from services.finnhub_incremental_post_close import _digest


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
        "/stock/candle", "/stock/split", "/stock/dividend2",
    ]
    assert len(plan["request_keys"]) == len(set(plan["request_keys"]))


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
