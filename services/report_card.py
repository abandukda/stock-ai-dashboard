"""Inactive immutable ATLAS Report Card foundation.

Only explicitly eligible future prospective signals may enter this ledger.
Historical artifacts are never auto-imported. Public performance publication is
outside this contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping, Sequence

VERSION = "ATLAS_REPORT_CARD_V1"
HORIZONS = (1, 5, 21, 63, 126, 252)
BENCHMARK = "SPY"
ELIGIBILITY_STATES = (
    "LIVE_PROSPECTIVE_SIGNAL", "VALID_IMMUTABLE_PRELAUNCH_SIGNAL",
    "BACKTEST_ONLY", "INSUFFICIENT_EVIDENCE",
)
PROSPECTIVE_ELIGIBLE = {"LIVE_PROSPECTIVE_SIGNAL", "VALID_IMMUTABLE_PRELAUNCH_SIGNAL"}
REPORT_CLASSIFICATION = "INTERNAL METHODOLOGY VALIDATION — NOT CUSTOMER-FACING PERFORMANCE ADVERTISING"


def _utc(value: Any, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_TIMESTAMP_INVALID") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field}_TIMESTAMP_TIMEZONE_REQUIRED")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class SignalRecord:
    signal_id: str
    ticker: str
    canonical_action: str
    presentation_label_at_issuance: str
    publication_timestamp: str
    executable_reference_timestamp: str
    certified_reference_price: float
    fair_value: float | None
    expected_potential: float | None
    opportunity: float | None
    decision_confidence: float | None
    six_pillars: Mapping[str, Any]
    evidence_completeness: Any
    valuation_methods: tuple[str, ...]
    market_regime: str | None
    sector: str | None
    industry: str | None
    methodology_version: str
    provider_authority_version: str
    candidate_digest: str
    evidence_ids: tuple[str, ...]
    eligibility_state: str
    benchmark: str = BENCHMARK
    cohort_id: str = ""


@dataclass(frozen=True)
class ObservationRecord:
    signal_id: str
    horizon_trading_days: int
    observation_timestamp: str
    stock_return: float | None
    benchmark_return: float | None
    excess_return: float | None
    current_price: float | None
    maximum_favorable_excursion: float | None
    maximum_adverse_excursion: float | None
    maximum_drawdown: float | None
    fair_value_reached: bool | None
    current_canonical_action: str | None
    evidence_provenance: Mapping[str, Any]
    benchmark: str = BENCHMARK
    corporate_action_status: str = "NO_GOVERNED_ADJUSTMENT_REPORTED"
    data_status: str = "AVAILABLE"


def build_signal_record(payload: Mapping[str, Any], *, activation_authorized: bool = False) -> SignalRecord:
    """Create a signal only with explicit prospective activation and immutable proof."""
    state = str(payload.get("eligibility_state") or "INSUFFICIENT_EVIDENCE")
    if state not in ELIGIBILITY_STATES:
        raise ValueError("INVALID_ELIGIBILITY_STATE")
    if state in PROSPECTIVE_ELIGIBLE and not activation_authorized:
        raise PermissionError("PROSPECTIVE_REPORT_CARD_NOT_ACTIVATED")
    required = ("ticker", "canonical_action", "publication_timestamp", "executable_reference_timestamp",
                "certified_reference_price", "methodology_version", "provider_authority_version", "candidate_digest")
    missing = [key for key in required if payload.get(key) in (None, "")]
    if missing:
        raise ValueError("MISSING_SIGNAL_FIELDS:" + ",".join(missing))
    publication = _utc(payload["publication_timestamp"], "PUBLICATION")
    executable = _utc(payload["executable_reference_timestamp"], "EXECUTABLE_REFERENCE")
    if executable < publication:
        raise ValueError("EXECUTABLE_REFERENCE_PRECEDES_PUBLICATION")
    methodology = str(payload["methodology_version"])
    identity = {
        "ticker": str(payload["ticker"]).upper(), "canonical_action": str(payload["canonical_action"]),
        "publication_timestamp": publication.isoformat(), "candidate_digest": str(payload["candidate_digest"]),
        "methodology_version": methodology, "provider_authority_version": str(payload["provider_authority_version"]),
    }
    signal_id = str(payload.get("signal_id") or hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest())
    return SignalRecord(
        signal_id=signal_id, ticker=identity["ticker"], canonical_action=identity["canonical_action"],
        presentation_label_at_issuance=str(payload.get("presentation_label_at_issuance") or identity["canonical_action"]),
        publication_timestamp=publication.isoformat(), executable_reference_timestamp=executable.isoformat(),
        certified_reference_price=float(payload["certified_reference_price"]),
        fair_value=payload.get("fair_value"), expected_potential=payload.get("expected_potential"),
        opportunity=payload.get("opportunity"), decision_confidence=payload.get("decision_confidence"),
        six_pillars=dict(payload.get("six_pillars") or {}), evidence_completeness=payload.get("evidence_completeness"),
        valuation_methods=tuple(payload.get("valuation_methods") or ()), market_regime=payload.get("market_regime"),
        sector=payload.get("sector"), industry=payload.get("industry"), methodology_version=methodology,
        provider_authority_version=identity["provider_authority_version"], candidate_digest=identity["candidate_digest"],
        evidence_ids=tuple(str(x) for x in payload.get("evidence_ids", ()) if x), eligibility_state=state,
        cohort_id=str(payload.get("cohort_id") or f"{methodology}:{identity['provider_authority_version']}"),
    )


def append_signal(path: Path, signal: SignalRecord) -> bool:
    """Append once; any attempt to rewrite an existing identity fails closed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            item = json.loads(line); current[str(item["signal_id"])] = item
    payload = asdict(signal)
    existing = current.get(signal.signal_id)
    if existing is not None:
        # JSON round-tripping represents immutable tuples as arrays; compare
        # canonical serialized values rather than Python container types.
        if json.dumps(existing, sort_keys=True) != json.dumps(payload, sort_keys=True):
            raise ValueError("IMMUTABLE_SIGNAL_CONFLICT")
        return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return True


def build_observation(signal: SignalRecord, *, horizon: int, stock_bars: Sequence[Mapping[str, Any]],
                      benchmark_bars: Sequence[Mapping[str, Any]], current_canonical_action: str | None,
                      evidence_provenance: Mapping[str, Any]) -> ObservationRecord:
    if horizon not in HORIZONS:
        raise ValueError("UNREGISTERED_REPORT_CARD_HORIZON")
    start = _utc(signal.executable_reference_timestamp, "EXECUTABLE_REFERENCE")
    def eligible(rows: Sequence[Mapping[str, Any]]) -> list[tuple[datetime, float]]:
        output = []
        for row in rows:
            timestamp = _utc(row.get("timestamp"), "OUTCOME")
            if timestamp <= start:  # same-time and pre-decision observations are forbidden
                continue
            try: output.append((timestamp, float(row["close"])))
            except (KeyError, TypeError, ValueError): continue
        return sorted(output)
    stock = eligible(stock_bars)
    benchmark_all = []
    for row in benchmark_bars:
        timestamp = _utc(row.get("timestamp"), "BENCHMARK")
        try: benchmark_all.append((timestamp, float(row["close"])))
        except (KeyError, TypeError, ValueError): continue
    benchmark_reference = next((item for item in reversed(sorted(benchmark_all)) if item[0] <= start), None)
    benchmark = [item for item in sorted(benchmark_all) if item[0] > start]
    if len(stock) < horizon:
        return ObservationRecord(signal.signal_id, horizon, datetime.now(timezone.utc).isoformat(), None, None, None,
                                 None, None, None, None, None, current_canonical_action,
                                 dict(evidence_provenance), data_status="FUTURE_DATA_UNAVAILABLE")
    stock_window = stock[:horizon]
    end = stock_window[-1][0]
    benchmark_window = [(timestamp, price) for timestamp, price in benchmark if timestamp <= end]
    if benchmark_reference is None or len(benchmark_window) < horizon or benchmark_window[horizon - 1][0] != end:
        raise ValueError("STOCK_BENCHMARK_BOUNDARIES_NOT_ALIGNED")
    prices = [price for _, price in stock_window]
    benchmark_prices = [price for _, price in benchmark_window[:horizon]]
    stock_return = prices[-1] / signal.certified_reference_price - 1
    benchmark_return = benchmark_prices[-1] / benchmark_reference[1] - 1
    peak = signal.certified_reference_price; drawdown = 0.0
    for price in prices:
        peak = max(peak, price); drawdown = min(drawdown, price / peak - 1)
    fair_value_reached = None if signal.fair_value is None else max(prices) >= float(signal.fair_value)
    return ObservationRecord(
        signal.signal_id, horizon, end.isoformat(), stock_return, benchmark_return,
        stock_return - benchmark_return, prices[-1], max(prices) / signal.certified_reference_price - 1,
        min(prices) / signal.certified_reference_price - 1, drawdown, fair_value_reached,
        current_canonical_action, dict(evidence_provenance),
    )


def internal_report(records: Sequence[ObservationRecord], signals: Sequence[SignalRecord]) -> dict[str, Any]:
    prospective = [signal for signal in signals if signal.eligibility_state in PROSPECTIVE_ELIGIBLE]
    eligible_ids = {signal.signal_id for signal in prospective}
    available = [record for record in records if record.signal_id in eligible_ids and record.data_status == "AVAILABLE" and record.stock_return is not None]
    returns = [float(record.stock_return) for record in available]
    excess = [float(record.excess_return) for record in available if record.excess_return is not None]
    return {
        "version": VERSION, "classification": REPORT_CLASSIFICATION, "customer_visible": False,
        "total_signals": len(prospective), "excluded_nonprospective_signals": len(signals) - len(prospective),
        "observed_records": len(available),
        "positive_return_rate": mean(value > 0 for value in returns) if returns else None,
        "benchmark_outperformance_rate": mean(value > 0 for value in excess) if excess else None,
        "mean_return": mean(returns) if returns else None, "median_return": median(returns) if returns else None,
        "mean_excess_return": mean(excess) if excess else None, "median_excess_return": median(excess) if excess else None,
        "winner_count": sum(value > 0 for value in returns), "loser_count": sum(value < 0 for value in returns),
        "maximum_drawdown": min((record.maximum_drawdown for record in available if record.maximum_drawdown is not None), default=None),
        "fair_value_hit_rate": mean(record.fair_value_reached for record in available if record.fair_value_reached is not None) if any(record.fair_value_reached is not None for record in available) else None,
        "horizon_breakdown": {str(h): sum(record.horizon_trading_days == h for record in available) for h in HORIZONS},
        "methodology_cohorts": sorted({signal.cohort_id for signal in prospective}),
        "sector_breakdown": {sector: sum(signal.sector == sector for signal in prospective) for sector in sorted({s.sector for s in prospective if s.sector})},
        "market_regime_breakdown": {regime: sum(signal.market_regime == regime for signal in prospective) for regime in sorted({s.market_regime for s in prospective if s.market_regime})},
        "sample_size_warning": "INSUFFICIENT_SAMPLE_FOR_CONCLUSIONS" if len(prospective) < 20 else None,
        "survivorship_policy": "DELISTED_AND_UNAVAILABLE_SECURITIES_RETAINED",
        "time_to_fair_value": "NOT_YET_IMPLEMENTED_REQUIRES_GOVERNED_SESSION_PATH",
    }


__all__ = ["BENCHMARK", "ELIGIBILITY_STATES", "HORIZONS", "ObservationRecord", "REPORT_CLASSIFICATION",
           "SignalRecord", "VERSION", "append_signal", "build_observation", "build_signal_record", "internal_report"]
