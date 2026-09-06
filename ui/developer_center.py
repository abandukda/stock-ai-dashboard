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


def _render_full_qa_status(publication_manifest: Mapping[str, Any]) -> None:
    """Render certification independently of optional methodology-health loaders."""
    with st.expander("Full-Universe QA Certification", expanded=True):
        qa = dict(publication_manifest.get("qa_certification") or {})
        if not qa:
            st.info("No full-universe QA certification has been promoted yet.")
            return
        headline = st.columns(4)
        headline[0].metric("Last QA Run", qa.get("generated_at", "Not available"))
        headline[1].metric("Dataset Gate", qa.get("dataset_certification_status", qa.get("publication_gate_status", "NOT AVAILABLE")))
        headline[2].metric("QA Engine", qa.get("qa_engine_status", "NOT AVAILABLE"))
        headline[3].metric("Blocking Findings", qa.get("blocking_issue_count", 0))
        coverage = st.columns(4)
        coverage[0].metric("Certified", qa.get("certified_count", 0))
        coverage[1].metric("High Uncertainty", qa.get("high_uncertainty_count", 0))
        coverage[2].metric("Screenshots", qa.get("screenshot_count", 0))
        coverage[3].metric("Visual Failures", qa.get("visual_failure_count", 0))
        severity = dict(qa.get("severity_counts") or {})
        cols = st.columns(5)
        for index in range(5):
            cols[index].metric(f"P{index}", severity.get(f"P{index}", 0))
        if qa.get("action_distribution"):
            st.caption("Canonical Action distribution")
            st.dataframe(pd.DataFrame([{"Action": key, "Count": value} for key, value in qa["action_distribution"].items()]), hide_index=True, use_container_width=True)
        if qa.get("artifact_link"):
            st.link_button("Open QA Artifact Run", qa["artifact_link"], use_container_width=True)
        st.caption(f"Certification engine {qa.get('version', 'Not available')} · Run {qa.get('run_id', 'Not available')}")


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
    manifest_path = Path("publication_manifest.json")
    try:
        _render_full_qa_status(json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {})
    except Exception:
        st.warning("Full-universe QA certification status is temporarily unavailable.")
    try:
        from services.methodology_health import methodology_health
        artifact = json.loads(Path("market_full_scan.json").read_text(encoding="utf-8"))
        from services.volume_screener import build_volume_screener
        snapshots_path=Path("performance_snapshots.jsonl")
        snapshot_count=sum(1 for line in snapshots_path.read_text().splitlines() if line.strip()) if snapshots_path.exists() else 0
        from services.model_validation import read_jsonl,regression_alerts,validation_report
        snapshot_rows=read_jsonl(snapshots_path);outcome_rows=read_jsonl(Path("performance_outcomes.jsonl"))
        matured_snapshot_count=len({row.get("snapshot_id") for row in outcome_rows})
        governed = methodology_health(artifact if isinstance(artifact, list) else [],performance_snapshot_count=snapshot_count,matured_performance_count=matured_snapshot_count)
        volume_rows=build_volume_screener(artifact if isinstance(artifact,list) else [])
        from services.canonical_data_validation import validation_health
        valuation_health=validation_health(artifact if isinstance(artifact,list) else [])
        manifest_path=Path("publication_manifest.json")
        publication_manifest=json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        with st.expander("Institutional Methodology Health", expanded=True):
            st.caption(f"Registry {governed['methodology_registry_version']} · Valuation {governed['valuation_methodology_version']} · Macro assumptions {governed['macro_assumption_version']}")
            columns=st.columns(4)
            for index,(label,key) in enumerate((("V2 Published","published_count"),("Stale Evidence","stale_evidence_count"),("High Dispersion","high_model_dispersion_count"),("High Terminal Dependence","high_terminal_dependence_count"),("WACC Below Treasury","wacc_below_risk_free_count"),("Single Method","single_model_count"),("Version Mismatches","methodology_mismatch_count"),("Home/Research Mismatches","home_research_mismatch_count"))):
                columns[index%4].metric(label,governed[key])
            more=st.columns(4);more[0].metric("Performance Snapshots",snapshot_count);more[1].metric("Matured Performance",governed["matured_performance_count"]);more[2].metric("Volume Candidates",len(volume_rows));more[3].metric("Breakouts",sum(x["volume_state"]=="BREAKOUT_CONFIRMED" for x in volume_rows))
            st.caption(f'High-volume population: {sum(x["volume_state"] in {"VOLUME_SURGE","HIGH_VOLUME_NO_ACTION","BREAKOUT_CONFIRMED","FAILED_BREAKOUT"} for x in volume_rows)}')
            if governed["matured_performance_count"] == 0:
                st.info("Performance analytics will appear after the first completed trading-session horizon matures. No client performance claim is published before then.")
        with st.expander("Canonical Valuation Data Health", expanded=True):
            distribution=valuation_health["certification_distribution"]
            columns=st.columns(5)
            for index,(label,key) in enumerate((("Certified","CERTIFIED"),("High Uncertainty","CERTIFIED_HIGH_UNCERTAINTY"),("Review Required","REVIEW_REQUIRED"),("Insufficient Inputs","INSUFFICIENT_INPUTS"),("Not Applicable","NOT_APPLICABLE"))):
                columns[index].metric(label,distribution.get(key,0))
            checks=st.columns(4)
            checks[0].metric("Source Divergence",valuation_health["input_source_divergence_count"])
            checks[1].metric("Period Mismatch",valuation_health["period_mismatch_count"])
            checks[2].metric("Market-Cap Bridge",valuation_health["market_cap_bridge_failure_count"])
            checks[3].metric("EV Bridge",valuation_health["ev_bridge_failure_count"])
            checks=st.columns(4)
            checks[0].metric("FCF Reconciliation",valuation_health["fcf_reconciliation_failure_count"])
            checks[1].metric("Extreme Dispersion",valuation_health["extreme_model_dispersion_count"])
            checks[2].metric("Sector/Model Review",valuation_health["sector_model_applicability_warning_count"])
            checks[3].metric("Published Audited",valuation_health["published_audited"])
            remediation_path=Path("audit_results/canonical_valuation_certification.json")
            remediation=json.loads(remediation_path.read_text(encoding="utf-8")) if remediation_path.exists() else {}
            provider_families=((remediation.get("provider_quality") or {}).get("families") or {})
            if provider_families:
                rows=[]
                for metric,item in provider_families.items():
                    rows.append({"Metric":metric,"Checked":item.get("records_checked"),"Agreement %":item.get("agreement_rate"),"Divergence %":item.get("divergence_rate"),"Missing %":item.get("missing_rate"),"Unresolved %":item.get("unresolved_rate")})
                st.caption("Independent validator quality by critical data family")
                st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        with st.expander("Hard Publication Governance", expanded=True):
            run=st.columns(4)
            run[0].metric("Evaluated",publication_manifest.get("universe_count",0))
            run[1].metric("Publication Gate",publication_manifest.get("publication_gate_status","NOT AVAILABLE"))
            run[2].metric("Withheld",publication_manifest.get("withheld_count",0))
            run[3].metric("Last Known Good",publication_manifest.get("generated_at","Not available"))
            provider=dict(publication_manifest.get("provider_status") or {})
            quality=st.columns(4)
            quality[0].metric("Provider Calls",provider.get("provider_calls",0))
            quality[1].metric("Retries / Throttling",provider.get("retry_count",0))
            quality[2].metric("Credential Failures",sum("KEY_UNAVAILABLE" in str(code) for code in provider.get("reason_codes") or ()))
            quality[3].metric("Home / Research Mismatch",governed["home_research_mismatch_count"])
            st.caption(f"Run {publication_manifest.get('run_id','Not available')} · Freshness {publication_manifest.get('freshness_status','Not available')} · Candidate status {publication_manifest.get('publication_gate_status','Not available')}")
        validation=validation_report(snapshot_rows,outcome_rows)
        st.markdown("### Model Validation — Internal Only")
        with st.container(border=True):
            st.caption("Observational validation only. Customer-facing performance remains disabled and these results cannot alter methodology.")
            overview=st.columns(4);overview[0].metric("Total Snapshots",validation["total_snapshots"]);overview[1].metric("Matured Snapshots",validation["matured_snapshots"]);overview[2].metric("Matured Records",validation["matured_records"]);overview[3].metric("Missing Prices",validation["missing_price_observations"])
            st.markdown("**Sample size by horizon**")
            horizon_columns=st.columns(6)
            for index,horizon in enumerate(("1","5","20","63","126","252")):
                horizon_columns[index].metric(f"{horizon}D",validation["sample_size_by_horizon"][horizon])
            if not outcome_rows:
                st.info("Insufficient matured sample")
            else:
                for key,label in (("action","By Action"),("opportunity_thesis","By Thesis Type"),("decision_confidence_bucket","By Confidence Bucket"),("valuation_confidence_bucket","By Valuation Confidence")):
                    st.markdown(f"**{label}**")
                    data=validation["aggregations"][key]
                    st.dataframe(pd.DataFrame(data),hide_index=True,use_container_width=True) if data else st.caption("Insufficient matured sample")
                st.write("Target / stop statistics",validation["target_stop"])
            alerts=regression_alerts(validation)
            st.warning(f"{len(alerts)} review-only validation alert(s)") if alerts else st.success("No governed validation regression alert is active.")
    except Exception:
        st.warning("Institutional methodology health is temporarily unavailable; canonical outputs remain unchanged.")
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
    from services.session_stability import emit_page_interactive
    emit_page_interactive(st, "Developer Center")

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
