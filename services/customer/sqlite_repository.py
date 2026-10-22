"""Opt-in private customer persistence for local beta validation.

This is a storage adapter, not an identity verifier or a production database
installation. Handlers must obtain user identity from a verified external auth
subject and must never accept arbitrary customer IDs as authentication.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime, time
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading
from typing import Any

from . import models
from .repository import CustomerRepository, InMemoryCustomerRepository


_SCHEMA = "ATLAS_PRIVATE_CUSTOMER_STATE_V1"
_TYPES = {name: value for name, value in vars(models).items()
          if isinstance(value, type) and (is_dataclass(value) or issubclass(value, Enum))}
_METHODS = {name for name in vars(CustomerRepository) if not name.startswith("_")}
_FIELDS = set(vars(InMemoryCustomerRepository()))
_READ_METHODS = {"user_by_auth_subject", "get_user", "list_watchlists", "get_watchlist",
                 "list_watchlist_symbols", "get_notification_preferences", "list_alert_preferences",
                 "list_saved_research", "get_feature_override", "list_deliveries", "active_symbol_union"}


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return {"enum": type(value).__name__, "value": value.value}
    if is_dataclass(value):
        return {"entity": type(value).__name__, "fields": {f.name: _encode(getattr(value, f.name)) for f in fields(value)}}
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, time):
        return {"time": value.isoformat()}
    if isinstance(value, dict):
        return {"map": [[_encode(k), _encode(v)] for k, v in value.items()]}
    if isinstance(value, (tuple, frozenset)):
        return {"tuple" if isinstance(value, tuple) else "frozenset": [_encode(v) for v in value]}
    if isinstance(value, list):
        return [_encode(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("unsupported customer-state value")


def _decode(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    if "entity" in value:
        cls = _TYPES[value["entity"]]
        if not is_dataclass(cls):
            raise ValueError("invalid customer entity")
        return cls(**{k: _decode(v) for k, v in value["fields"].items()})
    if "enum" in value:
        cls = _TYPES[value["enum"]]
        if not issubclass(cls, Enum):
            raise ValueError("invalid customer enum")
        return cls(value["value"])
    if set(value) == {"datetime"}:
        return datetime.fromisoformat(value["datetime"])
    if set(value) == {"time"}:
        return time.fromisoformat(value["time"])
    if set(value) == {"map"}:
        return {_decode(k): _decode(v) for k, v in value["map"]}
    if set(value) == {"tuple"}:
        return tuple(_decode(v) for v in value["tuple"])
    if set(value) == {"frozenset"}:
        return frozenset(_decode(v) for v in value["frozenset"])
    raise ValueError("unknown customer-state encoding")


class PrivateSQLiteCustomerRepository:
    """Bounded private snapshot storage using the existing ownership semantics.

    Serialized writes prevent lost updates between repository instances. Service
    operations use transaction() to make quota checks and multi-step defaults
    atomic. No path is selected from environment variables or user input.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / "customer_state.sqlite3"
        self._local = threading.local()
        self._private(self.root, directory=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self._private(self.path)
        with self._connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), schema TEXT NOT NULL, body TEXT NOT NULL, sha256 TEXT NOT NULL)")

    @staticmethod
    def _private(path: Path, *, directory: bool = False):
        info = path.lstat()
        if (info.st_uid != os.getuid() or info.st_mode & 0o077
                or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
            raise PermissionError("CUSTOMER_PRIVATE_STORAGE_REQUIRED")

    @contextmanager
    def _connection(self):
        self._private(self.root, directory=True)
        self._private(self.path)
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16 * 1024 * 1024)
            db.execute("PRAGMA journal_mode=DELETE")
            with db:
                yield db
        finally:
            db.close()

    def _load(self, db):
        repo = InMemoryCustomerRepository()
        row = db.execute("SELECT schema,body,sha256 FROM state WHERE id=1").fetchone()
        if row:
            if row[0] != _SCHEMA or hashlib.sha256(row[1].encode()).hexdigest() != row[2]:
                raise ValueError("CUSTOMER_STATE_INTEGRITY_FAILED")
            decoded = _decode(json.loads(row[1]))
            if not isinstance(decoded, dict) or set(decoded) != _FIELDS:
                raise ValueError("CUSTOMER_STATE_SCHEMA_FAILED")
            vars(repo).update(decoded)
        return repo

    @contextmanager
    def transaction(self):
        current = getattr(self._local, "repository", None)
        if current is not None:
            yield self
            return
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            repo = self._load(db)
            self._local.repository = repo
            self._local.dirty = False
            try:
                yield self
                if self._local.dirty:
                    body = json.dumps(_encode(vars(repo)), sort_keys=True, separators=(",", ":"), allow_nan=False)
                    db.execute("INSERT INTO state VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET schema=excluded.schema,body=excluded.body,sha256=excluded.sha256",
                               (_SCHEMA, body, hashlib.sha256(body.encode()).hexdigest()))
            finally:
                del self._local.repository
                del self._local.dirty

    def __getattr__(self, name):
        if name not in _METHODS:
            raise AttributeError(name)
        def call(*args, **kwargs):
            with self.transaction():
                result = getattr(self._local.repository, name)(*args, **kwargs)
                if name not in _READ_METHODS:
                    self._local.dirty = True
                return result
        return call


__all__ = ["PrivateSQLiteCustomerRepository"]
