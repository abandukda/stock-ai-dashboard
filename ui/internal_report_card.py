"""Admin-only read-only internal prospective Report Card UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from services.report_card_dashboard import build_internal_report_card


def render_internal_report_card(ledger_path: Path, *, authorized: bool) -> Mapping[str, Any]:
    report = build_internal_report_card(ledger_path, authorized=authorized)
    st.markdown('<span data-atlas-qa="internal-report-card" data-atlas-customer-visible="false" '
                'aria-hidden="true" style="display:none">internal-report-card</span>', unsafe_allow_html=True)
    st.title("Internal Prospective Report Card")
    st.warning("INTERNAL ONLY · Prospective and descriptive. Not a public performance claim.")
    a, b, c, d = st.columns(4)
    a.metric("Signals", report["signal_count"])
    b.metric("Observations", report["observation_count"])
    c.metric("SPY comparisons", report["spy_comparison_count"])
    d.metric("Ledger integrity", report["integrity"])
    st.caption(f'Activated {report["activation_timestamp"]} · Ledger tip {report["ledger_tip_digest"][:16]}…')
    coverage_rows = [
        {"Horizon": f"{h} sessions", **values} for h, values in report["coverage"].items()
    ]
    st.subheader("Matured horizon coverage")
    st.dataframe(coverage_rows, width="stretch", hide_index=True)
    st.subheader("Signals and observations")
    st.dataframe(report["rows"], width="stretch", hide_index=True)
    st.caption("Sample sizes are shown per horizon. Missing and not-yet-matured observations remain explicit.")
    return report


__all__ = ["render_internal_report_card"]
