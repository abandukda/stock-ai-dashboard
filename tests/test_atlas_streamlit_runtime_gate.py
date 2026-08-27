"""ATLAS_STREAMLIT_RUNTIME_GATE: real Streamlit session/widget semantics.

Run before recommending deployed QA after Research or navigation changes:

    python3 -m pytest -q tests/test_atlas_streamlit_runtime_gate.py

Unlike the pure critical gate, these tests execute through Streamlit AppTest and
therefore enforce the framework rule that instantiated widget keys are locked
for the remainder of the script run.
"""
from __future__ import annotations

import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
import streamlit as st
from engines.research_engine import begin_research_entry
from services.session_stability import (
    consume_navigation_handoff, consume_research_ticker_handoff,
)

PAGES = ["Home", "Research Any Ticker", "Ask AI"]
st.session_state.setdefault("authenticated", True)
st.session_state.setdefault("role", "viewer")
st.session_state.setdefault("user_role", "viewer")

page, pending_page = consume_navigation_handoff(
    st.session_state, PAGES, widget_key="atlas_runtime_nav",
)
page = st.radio("Navigation", PAGES, key="atlas_runtime_nav")
st.session_state["v73_page"] = page

if page == "Home":
    st.markdown("HOME_READY")
    for ticker in ("NVDA", "CRM", "EDU"):
        if st.button(f"Research {ticker}", key=f"home_{ticker}"):
            begin_research_entry(
                st.session_state, ticker, source="HOME_TIER_CARD",
                interaction_id=f"home-research-tier-{ticker.lower()}",
            )
            st.rerun()
elif page == "Research Any Ticker":
    consume_research_ticker_handoff(st.session_state, widget_key="typed_ticker")
    with st.form("research_ticker_form"):
        typed = st.text_input("Ticker", key="typed_ticker").strip().upper()
        submitted = st.form_submit_button("Research ticker")
    if submitted:
        entry = begin_research_entry(
            st.session_state, typed, source="DIRECT_TICKER_SUBMISSION",
            pending_navigation=False,
        )
        if not entry:
            st.session_state["active_research_ticker"] = typed
            st.session_state["research_status"] = "invalid"
            st.session_state["research_error"] = "invalid"
    if st.button("Home", key="research_home"):
        st.session_state["v79_pending_page"] = "Home"
        st.rerun()
    if st.button("Ask", key="research_ask"):
        st.session_state["v79_pending_page"] = "Ask AI"
        st.rerun()
    st.markdown("RESEARCH_READY")
    st.write("ACTIVE=" + str(st.session_state.get("active_research_ticker") or ""))
elif page == "Ask AI":
    st.markdown("ASK_READY")
    st.write("ASK_TICKER=" + str(st.session_state.get("active_research_ticker") or ""))
    if st.button("Back to Research", key="ask_research"):
        st.session_state["v79_pending_page"] = "Research Any Ticker"
        st.session_state["v79_pending_research_ticker"] = str(
            st.session_state.get("active_research_ticker") or ""
        )
        st.rerun()
'''


def _app() -> AppTest:
    app = AppTest.from_string(HARNESS, default_timeout=10)
    app.run()
    assert not app.exception
    return app


def _button(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def _go(app: AppTest, page: str) -> AppTest:
    app.radio(key="atlas_runtime_nav").set_value(page)
    app.run()
    assert not app.exception
    return app


def _submit(app: AppTest, ticker: str) -> AppTest:
    app.text_input(key="typed_ticker").set_value(ticker)
    _button(app, "Research ticker").click()
    app.run()
    assert not app.exception
    return app


def test_direct_research_transitions_obey_real_streamlit_widget_ownership():
    app = _go(_app(), "Research Any Ticker")
    for ticker in ("NVDA", "CRM", "EDU", "EDU"):
        _submit(app, ticker)
        assert app.session_state["active_research_ticker"] == ticker
        assert app.session_state["typed_ticker"] == ticker
        assert app.session_state["authenticated"] is True


def test_valid_invalid_valid_recovery_uses_canonical_state_not_widget_rewrite():
    app = _go(_app(), "Research Any Ticker")
    _submit(app, "NVDA")
    _submit(app, "INVALID123")
    assert app.session_state["research_status"] == "invalid"
    assert app.session_state["active_research_ticker"] == "INVALID123"
    _submit(app, "CRM")
    assert app.session_state["active_research_ticker"] == "CRM"
    assert app.session_state["research_status"] == "loading"


def test_home_research_home_different_research_consumes_pending_before_widgets():
    app = _app()
    _button(app, "Research CRM").click()
    app.run()
    assert not app.exception
    assert app.radio(key="atlas_runtime_nav").value == "Research Any Ticker"
    assert app.text_input(key="typed_ticker").value == "CRM"
    assert app.session_state["active_research_ticker"] == "CRM"
    _button(app, "Home").click()
    app.run()
    assert not app.exception
    _button(app, "Research EDU").click()
    app.run()
    assert not app.exception
    assert app.text_input(key="typed_ticker").value == "EDU"
    assert app.session_state["active_research_ticker"] == "EDU"
    assert app.session_state["authenticated"] is True


def test_research_ask_research_preserves_ticker_and_session():
    app = _go(_app(), "Research Any Ticker")
    _submit(app, "NVDA")
    _button(app, "Ask").click()
    app.run()
    assert not app.exception
    assert app.radio(key="atlas_runtime_nav").value == "Ask AI"
    assert app.session_state["active_research_ticker"] == "NVDA"
    _button(app, "Back to Research").click()
    app.run()
    assert not app.exception
    assert app.radio(key="atlas_runtime_nav").value == "Research Any Ticker"
    assert app.text_input(key="typed_ticker").value == "NVDA"
    assert app.session_state["authenticated"] is True


def test_active_fourteen_page_shell_has_no_known_widget_state_collision():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    final_functions = {
        node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert len(ast.literal_eval(next(
        node.value for node in ast.walk(final_functions["main"])
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "pages" for target in node.targets)
    ))) == 14
    research = ast.unparse(final_functions["render_research_any_ticker"])
    assert "key='typed_ticker'" in research
    assert 'st.session_state.update' not in research
    assert 'consume_research_ticker_handoff' in research
    navigation = ast.unparse(final_functions["render_v73_top_nav"])
    assert navigation.index("consume_navigation_handoff") < navigation.index("st.radio")

    # Audit every final (therefore active) top-level page/helper definition for
    # direct writes to a constant widget key after that widget is instantiated.
    widget_calls = {
        "text_input", "text_area", "radio", "selectbox", "multiselect",
        "slider", "checkbox", "number_input", "date_input",
    }
    collisions = []
    for function_name, function in final_functions.items():
        widgets: list[tuple[str, int]] = []
        writes: list[tuple[str, int]] = []
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "st"
                and node.func.attr in widget_calls
            ):
                key = next((item.value for item in node.keywords if item.arg == "key"), None)
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    widgets.append((key.value, node.lineno))
            targets = node.targets if isinstance(node, ast.Assign) else []
            for target in targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Attribute)
                    and isinstance(target.value.value, ast.Name)
                    and target.value.value.id == "st"
                    and target.value.attr == "session_state"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    writes.append((target.slice.value, node.lineno))
        collisions.extend(
            (function_name, key, widget_line, write_line)
            for key, widget_line in widgets
            for written_key, write_line in writes
            if key == written_key and write_line > widget_line
        )
    assert collisions == []


def test_runtime_gate_is_a_permanent_release_requirement():
    source = (ROOT / "tests/test_atlas_streamlit_runtime_gate.py").read_text(encoding="utf-8")
    assert "ATLAS_STREAMLIT_RUNTIME_GATE" in source
    assert "streamlit.testing.v1" in source
    assert "python3 -m pytest -q tests/test_atlas_streamlit_runtime_gate.py" in source
