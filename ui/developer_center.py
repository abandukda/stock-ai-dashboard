"""Atlas Developer Center."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

import pandas as pd
import streamlit as st

from agents.product_audit_agent import run_product_audit


def render_developer_center(
    *,
    pipeline: Mapping[str, Any],
    navigation_pages: Iterable[str],
    app_version: str = "",
) -> None:
    st.markdown("## Atlas Developer Center")
    st.caption(
        "Audits pipeline completeness, active navigation, decision consistency, "
        "valuation transparency, and customer-facing explanation quality."
    )

    report = run_product_audit(
        pipeline=pipeline,
        navigation_pages=navigation_pages,
        app_version=app_version,
    )

    counts = report["severity_counts"]
    metrics = st.columns(5)
    metrics[0].metric("System Health", f"{report['health_score']}%")
    metrics[1].metric("Critical", counts["critical"])
    metrics[2].metric("High", counts["high"])
    metrics[3].metric("Medium", counts["medium"])
    metrics[4].metric("Rows Inspected", report["rows_inspected"])

    st.warning(
        "Current audit mode checks pipeline data and product contracts. "
        "Automated browser inspection will be added in the next audit release."
    )

    issues = report.get("issues") or []
    if not issues:
        st.success("No pipeline or contract issues were detected.")
    else:
        severity_filter = st.multiselect(
            "Severity",
            ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
            default=["CRITICAL", "HIGH", "MEDIUM"],
            key="developer_audit_severity",
        )
        filtered = [
            item
            for item in issues
            if item["severity"] in severity_filter
        ]

        table = pd.DataFrame(
            [
                {
                    "Severity": item["severity"],
                    "Ticker": item.get("ticker") or "System",
                    "Category": item["category"],
                    "Issue": item["title"],
                    "Likely Area": item["likely_area"],
                }
                for item in filtered
            ]
        )
        if not table.empty:
            st.dataframe(
                table,
                hide_index=True,
                use_container_width=True,
            )

        for index, item in enumerate(filtered, start=1):
            label = (
                f"{item['severity']} · "
                f"{item.get('ticker') or 'System'} · "
                f"{item['title']}"
            )
            with st.expander(label):
                st.markdown(f"**Category:** {item['category']}")
                st.markdown(f"**Expected:** {item['expected']}")
                st.markdown(f"**Actual:** {item['actual']}")
                st.markdown(f"**Likely area:** `{item['likely_area']}`")
                st.markdown(f"**Recommended fix:** {item['recommendation']}")

    st.download_button(
        "Download audit JSON",
        data=json.dumps(report, indent=2, default=str),
        file_name="atlas_product_audit.json",
        mime="application/json",
        use_container_width=True,
    )


__all__ = ["render_developer_center"]
