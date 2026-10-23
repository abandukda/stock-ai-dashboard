"""Explicit individual-workspace composition; inactive in default app startup.

The trusted server supplies existing dependencies. This module never selects a
store, provisions accounts, configures OIDC, acquires evidence or generates AI.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from copy import deepcopy
import re

import pandas as pd
import streamlit as st

from services.customer.models import Capability
from services.customer_authority import customer_authority
from services.personal_request_authority import personal_viewer_scope
from services.customer.watchlist_controller import PersonalWatchlistAccessError
from services.customer_navigation_contract import migrate_navigation_state
from services.session_stability import emit_page_interactive
from services.transcript_cache_reader import ReadOnlyTranscriptCache
from ui.personal_account import PersonalAccountBindings, render_personal_account
from ui.personal_watchlists import _clear_personal_widget_state


@dataclass(frozen=True)
class CustomerRuntimeBindings:
    """Server-owned objects and supplied retained rows, never browser state."""
    account: PersonalAccountBindings
    transcript_cache: ReadOnlyTranscriptCache | None = None
    earnings_rows: tuple[Mapping[str, Any], ...] = ()
    research_rows: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self):
        if not isinstance(self.account, PersonalAccountBindings):
            raise TypeError('SERVER_ACCOUNT_BINDINGS_REQUIRED')
        if self.transcript_cache is not None and not isinstance(self.transcript_cache, ReadOnlyTranscriptCache):
            raise TypeError('EXISTING_READ_ONLY_TRANSCRIPT_CACHE_REQUIRED')
        for rows in (self.earnings_rows, self.research_rows):
            if not isinstance(rows, tuple) or any(not isinstance(row, Mapping) for row in rows):
                raise TypeError('SUPPLIED_RETAINED_ROWS_REQUIRED')


_OWNER = 'atlas_personal_runtime:owner'
_PRESENTATION_KEYS = frozenset({
    'selected_ticker', 'selected_research_ticker', 'active_research_ticker',
    'typed_ticker', 'v73_research_ticker', 'v805_force_live_on_open',
    'v79_pending_research_ticker', 'v79_research_focus',
    '_atlas_research_first_screen_rendered', 'atlas_exact_candidate_research',
    'v79_pending_page', 'v73_page', 'v784_single_nav',
})
_PRESENTATION_PREFIXES = ('atlas_personal_runtime:', 'atlas_research_',
    'atlas_canonical_research_row_', 'research_', 'research-', 'v8054_live_row_',
    '_atlas_research_', 'ask_ai_', 'earnings-transcript-')


def _clear_runtime_presentation(owner: str | None = None) -> None:
    """Owner marker only discards presentation; it never grants access."""
    if owner is None or st.session_state.get(_OWNER) != owner:
        _clear_personal_widget_state()
        for key in list(st.session_state):
            if str(key) in _PRESENTATION_KEYS or str(key).startswith(_PRESENTATION_PREFIXES):
                del st.session_state[key]
    if owner is not None:
        st.session_state[_OWNER] = owner


def _render_retained_research(rows) -> dict[str, str]:
    """Select only supplied admitted evidence; no legacy refresh/acquisition."""
    pending = str(st.session_state.pop('v79_pending_research_ticker', '') or '').strip().upper()
    st.session_state.pop('v805_force_live_on_open', None)
    key = 'atlas_personal_runtime:research_ticker'
    if pending:
        st.session_state[key] = pending
    with st.form('atlas_personal_runtime:research_form'):
        typed = st.text_input('Ticker', key=key, placeholder='Search supplied retained Research').strip().upper()
        submitted = st.form_submit_button('Open retained Research')
    ticker = typed if submitted or not pending else pending
    if not ticker:
        st.info('Choose a saved company or enter a ticker from the supplied retained Research inventory.')
        return {'status': 'RESEARCH_PENDING'}
    if not re.fullmatch(r'[A-Z]{1,10}(?:[.-][A-Z]{1,3})?', ticker):
        st.info('Enter a valid ticker. No provider lookup was requested.')
        return {'status': 'RESEARCH_UNAVAILABLE'}
    matches = [row for row in rows if str(row.get('ticker') or row.get('Ticker') or '').strip().upper() == ticker]
    if len(matches) != 1 or customer_authority(matches[0]).get('status') != 'AVAILABLE':
        st.info('Admitted retained Research is unavailable for this ticker. No provider lookup was requested.')
        return {'status': 'RESEARCH_UNAVAILABLE'}
    from ui.customer_research_v2 import render_customer_research_v2
    # A copied supplied record preserves caller authority and cannot be replaced
    # by another account's session-cached legacy report.
    render_customer_research_v2(deepcopy(matches[0]), ask_cta=lambda _: st.caption(
        'Ask ATLAS is not enabled in this individual workspace. No AI request was made.'))
    emit_page_interactive(st, 'Research Any Ticker')
    return {'status': 'RESEARCH_RENDERED'}


def render_personal_runtime(bindings: CustomerRuntimeBindings, *,
                            render_navigation: Callable,
                            open_research: Callable[[str], None],
                            render_earnings: Callable) -> dict[str, str]:
    """Execute actual app routes with current account and least privilege.

    Native identities never inherit administrator aliases or gain admin routes.
    Every rerun revalidates the registered account; each controller operation
    independently revalidates expiry, revocation, ownership and entitlements.
    """
    if not isinstance(bindings, CustomerRuntimeBindings):
        _clear_runtime_presentation()
        st.warning('Individual workspace configuration is unavailable.')
        return {'status': 'UNAVAILABLE'}
    with personal_viewer_scope():
        try:
            if bindings.account.is_logged_in() is not True:
                _clear_runtime_presentation()
                return render_personal_account(bindings=bindings.account, open_research=open_research)
            access = bindings.account.watchlists.account_access()
            _clear_runtime_presentation(access.view_key)
        except PersonalWatchlistAccessError:
            _clear_runtime_presentation()
            # The account shell distinguishes unknown invitations from expired,
            # revoked or unavailable sessions without showing private controls.
            return render_personal_account(bindings=bindings.account, open_research=open_research)
        except Exception:
            _clear_runtime_presentation()
            st.warning('Your individual workspace is temporarily unavailable.')
            return {'status': 'UNAVAILABLE'}
        pages = ('Watchlist', 'Research', 'Earnings', 'Account')
        migrate_navigation_state(st.session_state, allowed_routes=pages)
        for key in ('v79_pending_page', 'v73_page', 'v784_single_nav'):
            if key in st.session_state and st.session_state[key] not in pages:
                st.session_state[key] = pages[0]
        selected = render_navigation(list(pages))
        if selected not in pages:
            _clear_runtime_presentation()
            st.warning('This route is unavailable in your individual workspace.')
            return {'status': 'ROUTE_UNAVAILABLE'}
        # Navigation and any earlier rendering must not retain access across a
        # session switch, revocation, expiry or entitlement change.
        try:
            current = bindings.account.watchlists.account_access(view_key=access.view_key)
        except Exception:
            _clear_runtime_presentation()
            st.warning('Your account session is unavailable. Sign in again from Account.')
            return {'status': 'SESSION_UNAVAILABLE'}
        required = {'Research': Capability.FULL_RESEARCH,
                    'Earnings': Capability.FULL_EARNINGS_INTELLIGENCE}.get(selected)
        if required is not None and required not in current.capabilities:
            st.info('This feature is not enabled for your account. Your saved watchlists remain available.')
            return {'status': 'FEATURE_UNAVAILABLE'}
        if selected in {'Watchlist', 'Account'}:
            def logout():
                _clear_runtime_presentation()
                bindings.account.logout()
            account = PersonalAccountBindings(bindings.account.is_logged_in, bindings.account.login,
                                              logout, bindings.account.watchlists)
            result = render_personal_account(bindings=account, open_research=open_research)
        elif selected == 'Research':
            result = _render_retained_research(bindings.research_rows)
        else:
            render_earnings(pd.DataFrame(bindings.earnings_rows), open_research=open_research,
                            transcript_cache_reader=bindings.transcript_cache)
            result = {'status': 'EARNINGS_RENDERED'}
        if selected in {'Watchlist', 'Account'}:
            emit_page_interactive(st, 'Watchlist Intelligence')
        return result
