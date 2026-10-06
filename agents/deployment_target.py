"""Dependency-light validation for the governed ATLAS deployment target."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


PRODUCTION_ATLAS_URL = "https://stock-ai-dashboard.streamlit.app/"
PRODUCTION_ATLAS_HOST = "stock-ai-dashboard.streamlit.app"
RETIRED_ATLAS_HOSTS = frozenset({"atlas-production-7f3.streamlit.app"})


class DeploymentTargetValidationError(ValueError):
    """Raised when a production verification target is missing or unsafe."""

    def __init__(self, reason: str, resolved_target_url: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.resolved_target_url = resolved_target_url


def canonical_production_url(url: str) -> str:
    """Return a canonical public Streamlit origin or fail closed."""
    raw = str(url or "").strip()
    if not raw:
        raise DeploymentTargetValidationError("ATLAS_PRODUCTION_URL_MISSING")
    if "://" not in raw:
        raw = f"https://{raw}"
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    target = urlunsplit(("https", host, path, "", ""))
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise DeploymentTargetValidationError("LOCALHOST_NOT_ALLOWED_IN_PRODUCTION", target)
    if parts.scheme not in {"", "https"}:
        raise DeploymentTargetValidationError("PRODUCTION_URL_REQUIRES_HTTPS", target)
    try:
        port = parts.port
    except ValueError as exc:
        raise DeploymentTargetValidationError("MALFORMED_PRODUCTION_URL", target) from exc
    if parts.username or parts.password or port:
        raise DeploymentTargetValidationError("MALFORMED_PRODUCTION_URL", target)
    if host == "share.streamlit.io" or (host.endswith("streamlit.io") and path.startswith("/app/")):
        raise DeploymentTargetValidationError("GENERIC_STREAMLIT_SHARE_SHELL", target)
    if not host.endswith(".streamlit.app"):
        raise DeploymentTargetValidationError("NON_STREAMLIT_APP_ORIGIN", target)
    if host in RETIRED_ATLAS_HOSTS:
        raise DeploymentTargetValidationError("RETIRED_ATLAS_DEPLOYMENT_TARGET", target)
    if host != PRODUCTION_ATLAS_HOST:
        raise DeploymentTargetValidationError("UNAUTHORIZED_STREAMLIT_APP_TARGET", target)
    if path != "/":
        raise DeploymentTargetValidationError("UNEXPECTED_PRODUCTION_URL_PATH", target)
    return PRODUCTION_ATLAS_URL
