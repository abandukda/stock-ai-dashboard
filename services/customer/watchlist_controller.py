"""Opt-in personal watchlists behind a trusted server identity dependency.

This module does not verify tokens or create users. Its injected resolver must
perform the actual identity, expiry and revocation verification on every call.
Never construct that resolver from query parameters, widget or session fields.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import re
from typing import Any, Callable, Iterable, Mapping

from services.customer_authority import customer_authority
from services.live_market.models import SecurityType
from .service import CustomerService, EntitlementError
from .models import Capability


class PersonalWatchlistAccessError(PermissionError):
    """Sanitized identity/context failure; carries no credential or subject."""


@dataclass(frozen=True)
class VerifiedWatchlistSubject:
    """Result supplied by a trusted verifier, not authentication proof itself."""
    subject: str
    expires_at: datetime
    revoked: bool = False


@dataclass(frozen=True)
class WatchlistCatalogEntry:
    ticker: str
    company: str
    security_id: str
    security_type: SecurityType
    research_available: bool


@dataclass(frozen=True)
class PersonalWatchlistOverview:
    watchlist_id: str
    name: str
    is_default: bool
    symbol_count: int


@dataclass(frozen=True)
class PersonalAccountAccess:
    view_key: str
    capabilities: frozenset[Capability]


@dataclass(frozen=True)
class PersonalWatchlistSnapshot:
    view_key: str
    watchlists: tuple[PersonalWatchlistOverview, ...]


@dataclass(frozen=True)
class PersonalWatchlistItem:
    ticker: str
    company: str
    research_available: bool
    added_at: datetime
    research_entitled: bool = True


@dataclass(frozen=True)
class PersonalWatchlistDetail:
    watchlist_id: str
    name: str
    is_default: bool
    symbols: tuple[PersonalWatchlistItem, ...]


def _ticker(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("INVALID_TICKER")
    result = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-/]{0,11}", result):
        raise ValueError("INVALID_TICKER")
    return result


_UNBOUND_VIEW = object()


def _name(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80 or any(ord(char) < 32 for char in value):
        raise ValueError("INVALID_WATCHLIST_NAME")
    return value.strip()


class PersonalWatchlistController:
    """Resolve current identity before I/O; ownership never comes from the UI.

    ``view_key`` only rejects stale forms after an account switch. It is not an
    authentication token: all reads/writes still resolve the current subject
    and enforce repository ownership. No environment/path/database is selected.
    """
    def __init__(self, service: CustomerService, *,
                 resolve_verified_subject: Callable[[], VerifiedWatchlistSubject],
                 catalog: Iterable[Mapping[str, Any]] = (),
                 clock: Callable[[], datetime] | None = None):
        if not callable(resolve_verified_subject):
            raise TypeError("TRUSTED_SUBJECT_RESOLVER_REQUIRED")
        self._service = service
        self._repository = service.repository
        self._resolver = resolve_verified_subject
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        entries: dict[str, WatchlistCatalogEntry] = {}
        for row in catalog:
            if not isinstance(row, Mapping):
                continue
            try:
                ticker = _ticker(row.get("ticker") or row.get("Ticker"))
            except ValueError:
                continue
            security_id = row.get("security_id") or f"ticker:{ticker}"
            if not isinstance(security_id, str) or not security_id or len(security_id) > 200:
                continue
            kind = row.get("security_type") or row.get("Security Type")
            try:
                kind = SecurityType(kind) if kind else SecurityType.UNKNOWN
            except (TypeError, ValueError):
                kind = SecurityType.UNKNOWN
            company = row.get("company") or row.get("Company") or ticker
            if not isinstance(company, str):
                company = ticker
            entries[ticker] = WatchlistCatalogEntry(
                ticker, company[:200],
                security_id, kind, customer_authority(row).get("status") == "AVAILABLE",
            )
        self._catalog = entries

    def _verified_subject(self) -> VerifiedWatchlistSubject:
        try:
            identity = self._resolver()
            now = self._clock()
            valid = (
                isinstance(identity, VerifiedWatchlistSubject)
                and isinstance(identity.subject, str) and bool(identity.subject.strip())
                and identity.revoked is False and isinstance(identity.expires_at, datetime)
                and identity.expires_at.tzinfo is not None and identity.expires_at.utcoffset() is not None
                and isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None
                and identity.expires_at > now
            )
        except Exception:
            raise PersonalWatchlistAccessError("INDIVIDUAL_SESSION_REQUIRED") from None
        if not valid:
            raise PersonalWatchlistAccessError("INDIVIDUAL_SESSION_REQUIRED")
        return identity

    @contextmanager
    def _account(self, view_key: object = _UNBOUND_VIEW):
        identity = self._verified_subject()  # Before transaction/file/database I/O.
        transaction = getattr(self._repository, "transaction", None)
        with transaction() if callable(transaction) else nullcontext():
            # A competing request can hold the storage lock after the first
            # verification. Do not admit a session that expired, was revoked,
            # or changed accounts while this request waited for that lock.
            current_identity = self._verified_subject()
            if current_identity.subject != identity.subject:
                raise PersonalWatchlistAccessError("WATCHLIST_CONTEXT_CHANGED")
            try:
                registered = self._repository.user_by_auth_subject(identity.subject)
                if registered is None:
                    raise PersonalWatchlistAccessError("ACCOUNT_NOT_REGISTERED")
                user, _ = self._service.account(registered[0].user_id)
            except PersonalWatchlistAccessError:
                raise
            except (KeyError, PermissionError):
                raise PersonalWatchlistAccessError("ACCOUNT_UNAVAILABLE") from None
            current_key = hashlib.sha256(("personal-watchlists:" + user.user_id).encode()).hexdigest()[:24]
            if view_key is not _UNBOUND_VIEW and (not isinstance(view_key, str) or not hmac.compare_digest(view_key, current_key)):
                raise PersonalWatchlistAccessError("WATCHLIST_CONTEXT_CHANGED")
            yield user.user_id, current_key

    def account_access(self, *, view_key: object = _UNBOUND_VIEW) -> PersonalAccountAccess:
        """Revalidate current registered authority, never token/session roles."""
        with self._account(view_key) as (owner, key):
            return PersonalAccountAccess(key, self._service.entitlements(owner).capabilities)

    def snapshot(self) -> PersonalWatchlistSnapshot:
        with self._account() as (owner, key):
            lists = tuple(PersonalWatchlistOverview(item.watchlist_id, item.name, item.is_default,
                len(self._service.list_symbols(owner, item.watchlist_id)))
                for item in self._repository.list_watchlists(owner))
            return PersonalWatchlistSnapshot(key, lists)

    def read_watchlist(self, watchlist_id: str, *, view_key: str) -> PersonalWatchlistDetail:
        with self._account(view_key) as (owner, _):
            item = self._repository.get_watchlist(owner, watchlist_id)
            symbols = []
            for saved in self._service.list_symbols(owner, watchlist_id):
                entry = self._catalog.get(saved.security.ticker)
                symbols.append(PersonalWatchlistItem(saved.security.ticker,
                    entry.company if entry else saved.security.ticker,
                    bool(entry and entry.research_available), saved.added_at,
                    self._service.allows(owner, Capability.FULL_RESEARCH)))
            return PersonalWatchlistDetail(item.watchlist_id, item.name, item.is_default, tuple(symbols))

    def create_watchlist(self, name: str, *, view_key: str) -> None:
        with self._account(view_key) as (owner, _):
            self._service.create_watchlist(owner, _name(name))

    def rename_watchlist(self, watchlist_id: str, name: str, *, view_key: str) -> None:
        with self._account(view_key) as (owner, _):
            self._service.rename_watchlist(owner, watchlist_id, _name(name))

    def delete_watchlist(self, watchlist_id: str, *, view_key: str) -> None:
        with self._account(view_key) as (owner, _):
            self._service.delete_watchlist(owner, watchlist_id)

    def set_default_watchlist(self, watchlist_id: str, *, view_key: str) -> None:
        with self._account(view_key) as (owner, _):
            self._service.set_default_watchlist(owner, watchlist_id)

    def add_ticker(self, watchlist_id: str, ticker: str, *, view_key: str) -> None:
        with self._account(view_key) as (owner, _):
            self._repository.get_watchlist(owner, watchlist_id)
            entry = self._catalog.get(_ticker(ticker))
            if entry is None:
                raise ValueError("TICKER_NOT_IN_PROVIDED_CATALOG")
            self._service.add_symbol(owner, watchlist_id, security_id=entry.security_id,
                ticker=entry.ticker, security_type=entry.security_type)

    def remove_ticker(self, watchlist_id: str, ticker: str, *, view_key: str) -> None:
        with self._account(view_key) as (owner, _):
            ticker = _ticker(ticker)
            for saved in self._service.list_symbols(owner, watchlist_id):
                if saved.security.ticker == ticker:
                    self._service.remove_symbol(owner, watchlist_id, saved.security.security_id)
                    return
            raise KeyError("WATCHLIST_SYMBOL_UNAVAILABLE")

    def search_catalog(self, query: str, *, view_key: str) -> tuple[WatchlistCatalogEntry, ...]:
        with self._account(view_key):
            if not isinstance(query, str) or len(query) > 80:
                raise ValueError("INVALID_SEARCH_QUERY")
            needle = query.strip().casefold()
            return tuple(entry for _, entry in sorted(self._catalog.items())
                         if needle and (needle in entry.ticker.casefold() or needle in entry.company.casefold()))[:20]

    def research_ticker(self, watchlist_id: str, ticker: str, *, view_key: str) -> str:
        with self._account(view_key) as (owner, _):
            if not self._service.allows(owner, Capability.FULL_RESEARCH):
                raise EntitlementError("FULL_RESEARCH_REQUIRED")
            ticker = _ticker(ticker)
            saved = self._service.list_symbols(owner, watchlist_id)
            entry = self._catalog.get(ticker)
            if not any(value.security.ticker == ticker for value in saved) or not entry or not entry.research_available:
                raise KeyError("RESEARCH_UNAVAILABLE")
            return ticker
