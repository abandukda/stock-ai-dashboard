from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
import pandas as pd
import streamlit as st

from agents.product_audit_agent import run_product_audit
from agents.runtime_qa_report_v3 import load_latest_runtime_qa_v3


def _reset_severity(key):
    st.session_state[f"{key}_severity"] = ["CRITICAL", "HIGH", "MEDIUM"]


def _issues(items, key):
    if not items:
        st.success("No issues detected.")
        return
    selected = st.multiselect(
        "Severity",
        ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default=["CRITICAL", "HIGH", "MEDIUM"],
        key=f"{key}_severity",
        help="Filter detected issues by impact. Multiple selections are allowed; remove selections or use Reset Filters to clear the filter.",
    )
    st.button(
        "Reset Filters",
        key=f"{key}_reset_filters",
        help="Restore the default Critical, High, and Medium severity selection.",
        on_click=_reset_severity,
        args=(key,),
    )
    filtered = [item for item in items if item.get("severity") in selected]
    frame = pd.DataFrame([
        {
            "Severity": item.get("severity"),
            "Page": item.get("page"),
            "Ticker": item.get("ticker") or "",
            "Category": item.get("category"),
            "Actual": item.get("actual"),
        }
        for item in filtered
    ])
    if not frame.empty:
        st.dataframe(frame, hide_index=True, use_container_width=True)


def render_developer_center(
    *,
    pipeline: Mapping[str, Any],
    navigation_pages: Iterable[str],
    app_version: str = "",
):
    st.markdown("## Atlas Developer Center")
    st.caption(
        "Internal quality-control center for monitoring Atlas data, AI research, "
        "application reliability, and detected defects. This area does not generate "
        "investment recommendations; it monitors whether Atlas itself is working correctly."
    )
    st.info("This administrator/developer workspace remains in primary navigation for operational visibility; investor-facing decisions are produced elsewhere in Atlas.")
    deep_path = Path("audit_results/deep_qa/atlas_deep_qa.json")
    try:
        deep_report = json.loads(deep_path.read_text(encoding="utf-8")) if deep_path.exists() else None
    except Exception:
        deep_report = None
    if deep_report:
        health = deep_report.get("health") or {}
        domains = health.get("domains") or {}
        with st.expander("Deep QA Domain Health", expanded=False):
            st.caption("Separates application quality domains so one repeated root cause cannot hide which parts of Atlas are healthy. Scores are reduced by unique root causes weighted by severity and impact; 90%+ is healthy.")
            if domains:
                columns = st.columns(3)
                for index, (name, score) in enumerate(domains.items()):
                    columns[index % 3].metric(name, f"{score}%")
            st.metric("Overall Health", f"{health.get('overall', 0)}%", help=health.get("calculation") or "Mean of the displayed domain scores.")
    tabs = st.tabs([
        "Pipeline Audit",
        "Runtime QA v3",
        "AI Content Integrity",
        "Controlled Fix Plan",
        "Run Instructions",
    ])

    with tabs[0]:
        st.caption("Checks whether the market, financial, analyst, earnings and other data Atlas needs are successfully reaching the research engine.")
        report = run_product_audit(
            pipeline=pipeline,
            navigation_pages=navigation_pages,
            app_version=app_version,
        )
        st.metric(
            "Pipeline Health",
            f"{report['health_score']}%",
            help="Percentage of monitored data components currently passing Atlas data-quality checks. It is calculated from unique detected issues and monitored checks; higher is better, with 90%+ indicating a healthy pipeline.",
        )
        st.caption("Severity guide: CRITICAL may materially mislead; HIGH is important incomplete/incorrect behavior; MEDIUM is meaningful but does not invalidate research; LOW is minor presentation or usability impact.")
        _issues(report.get("issues") or [], "pipeline")
        st.caption("Next action: open the highest-severity unique issue, verify its affected source/component, then add the recommended regression test before repair.")

    with tabs[1]:
        st.caption("Simulates real user activity across Atlas to identify broken pages, buttons, navigation, layouts and research workflows.")
        report = load_latest_runtime_qa_v3()
        if not report:
            st.info("No Runtime QA v3 report found yet.")
        else:
            counts = report.get("severity_counts") or {}
            columns = st.columns(6)
            columns[0].metric("Health", f"{report.get('health_score', 0)}%")
            columns[1].metric("Pages", report.get("pages_inspected", 0))
            columns[2].metric("Critical", counts.get("CRITICAL", 0))
            columns[3].metric("High", counts.get("HIGH", 0))
            columns[4].metric("Medium", counts.get("MEDIUM", 0))
            columns[5].metric("Seconds", report.get("duration_seconds", 0))
            _issues(report.get("issues") or [], "runtime_v3")
            st.caption("Health reflects weighted detected runtime issues. A good run has all primary pages inspected, no failed journeys, and no critical browser errors.")
            st.download_button(
                "Download Runtime QA v3 JSON",
                json.dumps(report, indent=2, default=str),
                "atlas_runtime_qa_v3.json",
                "application/json",
                use_container_width=True,
            )

    with tabs[2]:
        st.caption("Checks Atlas research for missing information, repeated explanations, contradictions, suspicious values and other content-quality problems.")
        report = load_latest_runtime_qa_v3()
        integrity = (report or {}).get("ai_content_integrity") or {}
        st.metric("Summaries Reviewed", integrity.get("records_reviewed", 0))
        st.metric("Duplicate Pairs", len(integrity.get("duplicate_pairs") or []))
        scores = integrity.get("summary_scores") or []
        if scores:
            st.dataframe(pd.DataFrame(scores), hide_index=True, use_container_width=True)
        st.caption("Next action: review low-specificity summaries and grouped duplicate pairs to determine whether evidence mapping or templated synthesis is responsible.")

    with tabs[3]:
        st.caption("Groups detected problems into root causes and recommends which issues should be repaired first.")
        path = "audit_results/atlas_fix_plan.json"
        try:
            plan = json.loads(open(path, encoding="utf-8").read())
        except Exception:
            plan = None
        if not plan:
            st.info("Run Runtime QA v3 to generate the controlled fix plan.")
        else:
            st.warning(
                "The Fix Agent prepares replacement-file plans only. "
                "It never pushes directly to main."
            )
            st.dataframe(
                pd.DataFrame(plan.get("replacement_file_actions") or []),
                hide_index=True,
                use_container_width=True,
            )
            st.caption("Next action: repair one root cause at a time in severity order and rerun its recommended regression test; this tab never applies fixes automatically.")

    with tabs[4]:
        st.caption("Shows how Atlas QA tests are executed and how to interpret their results.")
        st.code(
            "python3 -m agents.atlas_runtime_qa_v3 "
            "--url https://stock-ai-dashboard.streamlit.app "
            "--output audit_results",
            language="bash",
        )
        st.caption("Run from the repository root. Review the generated JSON/Markdown reports and screenshots; PASS means the tested contract held, WARN needs review, and FAIL requires investigation.")
