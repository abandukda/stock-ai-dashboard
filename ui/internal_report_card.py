"""Admin-only read-only internal prospective Report Card UI."""
from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import streamlit as st

from services.report_card_dashboard import build_internal_report_card
from services.position_management_dashboard import build_shadow_position_dashboard
from ui.internal_position_monitor import render_shadow_position_monitor, render_signal_shadow_context


REPORT_CARD_VIEW_OVERVIEW = "OVERVIEW"
REPORT_CARD_VIEW_DETAIL = "DETAIL"
REPORT_CARD_VIEW_KEY = "report_card_view_mode"
REPORT_CARD_SELECTED_SIGNAL_KEY = "report_card_selected_signal_id"


def normalize_report_card_view_state(
    session_state: MutableMapping[str, Any], valid_signal_ids: Sequence[str]
) -> tuple[str, str | None]:
    """Normalize Report Card view ownership without inventing a detail target."""
    valid_ids = {str(item) for item in valid_signal_ids if item}
    mode = str(session_state.get(REPORT_CARD_VIEW_KEY) or "").upper()
    selected_id = session_state.get(REPORT_CARD_SELECTED_SIGNAL_KEY)
    selected_id = str(selected_id) if selected_id else None

    if mode == REPORT_CARD_VIEW_DETAIL and selected_id in valid_ids:
        return REPORT_CARD_VIEW_DETAIL, selected_id

    session_state[REPORT_CARD_VIEW_KEY] = REPORT_CARD_VIEW_OVERVIEW
    session_state.pop(REPORT_CARD_SELECTED_SIGNAL_KEY, None)
    return REPORT_CARD_VIEW_OVERVIEW, None


def open_report_card_overview(session_state: MutableMapping[str, Any]) -> None:
    session_state[REPORT_CARD_VIEW_KEY] = REPORT_CARD_VIEW_OVERVIEW
    session_state.pop(REPORT_CARD_SELECTED_SIGNAL_KEY, None)


def open_report_card_detail(session_state: MutableMapping[str, Any], signal_id: str) -> None:
    exact_id = str(signal_id or "").strip()
    if not exact_id:
        open_report_card_overview(session_state)
        return
    session_state[REPORT_CARD_SELECTED_SIGNAL_KEY] = exact_id
    session_state[REPORT_CARD_VIEW_KEY] = REPORT_CARD_VIEW_DETAIL


def _percent(value: Any) -> str:
    return "Pending" if value is None else f"{float(value) * 100:.2f}%"


def _money(value: Any) -> str:
    return "Unavailable" if value is None else f"${float(value):,.2f}"


def _score(value: Any) -> str:
    return "Unavailable" if value is None else f"{float(value):.2f}"


def _render_signal_detail(detail: Mapping[str, Any]) -> None:
    original = detail["original_signal"]
    current = detail["current_market_state"]
    profile = detail["company_profile"]
    ticker = html.escape(str(detail.get("ticker") or ""))
    company = html.escape(str(detail.get("company_name") or ticker))
    digest_sections = {str(item.get("title") or ""): item for item in detail.get("digest") or ()}
    contextual_available = any(item.get("status") == "AVAILABLE" for item in digest_sections.values())
    earnings_status = str((digest_sections.get("Earnings and management") or {}).get("status") or "UNAVAILABLE")
    news_status = "AVAILABLE" if contextual_available else "UNAVAILABLE"
    profile_status = "AVAILABLE" if profile.get("source") not in (None, "", "UNAVAILABLE") else "UNAVAILABLE"
    performance_status = "AVAILABLE" if any(item.get("status") == "AVAILABLE" for item in detail.get("performance") or ()) else "PENDING"
    st.markdown("""<style>
    .atlas-signal-detail{display:grid;gap:.8rem}.atlas-signal-detail-head{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;padding:1rem 1.1rem;border:1px solid rgba(94,234,212,.22);border-radius:16px;background:linear-gradient(145deg,rgba(15,23,42,.94),rgba(20,35,50,.88))}
    .atlas-signal-detail-head small,.atlas-detail-label{color:#77d7c4;letter-spacing:.1em;font-size:.68rem;font-weight:700}.atlas-signal-detail-head h2{margin:.18rem 0;font-size:1.45rem}.atlas-signal-detail-head p{margin:0;color:#9eabba;font-size:.8rem}.atlas-live-state{text-align:right}.atlas-live-state b{display:block;color:#e7edf5}.atlas-live-state span{font-size:.72rem;color:#8c9bad}
    .atlas-signal-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.45rem}.atlas-signal-metrics article{padding:.72rem;border:1px solid rgba(148,163,184,.16);border-radius:12px;background:rgba(15,23,42,.7)}.atlas-signal-metrics small{display:block;color:#8998aa;font-size:.7rem}.atlas-signal-metrics b{display:block;margin-top:.18rem;color:#edf3f8;font-size:.95rem}
    .atlas-context-flag{display:inline-flex;padding:.2rem .42rem;border-radius:999px;background:rgba(148,163,184,.1);color:#91a1b3;font-size:.62rem;letter-spacing:.06em}.atlas-profile-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem}.atlas-profile-grid div{padding:.6rem;border-radius:10px;background:rgba(30,41,59,.45)}.atlas-profile-grid small,.atlas-profile-grid b{display:block}.atlas-profile-grid small{color:#8e9bad;font-size:.68rem}.atlas-profile-grid b{margin-top:.18rem;font-size:.86rem}
    @media(max-width:760px){.atlas-signal-detail-head{display:grid}.atlas-live-state{text-align:left}.atlas-signal-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-profile-grid{grid-template-columns:1fr}.atlas-signal-detail-head h2{font-size:1.25rem}}
    </style>""", unsafe_allow_html=True)
    st.markdown(
        f'<div class="atlas-signal-detail" data-atlas-qa="report-card-signal-detail" '
        f'data-atlas-report-card-view="{REPORT_CARD_VIEW_DETAIL}" '
        f'data-atlas-signal-id="{html.escape(str(detail.get("signal_id") or ""))}" '
        f'data-atlas-ticker="{ticker}" data-atlas-snapshot="{html.escape(str(original.get("evaluation_snapshot_id") or ""))}" '
        f'data-atlas-action="{html.escape(str(original.get("action") or ""))}" '
        f'data-atlas-fair-value="{html.escape(str(original.get("atlas_fair_value") or ""))}" '
        f'data-atlas-opportunity="{html.escape(str(original.get("opportunity") or ""))}" '
        f'data-atlas-confidence="{html.escape(str(original.get("confidence") or ""))}" '
        f'data-atlas-candidate-digest="{html.escape(str(original.get("candidate_digest") or ""))}" '
        f'data-atlas-publication-digest="{html.escape(str(original.get("publication_digest") or ""))}" '
        f'data-atlas-contextual-evidence="{news_status}" data-atlas-earnings-evidence="{earnings_status}" '
        f'data-atlas-company-profile="{profile_status}" data-atlas-performance-evidence="{performance_status}" '
        f'data-atlas-context-classification="{detail["context_classification"]}">'
        '<section class="atlas-signal-detail-head"><div><small>ORIGINAL CERTIFIED SIGNAL</small>'
        f'<h2>{ticker} · {company}</h2><p>{html.escape(str(original.get("timestamp") or "Unavailable"))}</p></div>'
        f'<div class="atlas-live-state"><small>CURRENT MARKET STATE</small><b>{_money(current.get("price"))}</b>'
        f'<span>{html.escape(str(current.get("status") or "UNAVAILABLE"))} · not a live quote</span>'
        f'<span>vs reference: {_percent(current.get("distance_to_reference_pct") / 100 if current.get("distance_to_reference_pct") is not None else None)} · '
        f'vs Fair Value: {_percent(current.get("distance_to_fair_value_pct") / 100 if current.get("distance_to_fair_value_pct") is not None else None)}</span></div></section>'
        '<section class="atlas-signal-metrics">'
        f'<article><small>Original Action</small><b>{html.escape(str(original.get("action") or "Unavailable"))}</b></article>'
        f'<article><small>Reference Price</small><b>{_money(original.get("reference_price"))}</b></article>'
        f'<article><small>ATLAS Fair Value</small><b>{_money(original.get("atlas_fair_value"))}</b></article>'
        f'<article><small>Opportunity</small><b>{_score(original.get("opportunity"))}</b></article>'
        f'<article><small>Confidence</small><b>{_score(original.get("confidence"))}</b></article>'
        f'<article><small>Observations</small><b>{sum(x["status"] == "AVAILABLE" for x in detail["performance"])}</b></article>'
        '</section></div>', unsafe_allow_html=True,
    )

    st.subheader("Performance by registered horizon")
    st.dataframe([{
        "Horizon": f'{item["horizon_sessions"]} sessions',
        "Status": "Pending" if item["status"] == "PENDING" else item["status"],
        "Observed price": _money(item["observed_price"]) if item["observed_price"] is not None else "Pending",
        "Signal return": _percent(item["stock_return"]),
        "SPY return": _percent(item["spy_return"]),
        "Relative performance": _percent(item["excess_return"]),
        "Corporate action": item["corporate_action_status"],
    } for item in detail["performance"]], width="stretch", hide_index=True)

    st.subheader("ATLAS Signal Digest")
    for section in detail["digest"]:
        st.markdown(f'**{section["title"]}**  \n{section["text"]}')
        st.markdown(f'<span class="atlas-context-flag">{section["context_classification"]}</span>', unsafe_allow_html=True)

    st.subheader("Original thesis and view-change conditions")
    thesis = detail["original_thesis"]
    st.markdown("\n".join(f"- {item}" for item in thesis) if thesis else "No approved thesis narrative is available.")
    conditions = detail["view_change_conditions"]
    st.markdown("**Conditions that could change the view**")
    st.markdown("\n".join(f"- {item}" for item in conditions) if conditions else "No approved structured conditions are available.")
    shadow_path = os.getenv("ATLAS_POSITION_SHADOW_LEDGER", "").strip()
    shadow_item = None
    if shadow_path and Path(shadow_path).is_file():
        shadow_item = build_shadow_position_dashboard(Path(shadow_path), authorized=True)["latest_by_signal_id"].get(
            str(detail.get("signal_id") or "")
        )
    render_signal_shadow_context(shadow_item)

    with st.expander(f'About {detail.get("company_name") or detail.get("ticker")}', expanded=False):
        items = (
            ("Company", profile.get("company_name")), ("Sector", profile.get("sector")),
            ("Industry", profile.get("industry")), ("Market cap", _money(profile.get("market_cap"))),
            ("Leadership", profile.get("leadership")), ("Headquarters", profile.get("headquarters")),
            ("Founded", profile.get("founded")), ("Employees", profile.get("employees")),
            ("Source", profile.get("source")), ("Source timestamp", profile.get("source_timestamp")),
            ("Freshness", profile.get("freshness")),
        )
        st.markdown('<div class="atlas-profile-grid">' + "".join(
            f'<div><small>{html.escape(label)}</small><b>{html.escape(str(value if value not in (None, "") else "Unavailable"))}</b></div>'
            for label, value in items
        ) + '</div>', unsafe_allow_html=True)
    with st.expander("Event timeline", expanded=False):
        st.info(detail["event_timeline_status"])
    with st.expander("Evidence and audit identity", expanded=False):
        st.markdown(
            f'**Authority:** {detail["authority_status"]}  \n'
            f'**Candidate:** `{original.get("candidate_digest")}`  \n'
            f'**Publication:** `{original.get("publication_digest")}`  \n'
            f'**Evaluation snapshot:** `{original.get("evaluation_snapshot_id")}`  \n'
            f'**Generation:** {detail["generation_mode"]}  \n'
            f'**Context classification:** `{detail["context_classification"]}`'
        )
    st.subheader("What Drove the Move")
    st.info(detail["move_attribution"]["text"])
    st.markdown("**Positive drivers**")
    st.markdown("\n".join(f'- {item}' for item in detail["move_attribution"]["positive_drivers"]) or "- Not attributable from approved evidence.")
    st.markdown("**Negative drivers**")
    st.markdown("\n".join(f'- {item}' for item in detail["move_attribution"]["negative_drivers"]) or "- Not attributable from approved evidence.")
    st.markdown("**Uncertain / not attributable**")
    st.markdown("\n".join(f'- {item}' for item in detail["move_attribution"]["uncertain_or_not_attributable"]))


def render_internal_report_card(ledger_path: Path, *, authorized: bool) -> Mapping[str, Any]:
    report = build_internal_report_card(ledger_path, authorized=authorized, authority_root=Path("."))
    st.markdown('<span data-atlas-qa="internal-report-card" data-atlas-customer-visible="false" '
                'aria-hidden="true" style="display:none">internal-report-card</span>', unsafe_allow_html=True)
    st.markdown(
        '<div class="atlas-report-card-hero"><div class="atlas-kicker">INTERNAL ONLY · access controlled</div>'
        '<h1>Prospective Report Card</h1><p>Immutable signal observations measured against SPY. '
        'Signal tracking only — tracked recommendations are not funded model-portfolio purchases. '
        'Descriptive research operations only — Not a public performance claim.</p></div>',
        unsafe_allow_html=True,
    )
    view_mode, selected_id = normalize_report_card_view_state(
        st.session_state,
        [item["signal_id"] for item in report["signal_details"]],
    )
    selected = next((item for item in report["signal_details"] if item["signal_id"] == selected_id), None)
    if view_mode == REPORT_CARD_VIEW_DETAIL and selected is not None:
        if st.button("← Back to Report Card", key="report_card_back_to_overview"):
            open_report_card_overview(st.session_state)
            st.rerun()
        _render_signal_detail(selected)
        return report

    a, b, c, d = st.columns(4)
    a.metric("Signals", report["signal_count"])
    b.metric("Observations", report["observation_count"])
    c.metric("Open signals", report["open_signal_count"])
    d.metric("SPY comparisons", report["spy_comparison_count"])
    st.markdown(
        f'<span data-atlas-qa="report-card-overview" '
        f'data-atlas-report-card-view="{REPORT_CARD_VIEW_OVERVIEW}" '
        f'data-atlas-signal-count="{int(report["signal_count"])}" '
        f'data-atlas-observation-count="{int(report["observation_count"])}" '
        f'data-atlas-open-signal-count="{int(report["open_signal_count"])}" '
        f'data-atlas-spy-comparison-count="{int(report["spy_comparison_count"])}" '
        f'data-atlas-ledger-integrity="{html.escape(str(report["integrity"]))}" '
        f'data-atlas-backup-status="{html.escape(str(report["last_backup_status"]))}" '
        f'data-atlas-activation-timestamp="{html.escape(str(report["activation_timestamp"] or ""))}" '
        f'data-atlas-next-observation="{html.escape(str(report["next_eligible_observation"]))}" '
        'aria-hidden="true" style="display:none">report-card-overview</span>',
        unsafe_allow_html=True,
    )
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
            if st.button("View Signal Digest →", key=f'report_card_signal_{signal["signal_id"]}'):
                open_report_card_detail(st.session_state, signal["signal_id"])
                st.rerun()
    st.caption("Sample sizes are shown per horizon. Missing and not-yet-matured observations remain explicit.")
    shadow_path = os.getenv("ATLAS_POSITION_SHADOW_LEDGER", "").strip()
    st.subheader("Shadow Position Monitoring")
    if shadow_path and Path(shadow_path).is_file():
        render_shadow_position_monitor(Path(shadow_path), authorized=authorized)
    else:
        st.info("Shadow position tracking is not yet prospectively activated. No historical states are backfilled.")
    return report


__all__ = [
    "REPORT_CARD_SELECTED_SIGNAL_KEY", "REPORT_CARD_VIEW_DETAIL", "REPORT_CARD_VIEW_KEY",
    "REPORT_CARD_VIEW_OVERVIEW", "normalize_report_card_view_state", "open_report_card_detail",
    "open_report_card_overview", "render_internal_report_card",
]
