"""Legacy workspace watchlist boundary; no individual identity is inferred here."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any


def workspace_watchlist_allowed(state: Mapping[str, Any]) -> bool:
    """Only an authenticated, unambiguous administrator may use shared storage.

    These values are server-owned login state, never request/query parameters.
    A shared viewer/beta password or an arbitrary user_id/auth_subject is not
    an individual identity and cannot authorize access to the workspace file.
    """
    if state.get("authenticated") is not True:
        return False
    roles = [state.get(key) for key in ("role", "user_role") if state.get(key) is not None]
    if not roles or any(role != "admin" for role in roles):
        return False
    credential_role = state.get("authentication_credential_role")
    return credential_role in (None, "admin")
