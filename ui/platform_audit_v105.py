
"""Atlas V105 Platform Audit Agent UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import pandas as pd
import streamlit as st

from agents.platform_audit_agent_v105 import run_platform_audit


def render_v105_platform_audit(
    pipeline: Mapping[str, Any] | None = None,
) -> None:
    st.markdown("## Atlas Platform Audit Agent")
    st.caption(
        "Read-only scan of imports, exports, routes, UI surfaces, "
        "repository structure, Streamlit runtime hazards, and pipeline quality."
    )

    if st.button(
        "Run complete Atlas audit",
        type="primary",
        use_container_width=True,
        key="run_v105_platform_audit",
    ) or "v105_platform_audit" not in st.session_state:
        with st.spinner("Scanning Atlas…"):
            st.session_state["v105_platform_audit"] = run_platform_audit(
                Path.cwd(), pipeline
            )

    report = st.session_state.get("v105_platform_audit")
    if not report:
        return

    counts = report.get("counts") or {}
    cols = st.columns(5)
    cols[0].metric("Status", report.get("status"))
    cols[1].metric("Critical", counts.get("CRITICAL", 0))
    cols[2].metric("High", counts.get("HIGH", 0))
    cols[3].metric("Medium", counts.get("MEDIUM", 0))
    cols[4].metric("Files Scanned", report.get("files_scanned", 0))

    findings = report.get("findings") or []
    st.markdown("### Prioritized Fix List")
    if not findings:
        st.success("No automated findings were detected.")
    for index, finding in enumerate(findings, start=1):
        with st.container(border=True):
            st.markdown(
                f"**{index}. {finding.get('severity')} · "
                f"{finding.get('title')}**"
            )
            st.write(finding.get("detail"))
            if finding.get("file"):
                location = finding["file"]
                if finding.get("line"):
                    location += f":{finding['line']}"
                st.caption(f"Location: {location}")
            if finding.get("recommended_fix"):
                st.info("Recommended fix: " + finding["recommended_fix"])

    inventory = report.get("ui_inventory") or {}
    st.markdown("### UI Surface Inventory")
    st.dataframe(
        pd.DataFrame(
            [
                {"Surface": key.replace("_", " ").title(), "Count": value}
                for key, value in (inventory.get("totals") or {}).items()
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    with st.expander("Files containing Streamlit surfaces", expanded=False):
        st.dataframe(
            pd.DataFrame(inventory.get("files") or []),
            hide_index=True,
            use_container_width=True,
        )

    pipeline_report = report.get("pipeline") or {}
    st.markdown("### Current Pipeline Health")
    cols = st.columns(3)
    cols[0].metric("Ranked Rows", pipeline_report.get("ranked_count", 0))
    cols[1].metric("Research Candidates", pipeline_report.get("candidate_count", 0))
    cols[2].metric("Rows With Earnings Dates", pipeline_report.get("earnings_date_count", 0))
    st.caption(
        "Coverage values currently in the pipeline: "
        + (
            ", ".join(
                str(value)
                for value in pipeline_report.get("coverage_unique_values", [])[:20]
            )
            or "None"
        )
    )

    st.markdown("### Manual Browser Checks")
    st.write(
        "After each deployment, click every primary navigation page, open and "
        "close one research report, toggle earnings and methodology, change all "
        "filters, and verify the mobile layout. Static analysis cannot simulate "
        "every browser interaction."
    )


__all__ = ["render_v105_platform_audit"]
