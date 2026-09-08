"""Small compatibility surface for legacy UI helpers using governed providers.

It exists only to keep old presentation helpers operational while their call
sites are retired. Values come from canonical FMP history/profile services.
"""
from __future__ import annotations

import os
from typing import Any
import pandas as pd

from engines.canonical_market_data import load_price_history
from services.fmp_stable_client import FMPStableClient, SUCCESS


class GovernedTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = str(symbol).upper().strip()

    def history(self, **kwargs: Any) -> pd.DataFrame:
        return download(self.symbol, period=kwargs.get("period", "2y"), interval=kwargs.get("interval", "1d"))

    def get_info(self) -> dict[str, Any]:
        response = FMPStableClient(os.getenv("FMP_API_KEY", "")).get("profile", {"symbol": self.symbol})
        rows = response.payload if response.outcome == SUCCESS else []
        row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
        return dict(row)

    @property
    def info(self) -> dict[str, Any]:
        return self.get_info()

    @property
    def upgrades_downgrades(self):
        return None

    @property
    def funds_data(self):
        return None


def Ticker(symbol: str) -> GovernedTicker:
    return GovernedTicker(symbol)


def download(tickers: Any, *, period: str = "2y", interval: str = "1d", **_kwargs: Any) -> pd.DataFrame:
    symbols = [tickers] if isinstance(tickers, str) else list(tickers or [])
    frames: dict[str, pd.DataFrame] = {}
    for raw in symbols:
        symbol = str(raw).upper().strip()
        result = load_price_history(symbol, period=period, interval=interval)
        records = result.get("records") or []
        if not records:
            continue
        frame = pd.DataFrame(records)
        frame.index = pd.to_datetime(frame.pop("date"), errors="coerce", utc=True)
        frames[symbol] = frame.rename(columns={name: name.title() for name in ("open", "high", "low", "close", "volume")})
    if not frames:
        return pd.DataFrame()
    if len(frames) == 1:
        return next(iter(frames.values()))
    return pd.concat(frames, axis=1)


__all__ = ["Ticker", "download"]
