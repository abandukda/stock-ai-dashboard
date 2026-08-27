"""Pure session-state invariants for authenticated ATLAS navigation."""

from __future__ import annotations

from typing import Any, MutableMapping, Sequence


def stabilize_authenticated_session(state: MutableMapping[str, Any]) -> bool:
    """Keep role aliases stable without ever authenticating a new session."""
    if not bool(state.get("authenticated")):
        return False
    role = str(state.get("role") or state.get("user_role") or "viewer")
    state["role"] = role
    state["user_role"] = role
    return True


def consume_navigation_handoff(
    state: MutableMapping[str, Any], pages: Sequence[str], *, widget_key: str,
) -> tuple[str, bool]:
    """Consume one canonical pending-page handoff before widget creation."""
    if not pages:
        raise ValueError("pages are required")
    pending = state.pop("v79_pending_page", None)
    current = pending or state.get("v73_page") or pages[0]
    if current not in pages:
        current = pages[0]
    if pending or state.get(widget_key) not in pages:
        state[widget_key] = current
    state["v73_page"] = current
    return str(current), bool(pending)


def consume_research_ticker_handoff(
    state: MutableMapping[str, Any], *, widget_key: str,
) -> tuple[str, bool]:
    """Initialize a Research ticker widget before the widget is created.

    Home-card transitions write only ``v79_pending_research_ticker`` and
    canonical application state.  The destination page consumes that value
    before calling ``st.text_input``.  Direct form submissions do not rewrite
    the already-instantiated input key.
    """
    pending = str(state.pop("v79_pending_research_ticker", "") or "").upper().strip()
    current = str(
        pending
        or state.get("active_research_ticker")
        or state.get("selected_research_ticker")
        or ""
    ).upper().strip()
    if pending:
        state[widget_key] = pending
    elif widget_key not in state:
        state[widget_key] = current
    return current, bool(pending)


__all__ = [
    "consume_navigation_handoff", "consume_research_ticker_handoff",
    "stabilize_authenticated_session",
]
