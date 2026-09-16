"""Small, sanitized transport for Financial Modeling Prep stable endpoints.

This module owns transport mechanics only.  It does not decide which symbols
or endpoint families are requested and it does not change provider authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import io
import json
import time
from typing import Any, Mapping

import requests


FMP_STABLE_BASE_URL = "https://financialmodelingprep.com/stable"

SUCCESS = "SUCCESS"
AUTHORIZED_EMPTY = "AUTHORIZED_EMPTY"
AUTHORIZATION_FAILURE = "AUTHORIZATION_OR_ENTITLEMENT_FAILURE"
RATE_LIMITED = "RATE_LIMITED"
NETWORK_FAILURE = "TIMEOUT_OR_NETWORK_FAILURE"
SCHEMA_FAILURE = "SCHEMA_FAILURE"
HTTP_FAILURE = "HTTP_FAILURE"
DEADLINE_EXPIRED = "DEADLINE_EXPIRED"


@dataclass(frozen=True)
class FMPResponse:
    payload: Any
    outcome: str
    endpoint_family: str
    fetched_at: str
    http_status: int | None = None
    attempts: int = 0

    @property
    def successful(self) -> bool:
        return self.outcome in {SUCCESS, AUTHORIZED_EMPTY}


def _empty(payload: Any) -> bool:
    return payload in (None, [], {})


class FMPStableClient:
    """Retired compatibility object. It never performs an HTTP request."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 12.0,
        retries: int = 0,
        session: Any = requests,
    ) -> None:
        self._api_key = str(api_key or "").strip()
        self.timeout_seconds = max(0.1, min(float(timeout_seconds), 30.0))
        self.retries = max(0, min(int(retries), 2))
        self._session = session

    def get(
        self,
        endpoint_family: str,
        params: Mapping[str, Any] | None = None,
        *,
        allow_csv: bool = False,
        deadline_monotonic: float | None = None,
    ) -> FMPResponse:
        family = str(endpoint_family or "").strip().strip("/")
        fetched_at = datetime.now(timezone.utc).isoformat()
        return FMPResponse(None, AUTHORIZATION_FAILURE, family, fetched_at, attempts=0)


__all__ = [
    "AUTHORIZED_EMPTY", "AUTHORIZATION_FAILURE", "FMPResponse", "FMPStableClient",
    "DEADLINE_EXPIRED", "FMP_STABLE_BASE_URL", "HTTP_FAILURE", "NETWORK_FAILURE", "RATE_LIMITED",
    "SCHEMA_FAILURE", "SUCCESS",
]
