"""Internal-only shadow position-monitoring view."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from services.position_management_dashboard import build_shadow_position_dashboard


def render_shadow_position_monitor(path: Path, *, authorized: bool) -> Mapping[str, Any]:
    report = build_shadow_position_dashboard(path, authorized=authorized)
    st.warning("SHADOW RESEARCH ONLY — NOT CUSTOMER VISIBLE")
    st.markdown('<span data-atlas-qa="shadow-position-monitor" data-atlas-customer-visible="false" '
                'aria-hidden="true" style="display:none">shadow-position-monitor</span>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.metric("Tracked episodes", len(report["positions"]))
    b.metric("Shadow observations", report["history_count"])
    c.metric("Ledger integrity", report["integrity"])
    st.caption(f'Activated {report["activation_timestamp"]} · Methodology {report["methodology_version"] or "Not activated"}')
    for item in report["positions"]:
        with st.expander(f'{item["ticker"]} · {item["position_instruction"]} · {item["scan_timestamp"]}'):
            left, right = st.columns(2)
            with left:
                st.markdown("**ORIGINAL SIGNAL**")
                st.markdown(f'**Signal ID:** `{html.escape(str(item["signal_id"]))}`  \n'
                            f'**Candidate:** `{html.escape(str(item["candidate_digest"]))}`  \n'
                            f'**Publication:** `{html.escape(str(item["publication_digest"]))}`  \n'
                            f'**Snapshot:** `{html.escape(str(item["evaluation_snapshot"]))}`')
            with right:
                st.markdown("**CURRENT ATLAS VIEW**")
                st.markdown(f'**Thesis:** {item["thesis_state"]}  \n'
                            f'**Valuation:** {item["valuation_state"]}  \n'
                            f'**Technical:** {item["technical_state"]}  \n'
                            f'**Data certainty:** {item["data_certainty"]}  \n'
                            f'**Review:** {"YES" if item["review_required"] else "NO"}')
            st.markdown(f'**Shadow Position State:** `{item["position_instruction"]}` · '
                        f'**ADD ELIGIBLE:** {"YES" if item["add_eligible"] else "NO"}')
            st.markdown("**Reason codes:** " + ", ".join(item["reason_codes"]))
            st.markdown("**Review reasons:** " + (", ".join(item["review_reason_codes"]) or "None"))
            st.caption(f'Rule table {item["rule_table_version"]} · Inputs {item["inputs_digest"][:12]}…')
    return report


def render_signal_shadow_context(item: Mapping[str, Any] | None) -> None:
    """Descriptive axes only; deliberately excludes TRIM/EXIT instruction."""
    if not item:
        st.caption("Shadow position context: not yet activated for this prospective signal.")
        return
    st.markdown("**Internal shadow context**")
    st.markdown(f'Thesis **{item["thesis_state"]}** · Valuation **{item["valuation_state"]}** · '
                f'Technical **{item["technical_state"]}** · Review **{"YES" if item["review_required"] else "NO"}**')


__all__ = ["render_shadow_position_monitor", "render_signal_shadow_context"]
