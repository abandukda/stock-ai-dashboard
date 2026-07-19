"""
Atlas V99.1 — Institutional Experience UI Components

New file:
    ui/institutional_experience.py

This module renders V97/V98 outputs without changing recommendations.
"""

from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping
import html
import math
import pandas as pd
import streamlit as st

MISSING = {"", "n/a", "na", "none", "null", "nan", "unavailable",
           "under review", "not available", "not reported", "unknown", "-", "—"}

def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in MISSING
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return True

def _num(value: Any, default=None):
    if not _present(value):
        return default
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except Exception:
        return default

def _text(value: Any, default=""):
    return str(value).strip() if _present(value) else default

def _safe(value: Any) -> str:
    return html.escape(_text(value))

def _money(value: Any) -> str:
    n = _num(value)
    return "Under review" if n is None else f"${n:,.2f}"

def _pct(value: Any) -> str:
    n = _num(value)
    return "Under review" if n is None else f"{n:+.1f}%"

def _score(value: Any) -> str:
    n = _num(value)
    return "Under review" if n is None else f"{n:.1f}"

def _snapshot(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v93_snapshot")
    return value if isinstance(value, Mapping) else {}

def _decision(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("v89_decision")
    return value if isinstance(value, Mapping) else {}

def build_card_view_model(row, *, transparency=None, ranking=None, competition=None):
    transparency = dict(transparency or {})
    ranking = dict(ranking or {})
    competition = dict(competition or {})
    snapshot = _snapshot(row)
    decision = _decision(row)

    evidence = (transparency.get("passed_pillars")
                or decision.get("supporting_evidence")
                or snapshot.get("supporting_evidence")
                or row.get("why_atlas_likes_it")
                or [])
    if isinstance(evidence, str):
        evidence = [evidence]

    evidence_labels = []
    for item in evidence:
        label = item.get("label") if isinstance(item, Mapping) else item
        if _present(label):
            evidence_labels.append(_text(label))

    trigger = transparency.get("trigger")
    trigger = trigger if isinstance(trigger, Mapping) else {}

    return {
        "ticker": _text(row.get("Ticker") or row.get("ticker") or row.get("symbol"), "UNKNOWN").upper(),
        "company": _text(row.get("Company") or row.get("company") or row.get("Name"), "Unknown"),
        "action": _text(decision.get("display_action") or snapshot.get("display_action")
                        or row.get("Recommendation") or row.get("Decision"), "Monitor"),
        "current_price": snapshot.get("current_price", row.get("Current Price")),
        "fair_value": snapshot.get("atlas_fair_value", row.get("Atlas Fair Value")),
        "expected_return": snapshot.get("expected_return_pct", decision.get("expected_return_pct")),
        "confidence": transparency.get("confidence", snapshot.get("confidence", decision.get("conviction"))),
        "research_completeness": transparency.get(
            "research_completeness_pct",
            snapshot.get("research_completeness_pct", decision.get("research_completeness_pct")),
        ),
        "opportunity_score": ranking.get("opportunity_score"),
        "opportunity_tier": ranking.get("opportunity_tier", "Under review"),
        "overall_rank": ranking.get("overall_rank"),
        "universe_count": ranking.get("universe_count"),
        "percentile_text": ranking.get("top_percentile_text", "Under review"),
        "sector_rank": ranking.get("sector_rank"),
        "sector_count": ranking.get("sector_count"),
        "portfolio_rank": competition.get("portfolio_rank"),
        "evidence": evidence_labels[:8],
        "primary_risk": _text(transparency.get("primary_blocker")
                              or decision.get("biggest_risk")
                              or snapshot.get("primary_risk")
                              or row.get("primary_risk"),
                              "Risk evidence remains under review."),
        "trigger_label": trigger.get("label"),
        "trigger_condition": trigger.get("condition"),
        "required_passed": transparency.get("required_pillars_passed"),
        "required_total": transparency.get("required_pillars_total"),
        "consistency_warnings": transparency.get("consistency_warnings") or [],
    }

def render_institutional_opportunity_card(row, *, transparency=None, ranking=None, competition=None):
    vm = build_card_view_model(row, transparency=transparency, ranking=ranking, competition=competition)
    st.markdown("""
<style>
.atlas-card{border:1px solid rgba(120,140,170,.28);border-radius:18px;padding:18px;margin:8px 0 18px;background:rgba(15,23,42,.45)}
.atlas-head{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.atlas-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:16px}
.atlas-metric{border:1px solid rgba(120,140,170,.22);border-radius:12px;padding:11px;min-width:0}
.atlas-metric span{display:block;opacity:.65;font-size:.78rem;overflow-wrap:anywhere}
.atlas-metric b{display:block;margin-top:4px;overflow-wrap:anywhere;word-break:break-word}
.atlas-section{margin-top:14px;border-top:1px solid rgba(120,140,170,.18);padding-top:12px;overflow-wrap:anywhere}
@media(max-width:900px){.atlas-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>""", unsafe_allow_html=True)

    rank = (f"#{int(vm['overall_rank'])} of {int(vm['universe_count']):,}"
            if _num(vm["overall_rank"]) is not None and _num(vm["universe_count"]) is not None
            else "Under review")
    sector_rank = (f"#{int(vm['sector_rank'])} of {int(vm['sector_count'])}"
                   if _num(vm["sector_rank"]) is not None and _num(vm["sector_count"]) is not None
                   else "Under review")
    portfolio_rank = f"#{int(vm['portfolio_rank'])}" if _num(vm["portfolio_rank"]) is not None else "Under review"
    required = (f"{int(vm['required_passed'])}/{int(vm['required_total'])}"
                if _num(vm["required_passed"]) is not None and _num(vm["required_total"]) is not None
                else "Under review")
    evidence_html = "".join(f"<li>{_safe(item)}</li>" for item in vm["evidence"]) or "<li>Additional evidence is being assembled.</li>"
    trigger_html = (f"<div class='atlas-section'><b>{_safe(vm['trigger_label'] or 'Next trigger')}</b><br>{_safe(vm['trigger_condition'])}</div>"
                    if _present(vm["trigger_condition"]) else "")

    st.markdown(f"""
<div class="atlas-card">
  <div class="atlas-head"><div><h3>{_safe(vm["ticker"])}</h3><div>{_safe(vm["company"])}</div></div><b>{_safe(vm["action"])}</b></div>
  <div class="atlas-grid">
    <div class="atlas-metric"><span>Opportunity Score</span><b>{_score(vm["opportunity_score"])}</b></div>
    <div class="atlas-metric"><span>Tier</span><b>{_safe(vm["opportunity_tier"])}</b></div>
    <div class="atlas-metric"><span>Overall Rank</span><b>{_safe(rank)}</b></div>
    <div class="atlas-metric"><span>Market Position</span><b>{_safe(vm["percentile_text"])}</b></div>
    <div class="atlas-metric"><span>Sector Rank</span><b>{_safe(sector_rank)}</b></div>
    <div class="atlas-metric"><span>Portfolio Rank</span><b>{_safe(portfolio_rank)}</b></div>
    <div class="atlas-metric"><span>Confidence</span><b>{_pct(vm["confidence"])}</b></div>
    <div class="atlas-metric"><span>Research Complete</span><b>{_pct(vm["research_completeness"])}</b></div>
    <div class="atlas-metric"><span>Current Price</span><b>{_money(vm["current_price"])}</b></div>
    <div class="atlas-metric"><span>Atlas Fair Value</span><b>{_money(vm["fair_value"])}</b></div>
    <div class="atlas-metric"><span>Expected Return</span><b>{_pct(vm["expected_return"])}</b></div>
    <div class="atlas-metric"><span>Required Pillars</span><b>{_safe(required)}</b></div>
  </div>
  <div class="atlas-section"><b>Why Atlas selected it</b><ul>{evidence_html}</ul></div>
  <div class="atlas-section"><b>Primary risk</b><br>{_safe(vm["primary_risk"])}</div>
  {trigger_html}
</div>""", unsafe_allow_html=True)

def render_decision_scorecard(transparency: Mapping[str, Any], title="Decision Scorecard"):
    st.markdown(f"### {title}")
    passed = transparency.get("passed_pillars") or []
    failed = transparency.get("failed_pillars") or []
    missing = transparency.get("missing_required_pillars") or []
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Passed**")
        for item in passed:
            st.success(item.get("label") or item.get("key"))
    with c2:
        st.markdown("**Failed**")
        for item in failed:
            st.error(item.get("label") or item.get("key"))
    with c3:
        st.markdown("**Missing**")
        for item in missing:
            st.warning(item.get("label") or item.get("key"))
    trigger = transparency.get("trigger")
    if isinstance(trigger, Mapping) and _present(trigger.get("condition")):
        st.info(f"**{trigger.get('label') or 'Next trigger'}:** {trigger.get('condition')}")

def render_admin_opportunity_dashboard(*, ranking_report=None, competition_report=None,
                                       transparency_report=None, discovery_report=None):
    ranking_report = dict(ranking_report or {})
    competition_report = dict(competition_report or {})
    transparency_report = dict(transparency_report or {})
    discovery_report = dict(discovery_report or {})
    discovery = discovery_report.get("funnel_counts") or {}
    ranking = ranking_report.get("ranking_summary") or {}
    competition = competition_report.get("competition_summary") or {}
    transparency = transparency_report.get("summary") or {}

    st.markdown("## Institutional Opportunity Operations")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Universe", int(discovery.get("universe_received", 0)))
    c2.metric("Research shortlist", int(discovery.get("shortlisted_for_full_research", 0)))
    c3.metric("Portfolio candidates", int(competition.get("selected_candidates", 0)))
    c4.metric("Decision consistency", f"{_num(transparency.get('consistency_rate_pct'), 0):.1f}%")

    st.markdown("### Opportunity Distribution")
    st.dataframe(pd.DataFrame([
        ["Elite", ranking.get("elite_count", 0)],
        ["Exceptional", ranking.get("exceptional_count", 0)],
        ["High", ranking.get("high_count", 0)],
        ["Good", ranking.get("good_count", 0)],
        ["Average", ranking.get("average_count", 0)],
        ["Weak", ranking.get("weak_count", 0)],
    ], columns=["Tier", "Count"]), hide_index=True, use_container_width=True)

    suppressions = competition_report.get("suppressed_candidates") or []
    if suppressions:
        st.markdown("### Suppressed Opportunities")
        st.dataframe(pd.DataFrame([{
            "Ticker": item.get("ticker"),
            "Company": item.get("company"),
            "Sector": item.get("sector"),
            "Score": item.get("opportunity_score"),
            "Reason": item.get("suppression_reason"),
        } for item in suppressions[:100]]), hide_index=True, use_container_width=True)

def index_by_ticker(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    output = {}
    for row in rows or []:
        if isinstance(row, Mapping):
            ticker = _text(row.get("ticker") or row.get("Ticker")).upper()
            if ticker:
                output[ticker] = dict(row)
    return output

__all__ = [
    "build_card_view_model",
    "render_institutional_opportunity_card",
    "render_decision_scorecard",
    "render_admin_opportunity_dashboard",
    "index_by_ticker",
]
