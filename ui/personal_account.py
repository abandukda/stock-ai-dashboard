"""Opt-in individual-account shell; no production identity/store is opened here.

A server composition root supplies native login/logout callbacks and the trusted
watchlist controller. UI login state controls presentation only. Every personal
read/write is independently authorized by that controller's current resolver.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import streamlit as st
from services.customer.watchlist_controller import PersonalWatchlistAccessError, PersonalWatchlistController
from ui.personal_watchlists import _clear_personal_widget_state, render_personal_watchlists


@dataclass(frozen=True)
class PersonalAccountBindings:
    """Server-owned dependencies, never built from browser/session/query fields."""
    is_logged_in: Callable[[], bool]
    login: Callable[[], None]
    logout: Callable[[], None]
    watchlists: PersonalWatchlistController


def render_personal_account(*, bindings: PersonalAccountBindings | None = None,
                            open_research: Callable[[str], None] | None = None) -> dict[str, str]:
    st.markdown('''<section class="atlas-account-welcome"><h1>Your ATLAS account</h1>
<p>Keep your company research in a private, personal workspace.</p></section>''', unsafe_allow_html=True)
    if bindings is None:
        _clear_personal_widget_state()
        st.info('Individual accounts are not available yet. Shared-password access does not open personal watchlists.')
        return {'status': 'PENDING_CONFIGURATION'}
    try:
        logged_in = bindings.is_logged_in() is True
    except Exception:
        _clear_personal_widget_state()
        st.warning('Account access is temporarily unavailable.')
        return {'status': 'UNAVAILABLE'}
    if not logged_in:
        _clear_personal_widget_state()
        st.write('Sign in with your invited account to save companies and return to your research.')
        if st.button('Sign in to ATLAS', key='atlas_account:login', use_container_width=True):
            try:
                bindings.login()
            except Exception:
                st.warning('Sign-in could not be started. Please try again later.')
        st.caption('Provider credentials are never shared with your account.')
        return {'status': 'SIGNED_OUT'}
    # Place logout before data rendering: a native logout may rerun or redirect.
    if st.button('Sign out', key='atlas_account:logout', use_container_width=True):
        _clear_personal_widget_state()
        try:
            bindings.logout()
        except Exception:
            st.warning('Sign-out could not be completed. Close this session and try again.')
            return {'status': 'SIGN_OUT_FAILED'}
        return {'status': 'SIGNED_OUT'}
    try:
        bindings.watchlists.snapshot()
    except PersonalWatchlistAccessError as exc:
        _clear_personal_widget_state()
        if str(exc) == 'ACCOUNT_NOT_REGISTERED':
            st.info('Your login is recognized, but access has not been provisioned. Ask the owner to confirm your invitation.')
            return {'status': 'PENDING_INVITATION'}
        st.warning('Your account session is unavailable. Sign out and sign in again, or contact the owner.')
        return {'status': 'SESSION_UNAVAILABLE'}
    except Exception:
        _clear_personal_widget_state()
        st.warning('Your personal workspace is temporarily unavailable.')
        return {'status': 'UNAVAILABLE'}
    st.caption('Your saved lists belong to your individual account. They do not place trades or change ATLAS recommendations.')
    return render_personal_watchlists(controller=bindings.watchlists, open_research=open_research)
