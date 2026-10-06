"""Fail-closed throughput governance for parallel Finnhub certification shards."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable


RATE_CONTRACT_VERSION = "ATLAS_FINNHUB_GLOBAL_RATE_CONTRACT_V1"


@dataclass(frozen=True)
class FinnhubRateContract:
    global_requests_per_minute: float
    parallel_workers: int
    worker_slot: int
    max_in_flight_per_worker: int = 1

    def __post_init__(self) -> None:
        if self.global_requests_per_minute <= 0:
            raise ValueError("Finnhub global requests-per-minute must be positive")
        if self.parallel_workers < 1:
            raise ValueError("Finnhub parallel worker count must be positive")
        if not 0 <= self.worker_slot < self.parallel_workers:
            raise ValueError("Finnhub worker slot is outside the configured worker count")
        if self.max_in_flight_per_worker != 1:
            raise ValueError("Finnhub certification permits exactly one in-flight request per worker")

    @property
    def per_worker_requests_per_minute(self) -> float:
        return self.global_requests_per_minute / self.parallel_workers

    @property
    def minimum_interval_seconds(self) -> float:
        return 60.0 / self.per_worker_requests_per_minute

    @property
    def aggregate_burst_limit(self) -> int:
        # Matrix jobs cannot share a process-local token bucket. One in-flight
        # request per worker is therefore the explicit conservative burst cap.
        return self.parallel_workers

    def as_dict(self) -> dict[str, object]:
        return {
            "version": RATE_CONTRACT_VERSION,
            "global_requests_per_minute": self.global_requests_per_minute,
            "parallel_workers": self.parallel_workers,
            "worker_slot": self.worker_slot,
            "per_worker_requests_per_minute": self.per_worker_requests_per_minute,
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "max_in_flight_per_worker": self.max_in_flight_per_worker,
            "aggregate_burst_limit": self.aggregate_burst_limit,
        }


class FinnhubRateGovernor:
    """Process-local share of a globally partitioned Finnhub allowance."""

    def __init__(
        self,
        contract: FinnhubRateContract,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.contract = contract
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_started: float | None = None
        self.wait_seconds = 0.0

    def before_request(self) -> float:
        now = self._monotonic()
        waited = 0.0
        if self._last_started is not None:
            remaining = self.contract.minimum_interval_seconds - (now - self._last_started)
            if remaining > 0:
                self._sleep(remaining)
                waited = remaining
                now = self._monotonic()
        self._last_started = now
        self.wait_seconds += waited
        return waited

    def retry_delay(self, seconds: float) -> None:
        delay = max(0.0, float(seconds))
        if delay:
            self._sleep(delay)
            self.wait_seconds += delay


def build_parallel_rate_governor(
    *, global_requests_per_minute: float | None, parallel_workers: int, shard_index: int,
) -> FinnhubRateGovernor | None:
    """Build governed parallel pacing; retain legacy pacing for one worker."""
    if parallel_workers == 1 and global_requests_per_minute is None:
        return None
    if global_requests_per_minute is None:
        raise ValueError("parallel Finnhub acquisition requires an explicit global requests-per-minute allowance")
    contract = FinnhubRateContract(
        global_requests_per_minute=global_requests_per_minute,
        parallel_workers=parallel_workers,
        worker_slot=shard_index % parallel_workers,
    )
    return FinnhubRateGovernor(contract)


__all__ = [
    "RATE_CONTRACT_VERSION", "FinnhubRateContract", "FinnhubRateGovernor",
    "build_parallel_rate_governor",
]
