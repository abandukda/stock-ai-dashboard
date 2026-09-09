"""Bounded non-canonical caches for governed discovery market acquisition."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any, Mapping, Sequence

import pandas as pd


NEGATIVE_TTL_SECONDS = 7 * 86400
HISTORY_SCHEMA_VERSION = "GOVERNED_MARKET_HISTORY_CACHE_V1"
NEGATIVE_SCHEMA_VERSION = "GOVERNED_MARKET_NEGATIVE_CACHE_V1"


def normalize_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Canonicalize governed daily bars before caching or indicator use."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    value = frame.copy()
    value.index = pd.to_datetime(value.index, errors="coerce", utc=True)
    value = value.loc[~value.index.isna()]
    value = value.sort_index(kind="stable")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in value:
            value[column] = pd.to_numeric(value[column], errors="coerce")
    if value.index.has_duplicates:
        aggregations = {
            column: operation for column, operation in (
                ("Open", "first"), ("High", "max"), ("Low", "min"),
                ("Close", "last"), ("Volume", "max"),
            ) if column in value
        }
        value = value.groupby(level=0, sort=True).agg(aggregations)
    return value.dropna(subset=["Close"]) if "Close" in value else pd.DataFrame()


def cache_namespace(symbols: Sequence[str], *, provider_policy: str, mapping_version: str) -> str:
    material = "|".join((provider_policy, mapping_version, *sorted(set(symbols))))
    return hashlib.sha256(material.encode()).hexdigest()


def _safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Z0-9_.-]", "_", str(symbol).upper())


def load_negative_cache(path: Path, *, namespace: str, now: float | None = None) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if payload.get("schema_version") != NEGATIVE_SCHEMA_VERSION or payload.get("namespace") != namespace:
        return {}
    current = time.time() if now is None else now
    return {
        symbol: dict(record) for symbol, record in (payload.get("records") or {}).items()
        if isinstance(record, Mapping) and float(record.get("expires_at") or 0) > current
    }


def write_negative_cache(path: Path, *, namespace: str, records: Mapping[str, Mapping[str, Any]], now: float | None = None) -> None:
    current = time.time() if now is None else now
    kept = {
        symbol: {**dict(record), "expires_at": current + NEGATIVE_TTL_SECONDS}
        for symbol, record in records.items() if record.get("retryable") is False
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": NEGATIVE_SCHEMA_VERSION, "namespace": namespace,
                                "generated_at": datetime.now(timezone.utc).isoformat(), "records": kept}, indent=2) + "\n")


def load_history(root: Path, symbol: str, *, namespace: str) -> pd.DataFrame:
    path = root / f"{_safe_name(symbol)}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != HISTORY_SCHEMA_VERSION or payload.get("namespace") != namespace:
            return pd.DataFrame()
        frame = pd.DataFrame(payload.get("values") or [])
        frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True)
        return normalize_history_frame(frame.set_index("datetime"))
    except Exception:
        return pd.DataFrame()


def append_history(root: Path, symbol: str, frame: pd.DataFrame, *, namespace: str, keep: int = 320) -> pd.DataFrame:
    prior = load_history(root, symbol, namespace=namespace)
    combined = normalize_history_frame(pd.concat([prior, frame]) if not prior.empty else frame).tail(keep)
    combined.index.name = "datetime"
    root.mkdir(parents=True, exist_ok=True)
    values = combined.reset_index().assign(datetime=lambda value: value["datetime"].astype(str)).to_dict("records")
    (root / f"{_safe_name(symbol)}.json").write_text(json.dumps({
        "schema_version": HISTORY_SCHEMA_VERSION, "namespace": namespace,
        "updated_at": datetime.now(timezone.utc).isoformat(), "values": values,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    return combined
