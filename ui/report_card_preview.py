"""Customer-safe Report Card availability preview.

This module intentionally accepts publication state, not ledger observations.
It cannot calculate or expose returns and therefore cannot become a second
Report Card authority.
"""
from __future__ import annotations

import html
from typing import Any, Mapping

import streamlit as st


def _safe_count(source: Mapping[str, Any], key: str) -> int | None:
    """Return a non-negative published count without coercing bad evidence."""
    value = source.get(key)
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def customer_report_card_preview(publication: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Project the bounded customer state without inventing measurements."""
    source = dict(publication or {})
    customer_visible = source.get("customer_visible") is True
    claims_allowed = source.get("public_performance_claims_allowed") is True
    observation_count = _safe_count(source, "published_observation_count")
    has_observations = observation_count is not None and observation_count > 0
    if customer_visible and claims_allowed and has_observations:
        tracked = _safe_count(source, "published_signal_count")
        measured = _safe_count(source, "measured_signal_count")
        successful = _safe_count(source, "successful_signal_count")
        unsuccessful = _safe_count(source, "unsuccessful_signal_count")
        pending = _safe_count(source, "pending_signal_count")
        return {"state": "AVAILABLE", "eyebrow": "VERIFIED OBSERVATIONS",
                "title": "Measured outcomes are available",
                "body": "Open the published Report Card to review source-bound observations and SPY comparisons.",
                "tracked": str(tracked) if tracked is not None else "Published",
                "measured": str(measured) if measured is not None else str(observation_count),
                "successful": str(successful) if successful is not None else "See observations",
                "unsuccessful": str(unsuccessful) if unsuccessful is not None else "See observations",
                "pending": str(pending) if pending is not None else "See timeline",
                "benchmark": "SPY · same sessions", "methodology": "Registered horizons",
                "provenance": "Published observations",
                "success_definition": str(source.get("published_success_definition") or
                                          "See the published methodology; no definition is inferred here.")}
    return {"state": "PENDING", "eyebrow": "MEASUREMENT IN PROGRESS",
            "title": "Verified outcomes are pending",
            "body": "ATLAS does not present certified decisions as realized returns. Results remain unpublished until measured observations pass the customer publication gate.",
            "tracked": "Not public", "measured": "Pending", "successful": "Pending",
            "unsuccessful": "Pending", "pending": "Pending",
            "benchmark": "SPY comparison pending", "methodology": "Registered horizons only",
            "provenance": "Source-bound observations required",
            "success_definition": "No outcome-classification rule is published while observations are pending."}


def render_customer_report_card_preview(publication: Mapping[str, Any] | None = None) -> dict[str, str]:
    preview = customer_report_card_preview(publication)
    st.markdown("## Report Card Preview")
    if preview["state"] == "PENDING":
        st.markdown(
            '<style>.atlas-report-pending-preview{padding:1.2rem;border:1px solid #34465f;border-radius:18px;background:linear-gradient(135deg,#14273b,#101b2d);color:#e8eff8}'
            '.atlas-report-pending-preview h3{margin:.4rem 0!important;font-size:1.3rem!important}.atlas-report-pending-preview p{color:#bacbdd;line-height:1.55}'
            '.atlas-report-readiness{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.65rem;margin:1rem 0}'
            '.atlas-report-readiness article{padding:.8rem;border:1px solid #34465f;border-radius:12px;background:rgba(4,14,25,.35)}'
            '.atlas-report-readiness small,.atlas-report-readiness b{display:block}.atlas-report-readiness small{font-size:.65rem;color:#8eb2d7;letter-spacing:.05em}.atlas-report-readiness b{font-size:.9rem;margin-top:.35rem;line-height:1.45}'
            '.atlas-report-pending-preview summary{cursor:pointer;color:#b7d9f5;font-size:.85rem}.atlas-report-pending-preview details p{font-size:.82rem;margin:.5rem 0}'
            '@media(max-width:700px){.atlas-report-readiness{grid-template-columns:1fr}.atlas-report-readiness article{padding:.7rem}.atlas-report-pending-preview{padding:.9rem}}</style>'
            '<section class="atlas-report-pending-preview atlas-report-card-summary" data-atlas-qa="home-report-card-preview" '
            'data-atlas-report-card-preview-state="PENDING">'
            f'<small>{html.escape(preview["eyebrow"])}</small><h3>{html.escape(preview["title"])}</h3>'
            f'<p>{html.escape(preview["body"])}</p>'
            '<div class="atlas-report-readiness" aria-label="Performance evidence readiness">'
            '<article><small>01 · EVIDENCE</small><b>Certified observations required</b></article>'
            '<article><small>02 · MEASUREMENT</small><b>Returns and SPY comparison pending</b></article>'
            '<article><small>03 · PUBLICATION</small><b>Public activation OFF</b></article></div>'
            '<details><summary>How performance will be measured</summary>'
            f'<p>{html.escape(preview["methodology"])}. {html.escape(preview["provenance"])}. '
            f'{html.escape(preview["success_definition"])}</p>'
            '<p>Pending means evidence is not yet mature or not publicly approved. '
            'No successful/unsuccessful classification or realized return is inferred from a recommendation.</p>'
            '</details></section>', unsafe_allow_html=True,
        )
        return preview
    st.markdown(
        '<section class="atlas-report-preview atlas-report-card-summary" data-atlas-qa="home-report-card-preview" '
        f'data-atlas-report-card-preview-state="{html.escape(preview["state"])}">'
        '<div class="atlas-report-preview-mark" aria-hidden="true">RC</div><div>'
        f'<small>{html.escape(preview["eyebrow"])}</small><h3>{html.escape(preview["title"])}</h3>'
        f'<p>{html.escape(preview["body"])}</p>'
        '<div class="atlas-report-preview-grid" aria-label="Report Card outcome status">'
        f'<span><small>TRACKED</small><b>{html.escape(preview["tracked"])}</b></span>'
        f'<span><small>MEASURED</small><b>{html.escape(preview["measured"])}</b></span>'
        f'<span><small>SUCCESSFUL</small><b>{html.escape(preview["successful"])}</b></span>'
        f'<span><small>UNSUCCESSFUL</small><b>{html.escape(preview["unsuccessful"])}</b></span>'
        f'<span><small>PENDING</small><b>{html.escape(preview["pending"])}</b></span>'
        f'<span><small>BENCHMARK</small><b>{html.escape(preview.get("benchmark", "Published"))}</b></span>'
        f'<span><small>METHODOLOGY</small><b>{html.escape(preview.get("methodology", "Published"))}</b></span>'
        f'<span><small>PROVENANCE</small><b>{html.escape(preview.get("provenance", "Published"))}</b></span></div>'
        f'<p><strong>How success is defined:</strong> {html.escape(preview["success_definition"])}</p>'
        '<span class="atlas-report-preview-status">Outcome states use registered observation horizons. '
        'Pending means the evidence is not yet mature or not publicly approved.</span>'
        '</div></section>', unsafe_allow_html=True)
    return preview


__all__ = ["customer_report_card_preview", "render_customer_report_card_preview"]
