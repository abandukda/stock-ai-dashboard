"""Explicit individual-workspace composition; inactive in default app startup.

The trusted server supplies existing dependencies. This module never selects a
store, provisions accounts, configures OIDC, acquires evidence or generates AI.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from copy import deepcopy
import re
import inspect

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
    home_story: Mapping[str, Any] | None = None

    def __post_init__(self):
        if not isinstance(self.account, PersonalAccountBindings):
            raise TypeError('SERVER_ACCOUNT_BINDINGS_REQUIRED')
        if self.transcript_cache is not None and not isinstance(self.transcript_cache, ReadOnlyTranscriptCache):
            raise TypeError('EXISTING_READ_ONLY_TRANSCRIPT_CACHE_REQUIRED')
        if self.home_story is not None and not isinstance(self.home_story, Mapping):
            raise TypeError('SUPPLIED_ADMITTED_HOME_PROJECTION_REQUIRED')
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
    'home_buy_now_search', 'home_remaining_buy_now_ticker',
})
_PRESENTATION_PREFIXES = ('atlas_personal_runtime:', 'atlas_research_',
    'atlas_canonical_research_row_', 'research_', 'research-', 'v8054_live_row_',
    '_atlas_research_', 'ask_ai_', 'earnings-transcript-', 'home_chart_range_')


def _clear_runtime_presentation(owner: str | None = None) -> None:
    """Owner marker only discards presentation; it never grants access."""
    changed = owner is None or st.session_state.get(_OWNER) != owner
    if changed:
        _clear_personal_widget_state()
        for key in list(st.session_state):
            if str(key) in _PRESENTATION_KEYS or str(key).startswith(_PRESENTATION_PREFIXES):
                del st.session_state[key]
    if owner is not None:
        st.session_state[_OWNER] = owner
        if changed:
            # Explicit pending handoff synchronizes the existing radio before
            # creation. Deleting its key alone can leave the browser displaying
            # the previous account's route and swallow the next logout click.
            st.session_state['v79_pending_page'] = 'Watchlist'


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


def _render_personal_home(story: Mapping[str, Any] | None, *, routes: tuple[str, ...]) -> dict[str, str]:
    """Use the supplied admitted Home projection, never build/evaluate a fallback.

    Existing Home admission diagnostics and customer-authority checks remain
    independent of login. These checks do not certify new evidence or currentness.
    """
    from services.home_runtime_contract import build_home_runtime_contract
    try:
        if not story or not story.get('runtime_projection_contract'):
            raise ValueError('SUPPLIED_HOME_AUTHORITY_REQUIRED')
        projection = deepcopy(dict(story))
        runtime = build_home_runtime_contract(projection)
        if runtime.get('runtime_ready') is not True:
            raise ValueError('HOME_RUNTIME_UNAVAILABLE')
        cards = projection.get('cards')
        if not isinstance(cards, (list, tuple)):
            raise ValueError('SUPPLIED_HOME_INVENTORY_REQUIRED')
        tickers = []
        for card in cards:
            if not isinstance(card, Mapping):
                raise ValueError('INVALID_HOME_CARD')
            authority = customer_authority(card)
            ticker = str(card.get('ticker') or '').strip().upper()
            if authority.get('status') != 'AVAILABLE' or authority.get('ticker') != ticker:
                raise ValueError('HOME_CARD_NOT_PUBLISHED')
            tickers.append(ticker)
        if len(set(tickers)) != len(tickers):
            raise ValueError('AMBIGUOUS_HOME_INVENTORY')
        # Featured entries must be the same already-admitted cards, not a second
        # opportunity universe smuggled around the inventory boundary.
        for card in projection.get('home_featured_cards') or ():
            if not isinstance(card, Mapping) or card not in cards:
                raise ValueError('UNBOUND_HOME_FEATURED_CARD')
        projection['home_runtime_contract'] = runtime
        # A shared prebuilt projection must never import another workspace's
        # personal membership into this account. No shared file is consulted.
        projection['watchlist_cards'] = []
    except (TypeError, ValueError):
        st.info('The admitted Home opportunity snapshot is unavailable in this workspace. No market refresh or provider lookup was requested. Your personal watchlists remain available.')
        emit_page_interactive(st, 'Home')
        return {'status': 'HOME_UNAVAILABLE'}
    from ui.home_guidance_vnext import render_home_guidance_vnext
    # A held older Home renderer cannot enforce this restricted navigation.
    # Refuse it rather than calling without the boundary or reloading modules.
    try:
        compatible = 'navigation_routes' in inspect.signature(render_home_guidance_vnext).parameters
    except (TypeError, ValueError):
        compatible = False
    if not compatible:
        st.info('Home is temporarily unavailable while the workspace renderer updates. Your personal watchlists remain available.')
        emit_page_interactive(st, 'Home')
        return {'status': 'HOME_UNAVAILABLE'}
    st.caption('Retained admitted snapshot · source dates below are independent of your account session. This page does not refresh market data.')
    render_home_guidance_vnext(projection, authorized_internal=False, navigation_routes=routes)
    return {'status': 'HOME_RENDERED'}


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
        pages = ('Watchlist', 'Home', 'Research', 'Earnings', 'Account')
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
        required = {'Home': (Capability.HOME, Capability.TODAYS_OPPORTUNITIES),
                    'Research': (Capability.FULL_RESEARCH,),
                    'Earnings': (Capability.FULL_EARNINGS_INTELLIGENCE,)}.get(selected, ())
        if not set(required).issubset(current.capabilities):
            st.info('This feature is not enabled for your account. Your saved watchlists remain available.')
            return {'status': 'FEATURE_UNAVAILABLE'}
        if selected in {'Watchlist', 'Account'}:
            def logout():
                _clear_runtime_presentation()
                bindings.account.logout()
            account = PersonalAccountBindings(bindings.account.is_logged_in, bindings.account.login,
                                              logout, bindings.account.watchlists)
            result = render_personal_account(bindings=account, open_research=open_research)
        elif selected == 'Home':
            routes = tuple(page for page in pages if page not in {'Home', 'Research', 'Earnings'}
                           or (page == 'Research' and Capability.FULL_RESEARCH in current.capabilities)
                           or (page == 'Earnings' and Capability.FULL_EARNINGS_INTELLIGENCE in current.capabilities))
            result = _render_personal_home(bindings.home_story, routes=routes)
        elif selected == 'Research':
            result = _render_retained_research(bindings.research_rows)
        else:
            render_earnings(pd.DataFrame(bindings.earnings_rows), open_research=open_research,
                            transcript_cache_reader=bindings.transcript_cache)
            result = {'status': 'EARNINGS_RENDERED'}
        if selected in {'Watchlist', 'Account'}:
            emit_page_interactive(st, 'Watchlist Intelligence')
        return result
