"""Integrity-checked loader for retained annual and quarterly Research history."""
from __future__ import annotations

from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1] / "data" / "customer_research" / "statement_histories"
MANIFEST_CONTRACT = "ATLAS_CUSTOMER_STATEMENT_HISTORY_BUNDLE_MANIFEST_V1"
PROJECTION_CONTRACT = "ATLAS_CUSTOMER_STATEMENT_HISTORY_PROJECTION_V1"


def _unavailable(ticker: str, reason: str) -> dict[str, Any]:
    return {"status": "UNAVAILABLE", "ticker": ticker, "reason": reason}


@lru_cache(maxsize=1)
def _manifest() -> Mapping[str, Any]:
    try:
        value = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if (
        not isinstance(value, Mapping)
        or value.get("contract") != MANIFEST_CONTRACT
        or value.get("provider_calls") != 0
        or value.get("rating_authority") != "UNCHANGED"
        or value.get("publication_authority") != "UNCHANGED"
    ):
        return {}
    return value


@lru_cache(maxsize=32)
def customer_statement_history(ticker: Any) -> dict[str, Any]:
    symbol = str(ticker or "").strip().upper()
    entry = (_manifest().get("files") or {}).get(symbol)
    if not isinstance(entry, Mapping):
        return _unavailable(symbol, "SOURCE_BOUND_STATEMENT_HISTORY_NOT_RETAINED")
    path = ROOT / str(entry.get("gzip") or "")
    try:
        compressed = path.read_bytes()
        if hashlib.sha256(compressed).hexdigest() != entry.get("gzip_sha256"):
            return _unavailable(symbol, "STATEMENT_HISTORY_GZIP_HASH_MISMATCH")
        raw = gzip.decompress(compressed)
        if hashlib.sha256(raw).hexdigest() != entry.get("json_sha256"):
            return _unavailable(symbol, "STATEMENT_HISTORY_JSON_HASH_MISMATCH")
        value = json.loads(raw)
    except (OSError, ValueError, gzip.BadGzipFile):
        return _unavailable(symbol, "STATEMENT_HISTORY_READ_FAILED")
    if (
        not isinstance(value, Mapping)
        or value.get("contract") != PROJECTION_CONTRACT
        or str(value.get("ticker") or "").upper() != symbol
        or value.get("read_only") is not True
        or value.get("provider_calls") != 0
        or value.get("rating_authority") != "UNCHANGED"
        or value.get("publication_authority") != "UNCHANGED"
    ):
        return _unavailable(symbol, "STATEMENT_HISTORY_AUTHORITY_MISMATCH")
    return dict(value)


__all__ = ["customer_statement_history"]
