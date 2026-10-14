import pytest

from services.finnhub_rate_governance import FinnhubRateContract, FinnhubRateGovernor, build_parallel_rate_governor


def test_two_workers_partition_exact_500_rpm_contract():
    contract = FinnhubRateContract(global_requests_per_minute=500, parallel_workers=2, worker_slot=0)
    assert contract.per_worker_requests_per_minute == 250
    assert contract.minimum_interval_seconds == pytest.approx(0.24)
    assert contract.aggregate_burst_limit == 2


def test_fake_clock_proves_spacing_and_retry_wait_accounting():
    clock = {"now": 0.0}
    def monotonic(): return clock["now"]
    def sleep(seconds): clock.__setitem__("now", clock["now"] + seconds)
    governor = FinnhubRateGovernor(
        FinnhubRateContract(global_requests_per_minute=120, parallel_workers=2, worker_slot=0),
        monotonic=monotonic, sleep=sleep,
    )
    governor.before_request()
    governor.before_request()
    governor.retry_delay(2)
    assert governor.wait_seconds == pytest.approx(3)
    assert governor.peak_requests_per_second == 1


def test_parallel_acquisition_without_explicit_rpm_fails_closed():
    with pytest.raises(ValueError, match="explicit global"):
        build_parallel_rate_governor(global_requests_per_minute=None, parallel_workers=2, shard_index=0)


def test_invalid_burst_ceiling_is_rejected():
    with pytest.raises(ValueError):
        FinnhubRateContract(global_requests_per_minute=500, parallel_workers=2, worker_slot=0,
                            global_requests_per_second_ceiling=30)


def test_executor_has_independent_total_attempt_ceiling():
    source = open("services/finnhub_full_universe_executor.py", encoding="utf-8").read()
    assert "maximum_http_attempts" in source
    assert "PROVIDER_HTTP_ATTEMPT_CEILING_EXCEEDED" in source
    assert '"attempt_ceiling_status"' in source
