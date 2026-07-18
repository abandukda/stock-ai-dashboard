from __future__ import annotations

from typing import Any, Iterable
import random
import time

import requests


DEFAULT_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class ProviderRequestError(RuntimeError):
    """Raised after a provider request exhausts its retry budget."""


def _is_retryable_network_error(exc: BaseException) -> bool:
    class_name = exc.__class__.__name__.lower()
    module_name = exc.__class__.__module__.lower()

    retryable_names = {
        "timeout",
        "connecttimeout",
        "readtimeout",
        "connectionerror",
        "proxyerror",
        "chunkedencodingerror",
    }

    return (
        class_name in retryable_names
        or "timeout" in class_name
        or ("requests" in module_name and "connection" in class_name)
    )


def _sleep_delay(
    *,
    attempt: int,
    backoff_seconds: float,
    retry_after: Any = None,
) -> None:
    if retry_after is not None:
        try:
            delay = min(max(float(retry_after), 0.0), 30.0)
        except (TypeError, ValueError):
            delay = backoff_seconds * (2 ** (attempt - 1))
    else:
        delay = backoff_seconds * (2 ** (attempt - 1))

    jitter = random.uniform(0.0, min(0.25, max(delay, 0.0) * 0.10))
    time.sleep(max(delay, 0.0) + jitter)


def robust_get(
    url: str,
    *,
    timeout: float | tuple[float, float] | None = None,
    max_attempts: int = 3,
    backoff_seconds: float = 0.75,
    retry_statuses: Iterable[int] = DEFAULT_RETRY_STATUS,
    provider: str = "HTTP provider",
    session: Any = None,
    **kwargs: Any,
):
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if timeout is None:
        timeout = (5.0, 20.0)

    retry_statuses = set(retry_statuses)
    client = session if session is not None else requests
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.get(url, timeout=timeout, **kwargs)
            status_code = getattr(response, "status_code", None)

            if status_code not in retry_statuses:
                return response

            if attempt >= max_attempts:
                return response

            headers = getattr(response, "headers", {}) or {}
            retry_after = (
                headers.get("Retry-After")
                if hasattr(headers, "get")
                else None
            )

            _sleep_delay(
                attempt=attempt,
                backoff_seconds=backoff_seconds,
                retry_after=retry_after,
            )

        except Exception as exc:
            last_error = exc

            if not _is_retryable_network_error(exc):
                raise

            if attempt >= max_attempts:
                break

            _sleep_delay(
                attempt=attempt,
                backoff_seconds=backoff_seconds,
            )

    raise ProviderRequestError(
        f"{provider} request failed after {max_attempts} attempts: {url}"
    ) from last_error


__all__ = [
    "DEFAULT_RETRY_STATUS",
    "ProviderRequestError",
    "robust_get",
]
