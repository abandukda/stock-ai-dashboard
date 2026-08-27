"""Pure session-state invariants for authenticated ATLAS navigation."""

from __future__ import annotations

import html
import re
from typing import Any, Final, MutableMapping, Sequence


PAGE_LIFECYCLE_VERSION: Final = "ATLAS_PAGE_LIFECYCLE_V1"
PAGE_INTERACTIVE_CONTRACTS: Final = {
    "Home": "PRIMARY_CARDS", "Today's Opportunities": "OPPORTUNITY_SURFACE",
    "Volume Intelligence": "VOLUME_FILTERS", "Atlas Core Holdings": "CORE_HOLDINGS_SURFACE",
    "Research Any Ticker": "TICKER_FORM", "Earnings Intelligence": "EARNINGS_SURFACE",
    "Full Ranked Scan": "RANKED_SCAN_SURFACE", "Portfolio Intelligence": "PORTFOLIO_INPUT",
    "Watchlist Intelligence": "WATCHLIST_INPUT", "Recovery": "RECOVERY_SURFACE",
    "ETFs": "ETF_SURFACE", "Political Intelligence": "POLITICAL_EVIDENCE_SURFACE",
    "Ask AI": "ASK_FORM", "Developer Center": "DEVELOPER_TABS",
}


def emit_page_interactive(st: Any, page: str) -> None:
    """Emit lifecycle identity after a renderer establishes its primary surface."""
    identifier = re.sub(r"[^a-z0-9]+", "-", str(page).lower()).strip("-")
    surface = PAGE_INTERACTIVE_CONTRACTS[page]
    st.markdown(
        f'<span id="atlas-qa-interactive-{html.escape(identifier)}" '
        f'data-atlas-qa="page-interactive" data-atlas-page="{html.escape(identifier)}" '
        f'data-atlas-page-interactive="true" data-atlas-surface="{html.escape(surface)}" '
        'aria-hidden="true" style="display:none">page-interactive</span>',
        unsafe_allow_html=True,
    )


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
    "PAGE_INTERACTIVE_CONTRACTS", "PAGE_LIFECYCLE_VERSION", "emit_page_interactive",
    "consume_navigation_handoff", "consume_research_ticker_handoff",
    "stabilize_authenticated_session",
]
