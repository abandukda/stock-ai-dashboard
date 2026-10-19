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
