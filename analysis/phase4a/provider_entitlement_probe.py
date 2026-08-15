"""Tiny, non-production provider capability probe; never logs credentials."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import requests


TICKERS = ("NVDA", "AVGO")


def _probe(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=15)
        payload = response.json() if response.content else None
        rows = len(payload) if isinstance(payload, list) else (1 if payload else 0)
        return {"status_code": response.status_code, "entitled": response.ok and rows > 0, "rows": rows}
    except (requests.RequestException, ValueError) as exc:
        return {"status_code": None, "entitled": False, "rows": 0, "error_type": type(exc).__name__}


def run_probe() -> dict[str, Any]:
    fmp = os.getenv("FMP_API_KEY")
    finnhub = os.getenv("FINNHUB_API_KEY")
    result: dict[str, Any] = {"checked_at": datetime.now(timezone.utc).isoformat(), "tickers": list(TICKERS), "providers": {}}
    if fmp:
        fmp_checks = {}
        for ticker in TICKERS:
            fmp_checks[ticker] = {
                "as_reported": _probe("https://financialmodelingprep.com/stable/income-statement-as-reported", {"symbol": ticker, "limit": 2, "apikey": fmp}),
                "analyst_estimates": _probe("https://financialmodelingprep.com/stable/analyst-estimates", {"symbol": ticker, "limit": 2, "apikey": fmp}),
            }
        result["providers"]["fmp"] = {"credential_available": True, "checks": fmp_checks}
    else:
        result["providers"]["fmp"] = {"credential_available": False, "status": "NOT_TESTED_NO_APPROVED_CREDENTIAL"}
    if finnhub:
        result["providers"]["finnhub"] = {"credential_available": True, "checks": {
            ticker: {"eps_estimate": _probe("https://finnhub.io/api/v1/stock/eps-estimate", {"symbol": ticker, "token": finnhub})}
            for ticker in TICKERS
        }}
    else:
        result["providers"]["finnhub"] = {"credential_available": False, "status": "NOT_TESTED_NO_APPROVED_CREDENTIAL"}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("audit_results/phase4a/provider_entitlements.json"))
    args = parser.parse_args()
    result = run_probe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
