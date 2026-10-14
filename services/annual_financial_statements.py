"""Read-only, integrity-checked annual statement presentation for Research.

The bundle is a bounded customer projection of the validated G6 annual
presentation artifacts. It cannot alter ratings, publications, or valuation.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CONTRACT = "ATLAS_ANNUAL_CUSTOMER_BUNDLE_V1"
SOURCE_CONTRACT = "ATLAS_G6_ANNUAL_STATEMENT_PRESENTATION_V1"
_ROOT = Path(__file__).resolve().parents[1] / "data" / "customer_research" / "annual_financials"


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, Mapping) else {}


@lru_cache(maxsize=1)
def _validated_bundle() -> Mapping[str, Any]:
    manifest = _read_json(_ROOT / "manifest.json")
    if manifest.get("contract") != "ATLAS_ANNUAL_CUSTOMER_BUNDLE_MANIFEST_V1":
        return {}
    if manifest.get("ratings_changed") is not False or manifest.get("publications_changed") is not False:
        return {}
    bundle_path = _ROOT / str(manifest.get("bundle") or "")
    try:
        raw = bundle_path.read_bytes()
    except OSError:
        return {}
    if hashlib.sha256(raw).hexdigest() != manifest.get("bundle_sha256"):
        return {}
    try:
        bundle = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(bundle, Mapping) or bundle.get("contract") != CONTRACT:
        return {}
    return bundle


def annual_financial_statements(ticker: Any) -> dict[str, Any]:
    """Return a ticker-bound non-scoring presentation or a typed unavailable state."""
    symbol = str(ticker or "").strip().upper()
    row = (_validated_bundle().get("tickers") or {}).get(symbol)
    if not isinstance(row, Mapping):
        return {
            "status": "UNAVAILABLE", "ticker": symbol, "periods": (), "statements": {},
            "message": "Validated annual filing history is unavailable for this security.",
        }
    if (
        row.get("contract") != SOURCE_CONTRACT
        or str(row.get("ticker") or "").upper() != symbol
        or row.get("ratings_changed") is not False
        or row.get("publications_changed") is not False
    ):
        return {
            "status": "UNAVAILABLE", "ticker": symbol, "periods": (), "statements": {},
            "message": "Annual filing history failed its customer presentation contract.",
        }
    return {
        **dict(row), "status": "AVAILABLE", "classification": "HISTORICAL_NON_SCORING",
        "message": None,
    }


__all__ = ["annual_financial_statements"]
