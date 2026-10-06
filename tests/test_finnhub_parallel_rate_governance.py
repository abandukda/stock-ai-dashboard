from pathlib import Path

import pytest
from services.finnhub_rate_governance import (
    FinnhubRateContract, FinnhubRateGovernor, build_parallel_rate_governor,
)
from services.finnhub_shadow_provider import FinnhubShadowAdapter


class Clock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


def test_parallel_rate_contract_partitions_global_allowance_conservatively():
    contract = FinnhubRateContract(
        global_requests_per_minute=600, parallel_workers=5, worker_slot=3,
    )
    assert contract.per_worker_requests_per_minute == 120
    assert contract.minimum_interval_seconds == 0.5
    assert contract.aggregate_burst_limit == 5
    assert contract.max_in_flight_per_worker == 1


def test_parallel_rate_governor_paces_every_request_and_retry_delay():
    clock = Clock()
    governor = FinnhubRateGovernor(
        FinnhubRateContract(600, 5, 0), monotonic=clock.monotonic, sleep=clock.sleep,
    )
    assert governor.before_request() == 0
    assert governor.before_request() == 0.5
    governor.retry_delay(2.25)
    assert clock.sleeps == [0.5, 2.25]
    assert governor.wait_seconds == 2.75


def test_parallel_mode_fails_closed_without_explicit_global_allowance():
    with pytest.raises(ValueError, match="explicit global requests-per-minute"):
        build_parallel_rate_governor(
            global_requests_per_minute=None, parallel_workers=5, shard_index=0,
        )
    assert build_parallel_rate_governor(
        global_requests_per_minute=None, parallel_workers=1, shard_index=0,
    ) is None


def test_worker_slot_is_deterministic_for_all_41_shards():
    slots = [build_parallel_rate_governor(
        global_requests_per_minute=600, parallel_workers=5, shard_index=index,
    ).contract.worker_slot for index in range(41)]
    assert slots == [index % 5 for index in range(41)]
    assert set(slots) == set(range(5))


def test_workflow_exposes_opt_in_five_worker_contract_without_activating_schedule():
    path = Path(".github/workflows/atlas_finnhub_full_universe_certification.yml")
    source = path.read_text(encoding="utf-8")
    assert 'default: "5"' in source
    assert 'options: ["5"]' in source
    assert "ATLAS_FINNHUB_GLOBAL_REQUESTS_PER_MINUTE" in source
    assert source.count("GOVERNED_GLOBAL_RPM") >= 4
    assert "inputs.parallel_workers || '2'" in source
    # The five existing schedules remain byte-for-byte represented; 18:30 ET
    # activation is intentionally deferred until a complete governed pass.
    assert source.count("- cron:") == 5


def test_finnhub_429_preserves_retry_after_for_governed_backoff():
    class Response:
        status_code = 429
        headers = {"Retry-After": "7"}

        @staticmethod
        def json():
            return {}

    record = FinnhubShadowAdapter(
        "key", get=lambda *_args, **_kwargs: Response(),
    ).fetch("company_profile", "NVDA").as_dict()
    assert record["payload"]["reason"] == "HTTP_429"
    assert record["payload"]["retry_after_seconds"] == 7.0
