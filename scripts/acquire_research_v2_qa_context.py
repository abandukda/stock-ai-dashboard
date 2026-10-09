"""Acquire a bounded, QA-only licensed Research V2 context bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from services.finnhub_shadow_provider import FinnhubShadowAdapter


CAPABILITIES = ("historical_ohlcv", "recommendations", "price_targets", "company_news", "company_profile", "basic_financials", "earnings_calendar")


def acquire(tickers: tuple[str, ...], output: Path) -> dict:
    adapter = FinnhubShadowAdapter(license_class="LICENSED_GOVERNED_QA_ONLY")
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=370)
    rows, calls = {}, 0
    for ticker in tickers:
        records = {}
        for capability in CAPABILITIES:
            params = {}
            if capability == "historical_ohlcv":
                params = {"resolution": "D", "from": int(start.timestamp()), "to": int(now.timestamp())}
            elif capability in {"company_news", "earnings_calendar"}:
                params = {"from": (now - timedelta(days=120)).date().isoformat(), "to": now.date().isoformat()}
            records[capability] = adapter.fetch(capability, ticker, **params).as_dict()
            calls += 1
        rows[ticker] = records
    spy = adapter.fetch("historical_ohlcv", "SPY", resolution="D", **{"from": int(start.timestamp()), "to": int(now.timestamp())}).as_dict()
    calls += 1
    for records in rows.values():
        records["spy_historical_ohlcv"] = spy
    result = {"schema": "ATLAS_RESEARCH_V2_LICENSED_QA_CONTEXT_V1", "scope": "QA_ONLY", "provider_calls": calls, "tickers": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default="NVDA,MSFT,AVT")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = acquire(tuple(x.strip().upper() for x in args.tickers.split(",") if x.strip()), args.output)
    print(json.dumps({"provider_calls": result["provider_calls"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
