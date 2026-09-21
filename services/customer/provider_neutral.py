"""Customer-presentation boundary for provider-neutral ATLAS evidence.

Canonical records retain complete provider provenance.  Objects crossing this
boundary are presentation copies and must not expose the current data vendor.
"""
from __future__ import annotations

import re
from typing import Any, Mapping


_TWELVE = re.compile(r"(?i)(?:TWELVE_DATA|TWELVE[ _-]+DATA|\bTWELVE\b)")
_PROVIDER_KEYS = {
    "provider", "provider_name", "transport_provider", "quote_source",
    "source_attribution", "attribution",
}


def _neutral_text(value: str) -> str:
    replacements = (
        (re.compile(r"(?i)certified using twelve[ _-]+data"), "Certified ATLAS analysis"),
        (re.compile(r"(?i)according to twelve[ _-]+data"), "based on ATLAS's certified market and financial data"),
        (re.compile(r"(?i)twelve[ _-]+data price"), "last verified market price"),
        (re.compile(r"(?i)twelve[ _-]+data unavailable"), "market data unavailable"),
        (re.compile(r"(?i)twelve[ _-]+data\s*/\s*time_series"), "Verified market history"),
        (re.compile(r"(?i)twelve[ _-]+data websocket"), "Verified live market data"),
    )
    output = value
    for pattern, replacement in replacements:
        output = pattern.sub(replacement, output)
    return _TWELVE.sub("ATLAS verified data", output)


def contains_customer_provider_branding(value: Any) -> bool:
    """Return whether a serialized customer value exposes Twelve branding."""
    return bool(_TWELVE.search(str(value)))


def provider_neutral_customer_projection(value: Any) -> Any:
    """Return a deep customer-safe copy without changing the source object.

    Provider-labelled keys are omitted only when their value identifies Twelve.
    Internal provenance remains untouched in the canonical source record.
    """
    if isinstance(value, Mapping):
        output: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if contains_customer_provider_branding(key):
                continue
            if normalized_key in _PROVIDER_KEYS and contains_customer_provider_branding(item):
                continue
            if isinstance(item, str) and contains_customer_provider_branding(item):
                if normalized_key in {"source_type", "source_methodology_version", "methodology_version"}:
                    output[key] = "VERIFIED_ATLAS_MARKET_DATA"
                elif normalized_key in {"status_detail", "message", "error", "reason"}:
                    output[key] = "Market data unavailable."
                else:
                    output[key] = _neutral_text(item)
                continue
            output[key] = provider_neutral_customer_projection(item)
        return output
    if isinstance(value, tuple):
        return tuple(provider_neutral_customer_projection(item) for item in value)
    if isinstance(value, list):
        return [provider_neutral_customer_projection(item) for item in value]
    if isinstance(value, set):
        return {provider_neutral_customer_projection(item) for item in value}
    return value


__all__ = ["contains_customer_provider_branding", "provider_neutral_customer_projection"]
