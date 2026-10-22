"""Opt-in binding from Streamlit's server-verified OIDC user to personal lists.

The caller must supply ``read_server_user=lambda: st.user`` from server code,
not a widget, query parameter or session_state mapping. Streamlit performs OIDC
signature verification; this adapter additionally pins issuer/audience, expiry
and current revocation. It never verifies arbitrary browser-supplied claims.
No accounts, roles, credentials, persistence paths or provider calls are created.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import hashlib
import json
import math

from .service import CustomerService
from .watchlist_controller import (
    PersonalWatchlistAccessError, PersonalWatchlistController,
    VerifiedWatchlistSubject,
)


def oidc_account_subject(issuer: str, subject: str) -> str:
    """Stable collision-resistant account key; identical subs across IdPs differ."""
    if not all(isinstance(value, str) and value and value == value.strip()
               and len(value) <= 2048 and not any(ord(c) < 32 for c in value)
               for value in (issuer, subject)):
        raise ValueError("INVALID_OIDC_ACCOUNT_IDENTITY")
    canonical = json.dumps([issuer, subject], ensure_ascii=True, separators=(",", ":"))
    return "oidc:v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StreamlitOIDCSubjectResolver:
    """Resolve each operation from current native login and revocation authority.

    ``is_revoked`` is mandatory and must return exactly False to admit. Exceptions
    and unavailable authorities fail closed. Roles/entitlements remain in the
    customer repository; an OIDC role claim grants no application role.
    """
    def __init__(self, *, read_server_user: Callable, issuer: str, audience: str,
                 is_revoked: Callable[[str], bool],
                 clock: Callable[[], datetime] | None = None):
        if not callable(read_server_user) or not callable(is_revoked):
            raise TypeError("TRUSTED_IDENTITY_DEPENDENCIES_REQUIRED")
        oidc_account_subject(issuer, audience)  # Validate nonempty pinned values.
        self._read = read_server_user
        self._issuer = issuer
        self._audience = audience
        self._revoked = is_revoked
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def __call__(self) -> VerifiedWatchlistSubject:
        try:
            user = self._read()
            # Native st.user exposes login status as an attribute, not a token claim.
            if getattr(user, "is_logged_in", None) is not True:
                raise ValueError("login required")
            if not isinstance(user, Mapping):
                raise ValueError("server user required")
            claims = user
            if claims.get("iss") != self._issuer:
                raise ValueError("issuer mismatch")
            aud = claims.get("aud")
            if isinstance(aud, str):
                audiences = [aud]
            elif isinstance(aud, list) and aud and all(isinstance(x, str) for x in aud):
                audiences = aud
            else:
                raise ValueError("audience required")
            if self._audience not in audiences:
                raise ValueError("audience mismatch")
            # OIDC requires authorized party when more than one audience exists.
            if len(audiences) > 1 and claims.get("azp") != self._audience:
                raise ValueError("authorized party mismatch")
            if claims.get("azp", self._audience) != self._audience:
                raise ValueError("authorized party mismatch")
            subject = oidc_account_subject(self._issuer, claims.get("sub"))
            now = self._clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("aware clock required")
            expiry = claims.get("exp")
            if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
                raise ValueError("expiry required")
            for field in ("nbf", "iat"):
                value = claims.get(field)
                if value is not None and (isinstance(value, bool)
                    or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or value > now.timestamp()):
                    raise ValueError("session not yet valid")
            expires_at = datetime.fromtimestamp(expiry, timezone.utc)
            if expires_at <= now or self._revoked(subject) is not False:
                raise ValueError("session unavailable")
            return VerifiedWatchlistSubject(subject, expires_at)
        except Exception:
            raise PersonalWatchlistAccessError("INDIVIDUAL_SESSION_REQUIRED") from None


def bind_personal_watchlists(service: CustomerService, *, read_server_user: Callable,
                             issuer: str, audience: str, is_revoked: Callable,
                             catalog=(), clock=None) -> PersonalWatchlistController:
    """Explicit opt-in only; approved persistence is supplied, never auto-opened."""
    resolver = StreamlitOIDCSubjectResolver(read_server_user=read_server_user,
        issuer=issuer, audience=audience, is_revoked=is_revoked, clock=clock)
    return PersonalWatchlistController(service, resolve_verified_subject=resolver,
                                      catalog=catalog, clock=clock)
