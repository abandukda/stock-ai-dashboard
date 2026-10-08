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
    st.markdown(
        '<div class="atlas-report-card-hero"><div class="atlas-kicker">INTERNAL ONLY · access controlled</div>'
        '<h1>Prospective Report Card</h1><p>Immutable signal observations measured against SPY. '
        'Descriptive research operations only — Not a public performance claim.</p></div>',
        unsafe_allow_html=True,
    )
    a, b, c, d = st.columns(4)
    a.metric("Signals", report["signal_count"])
    b.metric("Observations", report["observation_count"])
    c.metric("SPY comparisons", report["spy_comparison_count"])
    d.metric("Ledger integrity", report["integrity"])
    st.markdown(
        '<div class="atlas-source-chips"><span class="atlas-certification-chip">Append-only ledger</span>'
        f'<span class="atlas-source-chip">Activated {report["activation_timestamp"]}</span>'
        f'<span class="atlas-source-chip">Ledger {report["ledger_tip_digest"][:12]}…</span>'
        f'<span class="atlas-source-chip">Backup {report["last_backup_status"]}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f'Next eligible observation: {report["next_eligible_observation"]}')
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
