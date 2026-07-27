
"""Small shared cache helpers for component payloads.

The builder itself is deterministic and does not perform remote calls. Remote
provider adapters should use these TTLs and keep last-known-good data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


COMPONENT_TTLS_SECONDS = {
    "quote": 1800,
    "technical": 1800,
    "news": 3600,
    "analyst": 21600,
    "earnings": 21600,
    "financial": 43200,
    "institutional": 43200,
    "political": 43200,
}


@dataclass(frozen=True)
class CacheEnvelope:
    data: Any
    source: str
    as_of: str
    cache_status: str
    retrieval_status: str
    error: str = ""


def ttl_for(component_name: str) -> int:
    return COMPONENT_TTLS_SECONDS.get(component_name, 21600)


__all__ = [
    "COMPONENT_TTLS_SECONDS",
    "CacheEnvelope",
    "ttl_for",
]
