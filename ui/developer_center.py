from __future__ import annotations
import json
from typing import Any, Iterable, Mapping
import pandas as pd
import streamlit as st

from agents.product_audit_agent import run_product_audit
from agents.runtime_qa_report_v3 import load_latest_runtime_qa_v3


def _issues(items, key):
    if not items:
        st.success("No issues detected.")
        return
    selected = st.multiselect(
        "Severity",
        ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default=["CRITICAL", "HIGH", "MEDIUM"],
        key=f"{key}_severity",
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
    tabs = st.tabs([
        "Pipeline Audit",
        "Runtime QA v3",
        "AI Content Integrity",
        "Controlled Fix Plan",
        "Run Instructions",
    ])

    with tabs[0]:
        report = run_product_audit(
            pipeline=pipeline,
            navigation_pages=navigation_pages,
            app_version=app_version,
        )
        st.metric("Pipeline Health", f"{report['health_score']}%")
        _issues(report.get("issues") or [], "pipeline")

    with tabs[1]:
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
            st.download_button(
                "Download Runtime QA v3 JSON",
                json.dumps(report, indent=2, default=str),
                "atlas_runtime_qa_v3.json",
                "application/json",
                use_container_width=True,
            )

    with tabs[2]:
        report = load_latest_runtime_qa_v3()
        integrity = (report or {}).get("ai_content_integrity") or {}
        st.metric("Summaries Reviewed", integrity.get("records_reviewed", 0))
        st.metric("Duplicate Pairs", len(integrity.get("duplicate_pairs") or []))
        scores = integrity.get("summary_scores") or []
        if scores:
            st.dataframe(pd.DataFrame(scores), hide_index=True, use_container_width=True)

    with tabs[3]:
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

    with tabs[4]:
        st.code(
            "python3 -m agents.atlas_runtime_qa_v3 "
            "--url https://stock-ai-dashboard.streamlit.app "
            "--output audit_results",
            language="bash",
        )
