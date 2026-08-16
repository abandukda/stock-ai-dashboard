"""Bounded aggregate-only Alpaca calibration runner for manual GitHub Actions.

Credentials and authenticated URLs are never logged. Provider payloads remain
in memory, and only aggregate calibration reports are written.
"""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import statistics
import time
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from analysis.phase8b_calibration.calibration import (
    AssetMetadata, HistoricalDataset, build_calibration_report,
    chronological_split, summarize_events,
)
from services.live_market.models import SecurityType
from services.technical_intelligence.config import TECHNICAL_MODEL_VERSION, TechnicalConfig
from services.technical_intelligence.engine import DailyBar


DATA_BASE = "https://data.alpaca.markets"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_REQUEST_CAP = 80
MAX_RETRIES = 2
BATCH_SIZE = 20
PAGE_LIMIT = 10_000
MIN_REQUEST_INTERVAL_SECONDS = 0.4
WALK_FORWARD_SPLIT = datetime(2022, 1, 1, tzinfo=timezone.utc)


class RequestBudget:
    def __init__(self, cap: int = DEFAULT_REQUEST_CAP) -> None:
        self.cap = min(max(int(cap), 1), DEFAULT_REQUEST_CAP)
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.cap:
            raise RuntimeError("ALPACA_REQUEST_CAP_REACHED")
        self.used += 1


def _request_json(
    path: str,
    params: Mapping[str, Any],
    *,
    key_id: str,
    secret_key: str,
    budget: RequestBudget,
    timeout: float,
    opener=urlopen,
    sleeper=time.sleep,
) -> Mapping[str, Any]:
    """Request JSON without emitting URL, credentials, body, or market values."""
    last_error = "NETWORK_ERROR"
    for attempt in range(MAX_RETRIES + 1):
        budget.consume()
        request = Request(
            f"{DATA_BASE}{path}?{urlencode(dict(params))}",
            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key, "User-Agent": "Atlas-Radar-Calibration/1.0"},
        )
        started = time.monotonic()
        try:
            with opener(request, timeout=timeout) as response:
                raw = response.read()
            payload = json.loads(raw)
            if not isinstance(payload, Mapping):
                raise RuntimeError("NON_OBJECT_RESPONSE")
            remaining = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - started)
            if remaining > 0:
                sleeper(remaining)
            return payload
        except HTTPError as exc:
            last_error = f"HTTP_{int(exc.code)}"
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= MAX_RETRIES:
                break
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = min(10.0, max(1.0, float(retry_after)))
            except (TypeError, ValueError):
                delay = min(8.0, 2.0 ** attempt)
            sleeper(delay)
        except (URLError, TimeoutError, socket.timeout, json.JSONDecodeError):
            if attempt >= MAX_RETRIES:
                break
            sleeper(min(8.0, 2.0 ** attempt))
    raise RuntimeError(last_error)


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _parse_bar(ticker: str, row: Mapping[str, Any]) -> DailyBar:
    return DailyBar(
        ticker=ticker,
        timestamp=datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00")),
        open=float(row["o"]), high=float(row["h"]), low=float(row["l"]),
        close=float(row["c"]), volume=float(row["v"]),
    )


def fetch_daily_bars(
    symbols: Sequence[str],
    *,
    start: str,
    end: str,
    feed: str,
    adjustment: str,
    key_id: str,
    secret_key: str,
    budget: RequestBudget,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    requester=_request_json,
) -> dict[str, list[DailyBar]]:
    output: dict[str, list[DailyBar]] = {symbol: [] for symbol in symbols}
    for batch_number, batch in enumerate(_chunks(tuple(symbols), BATCH_SIZE), 1):
        token = None
        pages = 0
        while True:
            params = {
                "symbols": ",".join(batch), "timeframe": "1Day", "start": start,
                "end": end, "adjustment": adjustment, "feed": feed,
                "sort": "asc", "limit": PAGE_LIMIT,
            }
            if token:
                params["page_token"] = token
            payload = requester(
                "/v2/stocks/bars", params, key_id=key_id, secret_key=secret_key,
                budget=budget, timeout=timeout,
            )
            pages += 1
            bars = payload.get("bars")
            if not isinstance(bars, Mapping):
                raise RuntimeError("MALFORMED_BARS_RESPONSE")
            for ticker in batch:
                rows = bars.get(ticker, [])
                if not isinstance(rows, list):
                    raise RuntimeError("MALFORMED_SYMBOL_BARS")
                output[ticker].extend(_parse_bar(ticker, row) for row in rows if isinstance(row, Mapping))
            next_token = payload.get("next_page_token")
            token = str(next_token) if next_token else None
            if not token:
                break
        print(json.dumps({"kind": "fetch_progress", "batch": batch_number, "batch_size": len(batch), "pages": pages, "requests_used": budget.used}, sort_keys=True))
    return {ticker: rows for ticker, rows in output.items() if rows}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float) and not (value == value and abs(value) != float("inf")):
        return None
    return value


def _write_group_csv(path: Path, groups: Mapping[str, Mapping[str, Any]]) -> None:
    columns = sorted({key for row in groups.values() for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group", *columns])
        writer.writeheader()
        for name, row in sorted(groups.items()):
            writer.writerow({"group": name, **row})


def _threshold_inventory(path: Path) -> None:
    config = TechnicalConfig()
    rows = [
        ("breakout_relative_volume", config.breakout_relative_volume, "1.20|1.40|1.60"),
        ("near_breakout_distance_pct", config.near_breakout_distance_pct, "0.025|0.035|0.050"),
        ("state_score_near", config.state_score_near, "55|58|62"),
        ("state_score_forming", config.state_score_forming, "40|45|50"),
        ("extended_from_pivot_pct", config.extended_from_pivot_pct, "0.10|0.12|0.15"),
        ("extended_atr_from_sma20", config.extended_atr_from_sma20, "2.0|2.5|3.0"),
        ("failed_breakout_buffer_pct", config.failed_breakout_buffer_pct, "0.010|0.015|0.020"),
        ("breakout_confirmation_bars", config.breakout_confirmation_bars, "1|2|3"),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("threshold", "v1_value", "future_ranges", "baseline_status"))
        for name, current, alternatives in rows:
            writer.writerow((name, current, alternatives, "NOT_RUN_BASELINE_ONLY"))


def run() -> int:
    key_id = os.getenv("APCA_API_KEY_ID", "").strip()
    secret_key = os.getenv("APCA_API_SECRET_KEY", "").strip()
    if not key_id or not secret_key:
        print(json.dumps({"kind": "calibration_complete", "status": "MISSING_CREDENTIALS_ZERO_NETWORK_CALLS", "requests_used": 0}))
        return 2
    universe_path = Path(os.getenv("PHASE8C_UNIVERSE", "analysis/phase8b_calibration/universe_v1.json"))
    universe = json.loads(universe_path.read_text())
    assets_input = universe["assets"]
    symbols = tuple(item["ticker"] for item in assets_input)
    if len(symbols) != len(set(symbols)) or "SPY" not in symbols:
        raise RuntimeError("INVALID_UNIVERSE")
    end = os.getenv("PHASE8C_END_DATE", "").strip() or (date.today() - timedelta(days=1)).isoformat()
    budget = RequestBudget(int(os.getenv("PHASE8C_REQUEST_CAP", str(DEFAULT_REQUEST_CAP))))
    timeout = min(float(os.getenv("PHASE8C_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))), DEFAULT_TIMEOUT_SECONDS)
    print(json.dumps({
        "kind": "calibration_start", "model": TECHNICAL_MODEL_VERSION,
        "universe_version": universe["version"], "symbol_count": len(symbols),
        "start": universe["start"], "end": end, "feed": universe["feed"],
        "adjustment": universe["adjustment"], "request_cap": budget.cap,
    }, sort_keys=True))
    bars = fetch_daily_bars(
        symbols, start=universe["start"], end=end, feed=universe["feed"],
        adjustment=universe["adjustment"], key_id=key_id, secret_key=secret_key,
        budget=budget, timeout=timeout,
    )
    if "SPY" not in bars:
        raise RuntimeError("MISSING_SPY_HISTORY")
    asset_lookup = {item["ticker"]: item for item in assets_input}
    assets = {
        ticker: AssetMetadata(
            ticker=ticker,
            security_type=SecurityType(asset_lookup[ticker]["type"]),
            sector=asset_lookup[ticker].get("sector"),
            market_cap_band=asset_lookup[ticker].get("cap"), active=True,
            adjustment=universe["adjustment"],
        )
        for ticker in bars
    }
    sector_benchmarks = {sector: ticker for sector, ticker in universe["sector_benchmarks"].items() if ticker in bars}
    dataset = HistoricalDataset(bars=bars, assets=assets, benchmark_symbol="SPY", sector_benchmarks=sector_benchmarks)
    report = build_calibration_report(dataset)
    calibration, validation = chronological_split(report.events, WALK_FORWARD_SPLIT)
    years: dict[str, list[Any]] = defaultdict(list)
    for event in report.events:
        years[str(event.timestamp.year)].append(event)
    year_outcomes = {year: summarize_events(events) for year, events in sorted(years.items())}
    output_dir = Path(os.getenv("PHASE8C_OUTPUT_DIR", "audit_results/phase8c1"))
    output_dir.mkdir(parents=True, exist_ok=True)
    all_dates = [bar.timestamp for rows in bars.values() for bar in rows]
    summary = {
        "schema_version": "ATLAS_RADAR_CALIBRATION_AGGREGATES_V1",
        "model_version": report.model_version,
        "universe_version": universe["version"],
        "survivorship_note": universe["survivorship_note"],
        "feed": universe["feed"], "adjustment": universe["adjustment"],
        "requested_securities": len(symbols), "securities_with_history": len(bars),
        "security_symbols": sorted(bars), "total_bars": sum(len(rows) for rows in bars.values()),
        "earliest_bar": min(all_dates).isoformat(), "latest_bar": max(all_dates).isoformat(),
        "requests_used": budget.used, "state_counts": report.state_counts,
        "transition_counts": report.transition_counts,
        "state_outcomes": report.state_outcomes, "score_buckets": report.score_buckets,
        "security_type_outcomes": report.security_type_outcomes,
        "sector_outcomes": report.sector_outcomes, "regime_outcomes": report.regime_outcomes,
        "liquidity_outcomes": report.liquidity_outcomes,
        "volatility_outcomes": report.volatility_outcomes,
        "market_cap_outcomes": report.market_cap_outcomes,
        "component_correlations_20d": report.component_correlations_20d,
        "component_overlap": report.component_overlap,
        "year_outcomes": year_outcomes,
        "walk_forward": {
            "split": WALK_FORWARD_SPLIT.isoformat(),
            "calibration": summarize_events(calibration), "validation": summarize_events(validation),
        },
        "threshold_sensitivity": "DEFERRED_UNTIL_UNTOUCHED_V1_BASELINE_REVIEW",
    }
    (output_dir / "summary.json").write_text(json.dumps(_json_safe(summary), sort_keys=True, indent=2) + "\n")
    _write_group_csv(output_dir / "state_outcomes.csv", report.state_outcomes)
    _write_group_csv(output_dir / "score_buckets.csv", report.score_buckets)
    _threshold_inventory(output_dir / "threshold_sensitivity.csv")
    print(json.dumps({
        "kind": "calibration_complete", "status": "SUCCESS",
        "securities_with_history": len(bars), "total_bars": summary["total_bars"],
        "events": len(report.events), "requests_used": budget.used,
        "aggregate_artifact_count": 4,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
