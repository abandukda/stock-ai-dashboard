from streamlit.testing.v1 import AppTest


def test_retained_eps_render_preserves_zero_losses_and_converts_capture_clock():
    context = {
        "contract": "ATLAS_RETAINED_REPORTED_EPS_CONTEXT_V1", "status": "PARTIAL",
        "records": [
            {"period_end": "2026-07-31", "eps_actual": 0, "eps_estimate": None},
            {"period_end": "2026-04-30", "eps_actual": -1.25, "eps_estimate": 0},
        ],
        "source": {"provider": "FINNHUB_RETAINED_EVIDENCE", "captured_at": "2026-10-23T01:00:00+05:00",
                   "raw_evidence_id": "generated:eps:<img src=x>"},
    }
    app = AppTest.from_string('''
import streamlit as st
from ui.customer_research_v2 import _render_retained_reported_earnings
_render_retained_reported_earnings(st.session_state.context, ticker="NVDA")
''')
    app.session_state["context"] = context
    app.run()
    assert not app.exception
    rows = app.table[0].value
    assert rows["Actual EPS · provider units"].tolist() == ["0", "-1.25"]
    assert rows["Estimate EPS · basis unverified"].tolist() == ["Unavailable", "0"]
    text = " ".join(item.value for item in app.markdown)
    assert "Oct 22, 2026 · 8:00 PM UTC" in text
    assert "generated:eps:&lt;img src=x&gt;" in text
    assert "no earnings beat, miss or surprise is inferred" in app.info[0].value


def test_unavailable_retained_eps_does_not_render_a_factual_table():
    app = AppTest.from_string('''
from ui.customer_research_v2 import _render_retained_reported_earnings
_render_retained_reported_earnings({"status": "UNAVAILABLE", "records": []}, ticker="NVDA")
''').run()
    assert not app.exception
    assert not app.table
    assert not any("### Retained reported EPS" == item.value for item in app.markdown)
