"""Request-scoped restriction for explicitly composed individual workspaces.

This context can only narrow authority to viewer. It does not authenticate a
user or grant any role, and never reads or writes shared session aliases.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_PERSONAL_VIEWER = ContextVar('atlas_personal_viewer', default=False)


def personal_viewer_active() -> bool:
    return _PERSONAL_VIEWER.get() is True


@contextmanager
def personal_viewer_scope():
    token = _PERSONAL_VIEWER.set(True)
    try:
        yield
    finally:
        _PERSONAL_VIEWER.reset(token)
