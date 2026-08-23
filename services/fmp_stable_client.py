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
    """Bounded FMP stable transport with sanitized outcomes.

    ``retries=0`` preserves the scanner's existing one-request behavior.  A
    caller may explicitly request a bounded retry for research-only use.
    """

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
    ) -> FMPResponse:
        family = str(endpoint_family or "").strip().strip("/")
        fetched_at = datetime.now(timezone.utc).isoformat()
        if not self._api_key or not family:
            return FMPResponse(None, AUTHORIZATION_FAILURE, family, fetched_at, attempts=0)

        request_params = dict(params or {})
        request_params["apikey"] = self._api_key
        attempts = 0
        for attempt in range(self.retries + 1):
            attempts += 1
            try:
                response = self._session.get(
                    f"{FMP_STABLE_BASE_URL}/{family}",
                    params=request_params,
                    timeout=self.timeout_seconds,
                )
            except (requests.Timeout, requests.ConnectionError):
                if attempt < self.retries:
                    time.sleep(min(0.25 * (2 ** attempt), 1.0))
                    continue
                return FMPResponse(None, NETWORK_FAILURE, family, fetched_at, attempts=attempts)
            except Exception:
                return FMPResponse(None, NETWORK_FAILURE, family, fetched_at, attempts=attempts)

            status = int(getattr(response, "status_code", 0) or 0)
            if status in {401, 402, 403}:
                return FMPResponse(None, AUTHORIZATION_FAILURE, family, fetched_at, status, attempts)
            if status == 429:
                if attempt < self.retries:
                    time.sleep(min(0.25 * (2 ** attempt), 1.0))
                    continue
                return FMPResponse(None, RATE_LIMITED, family, fetched_at, status, attempts)
            if not 200 <= status < 300:
                return FMPResponse(None, HTTP_FAILURE, family, fetched_at, status, attempts)
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError):
                if not allow_csv:
                    return FMPResponse(None, SCHEMA_FAILURE, family, fetched_at, status, attempts)
                try:
                    body = str(getattr(response, "text", "") or "")
                    if not body.strip():
                        payload = []
                    else:
                        reader = csv.DictReader(io.StringIO(body))
                        if not reader.fieldnames:
                            raise ValueError("missing CSV schema")
                        payload = [dict(row) for row in reader]
                except Exception:
                    return FMPResponse(None, SCHEMA_FAILURE, family, fetched_at, status, attempts)
            if not isinstance(payload, (list, dict)):
                return FMPResponse(None, SCHEMA_FAILURE, family, fetched_at, status, attempts)
            outcome = AUTHORIZED_EMPTY if _empty(payload) else SUCCESS
            return FMPResponse(payload, outcome, family, fetched_at, status, attempts)

        return FMPResponse(None, NETWORK_FAILURE, family, fetched_at, attempts=attempts)


__all__ = [
    "AUTHORIZED_EMPTY", "AUTHORIZATION_FAILURE", "FMPResponse", "FMPStableClient",
    "FMP_STABLE_BASE_URL", "HTTP_FAILURE", "NETWORK_FAILURE", "RATE_LIMITED",
    "SCHEMA_FAILURE", "SUCCESS",
]
