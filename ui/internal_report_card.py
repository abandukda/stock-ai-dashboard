"""Admin-only read-only internal prospective Report Card UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from services.report_card_dashboard import build_internal_report_card


def _percent(value: Any) -> str:
    return "Pending" if value is None else f"{float(value) * 100:.2f}%"


def render_internal_report_card(ledger_path: Path, *, authorized: bool) -> Mapping[str, Any]:
    report = build_internal_report_card(ledger_path, authorized=authorized)
    st.markdown('<span data-atlas-qa="internal-report-card" data-atlas-customer-visible="false" '
                'aria-hidden="true" style="display:none">internal-report-card</span>', unsafe_allow_html=True)
    st.markdown(
        '<div class="atlas-report-card-hero"><div class="atlas-kicker">INTERNAL ONLY · access controlled</div>'
        '<h1>Prospective Report Card</h1><p>Immutable signal observations measured against SPY. '
        'Signal tracking only — tracked recommendations are not funded model-portfolio purchases. '
        'Descriptive research operations only — Not a public performance claim.</p></div>',
        unsafe_allow_html=True,
    )
    a, b, c, d = st.columns(4)
    a.metric("Signals", report["signal_count"])
    b.metric("Observations", report["observation_count"])
    c.metric("Open signals", report["open_signal_count"])
    d.metric("SPY comparisons", report["spy_comparison_count"])
    st.markdown(
        '<div class="atlas-source-chips"><span class="atlas-certification-chip">Append-only ledger</span>'
        f'<span class="atlas-source-chip">Activated {report["activation_timestamp"]}</span>'
        f'<span class="atlas-source-chip">Ledger {report["ledger_tip_digest"][:12]}…</span>'
        f'<span class="atlas-source-chip">Backup {report["last_backup_status"]}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f'Next eligible observation: {report["next_eligible_observation"]}')
    st.markdown(f'**Ledger integrity:** {report["integrity"]} · **Admission integrity:** '
                f'{report["admission_integrity"]} · **Backup status:** {report["last_backup_status"]}')
    if report["admission_defects"]:
        st.error("Signal-admission QA failed: " + ", ".join(report["admission_defects"]))
    coverage_rows = [
        {"Horizon": f"{h} sessions", **values} for h, values in report["coverage"].items()
    ]
    st.subheader("Matured horizon coverage")
    st.dataframe(coverage_rows, width="stretch", hide_index=True)
    st.subheader("Signal admission and observation detail")
    for signal in report["signals"]:
        with st.expander(f'{signal["ticker"]} · {signal["original_action"]} · {signal["observation_count"]} observations'):
            st.markdown(
                f'**Signal ID:** `{signal["signal_id"]}`  \n'
                f'**First seen:** {signal["signal_timestamp"]}  \n'
                f'**Reference price:** {signal["reference_price"]} · {signal["reference_price_timestamp"]}  \n'
                f'**Admission:** {signal["admission_reason"]} · publication eligible: '
                f'{signal["customer_publication_eligible_at_issuance"]}  \n'
                f'**Candidate:** `{signal["candidate_digest"]}`  \n'
                f'**Publication:** `{signal["publication_digest"]}`  \n'
                f'**Evaluation snapshot:** `{signal["evaluation_snapshot_id"]}`  \n'
                f'**Horizons:** {", ".join(str(item) for item in signal["registered_horizons"])} sessions · '
                f'next: {signal["next_eligible_horizon"] if signal["next_eligible_horizon"] is not None else "Complete"}  \n'
                f'**Corporate action:** {signal["corporate_action_state"]}'
            )
            rows = []
            for item in report["rows"]:
                if item["signal_id"] != signal["signal_id"]:
                    continue
                rows.append({
                    "Horizon": f'{item["horizon_sessions"]} sessions',
                    "Status": "Pending" if item["status"] == "NOT_MATURED_OR_NOT_OBSERVED" else item["status"],
                    "Observed price": (f'${float(item["observed_price"]):,.2f}'
                                       if item["observed_price"] is not None else "Not yet observed"),
                    "Signal return": _percent(item["stock_return"]), "SPY return": _percent(item["spy_return"]),
                    "Relative performance": _percent(item["excess_return"]),
                    "Observed at": item["observed_at"] or "Not yet observed",
                })
            st.dataframe(rows, width="stretch", hide_index=True)
    st.caption("Sample sizes are shown per horizon. Missing and not-yet-matured observations remain explicit.")
    return report


__all__ = ["render_internal_report_card"]
