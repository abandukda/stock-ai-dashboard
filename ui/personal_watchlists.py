"""Unwired personal-watchlist surface; trusted controller injection is required."""
from __future__ import annotations
from typing import Callable
import streamlit as st
from services.customer.service import EntitlementError
from services.customer.watchlist_controller import PersonalWatchlistAccessError, PersonalWatchlistController

_PREFIX = "atlas_personal_watchlists:"
_OWNER_KEY = _PREFIX + "view_owner"


def _clear_personal_widget_state(keep_owner: str | None = None) -> None:
    previous = st.session_state.get(_OWNER_KEY)
    if keep_owner is None or previous != keep_owner:
        for key in list(st.session_state):
            if str(key).startswith(_PREFIX):
                del st.session_state[key]
    if keep_owner is not None:
        st.session_state[_OWNER_KEY] = keep_owner


def _pending() -> dict[str, str]:
    _clear_personal_widget_state()
    st.info("Personal watchlists require individual account access. Shared-password sessions cannot use personal saved lists.")
    return {"status": "PENDING_INDIVIDUAL_ACCESS"}


def _apply(operation) -> bool:
    try:
        operation()
        return True
    except PersonalWatchlistAccessError:
        _clear_personal_widget_state()
        st.rerun()
    except EntitlementError:
        st.info("Your account's watchlist or symbol limit has been reached.")
    except KeyError:
        st.warning("This watchlist or symbol is not available in your current account.")
    except ValueError:
        st.warning("Check the watchlist name or select a ticker from the available results.")
    except Exception:
        st.warning("Personal watchlists are temporarily unavailable. No other account's list is shown.")
    return False


def render_personal_watchlists(*, controller: PersonalWatchlistController | None = None,
                              open_research: Callable[[str], None] | None = None) -> dict[str, str]:
    """No controller is constructed from session/query fields or environment."""
    st.markdown('''<style>
    .atlas-personal-watchlist-head{padding:1.1rem;border:1px solid #28465e;border-radius:18px;
    background:linear-gradient(120deg,#10283b,#101b2b);color:#eef6ff;margin-bottom:1rem}
    .atlas-personal-watchlist-head h1{font-size:clamp(1.6rem,4vw,2.3rem);margin:.2rem 0}
    [class*="st-key-atlas_personal_watchlists"] button{min-height:44px}
    @media(max-width:700px){.atlas-personal-watchlist-head{padding:.85rem}}
    </style><section class="atlas-personal-watchlist-head"><small>Your research workspace</small>
    <h1>Personal watchlists</h1><p>Save companies, organize your research and return to the evidence.</p></section>''', unsafe_allow_html=True)
    if controller is None:
        return _pending()
    try:
        snapshot = controller.snapshot()
    except PersonalWatchlistAccessError:
        return _pending()
    except Exception:
        _clear_personal_widget_state()
        st.warning("Personal watchlists are temporarily unavailable.")
        return {"status": "UNAVAILABLE"}
    _clear_personal_widget_state(snapshot.view_key)
    key = _PREFIX + snapshot.view_key + ":"
    with st.expander("Create a watchlist", expanded=not snapshot.watchlists):
        name = st.text_input("Watchlist name", key=key + "create_name", max_chars=80)
        if st.button("Create watchlist", key=key + "create", use_container_width=True):
            if _apply(lambda: controller.create_watchlist(name, view_key=snapshot.view_key)):
                st.rerun()
    if not snapshot.watchlists:
        st.info("Your watchlists are empty. Create a list, then search the available company catalog to add a ticker.")
        return {"status": "EMPTY"}
    owned = {item.watchlist_id: item for item in snapshot.watchlists}
    selected = st.selectbox("Choose watchlist", list(owned), format_func=lambda value: owned[value].name,
                            key=key + "selected")
    try:
        detail = controller.read_watchlist(selected, view_key=snapshot.view_key)
    except PersonalWatchlistAccessError:
        _clear_personal_widget_state()
        st.rerun()
    except (KeyError, ValueError):
        st.warning("Select a watchlist belonging to your current account.")
        return {"status": "UNAVAILABLE"}
    except Exception:
        st.warning("This watchlist is temporarily unavailable.")
        return {"status": "UNAVAILABLE"}
    st.markdown("### " + detail.name.replace("$", r"\$"))
    st.caption(f"{len(detail.symbols)} saved companies" + (" · Default watchlist" if detail.is_default else ""))
    with st.expander("Manage this watchlist"):
        renamed = st.text_input("Rename watchlist", value=detail.name, key=key + selected + ":rename", max_chars=80)
        if st.button("Save name", key=key + selected + ":save_name", use_container_width=True):
            if _apply(lambda: controller.rename_watchlist(selected, renamed, view_key=snapshot.view_key)):
                st.rerun()
        if not detail.is_default and st.button("Make default", key=key + selected + ":default", use_container_width=True):
            if _apply(lambda: controller.set_default_watchlist(selected, view_key=snapshot.view_key)):
                st.rerun()
        confirmed = st.checkbox("Confirm deletion of this watchlist", key=key + selected + ":confirm_delete")
        if st.button("Delete watchlist", key=key + selected + ":delete", disabled=not confirmed, use_container_width=True):
            if _apply(lambda: controller.delete_watchlist(selected, view_key=snapshot.view_key)):
                st.rerun()
    query = st.text_input("Find a ticker or company", placeholder="Search the available company catalog", key=key + "query", max_chars=80)
    if query.strip():
        try:
            matches = controller.search_catalog(query, view_key=snapshot.view_key)
        except PersonalWatchlistAccessError:
            _clear_personal_widget_state()
            st.rerun()
        except Exception:
            matches = ()
            st.warning("Company search is temporarily unavailable.")
        if matches:
            lookup = {entry.ticker: entry for entry in matches}
            ticker = st.selectbox("Matching companies", list(lookup), format_func=lambda value: f"{value} · {lookup[value].company}", key=key + "match")
            if st.button("Add ticker", key=key + selected + ":add", use_container_width=True):
                if _apply(lambda: controller.add_ticker(selected, ticker, view_key=snapshot.view_key)):
                    st.rerun()
        else:
            st.info("No matching company is available in this catalog. No provider lookup was requested.")
    if not detail.symbols:
        st.info("No companies saved in this watchlist yet. Search above to add your first ticker.")
    for item in detail.symbols:
        with st.container(border=True):
            st.markdown("**" + item.ticker + "** · " + item.company.replace("$", r"\$"))
            st.caption("Certified Research available" if item.research_available else "Certified Research is unavailable for this saved symbol.")
            if st.button("Open Research — " + item.ticker, key=key + selected + ":research:" + item.ticker,
                         disabled=not item.research_available or open_research is None, use_container_width=True):
                def navigate():
                    ticker = controller.research_ticker(selected, item.ticker, view_key=snapshot.view_key)
                    open_research(ticker)
                _apply(navigate)
            if st.button("Remove " + item.ticker, key=key + selected + ":remove:" + item.ticker, use_container_width=True):
                if _apply(lambda: controller.remove_ticker(selected, item.ticker, view_key=snapshot.view_key)):
                    st.rerun()
    return {"status": "AVAILABLE"}
