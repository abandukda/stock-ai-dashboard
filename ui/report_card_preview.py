"""Customer-safe Report Card availability preview.

This module intentionally accepts publication state, not ledger observations.
It cannot calculate or expose returns and therefore cannot become a second
Report Card authority.
"""
from __future__ import annotations

import html
from typing import Any, Mapping

import streamlit as st


def customer_report_card_preview(publication: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Project the bounded customer state without inventing measurements."""
    source = dict(publication or {})
    customer_visible = source.get("customer_visible") is True
    claims_allowed = source.get("public_performance_claims_allowed") is True
    try:
        has_observations = int(source.get("published_observation_count")) > 0
    except (TypeError, ValueError):
        has_observations = False
    if customer_visible and claims_allowed and has_observations:
        return {"state": "AVAILABLE", "eyebrow": "VERIFIED OBSERVATIONS",
                "title": "Measured outcomes are available",
                "body": "Open the published Report Card to review source-bound observations and SPY comparisons."}
    return {"state": "PENDING", "eyebrow": "MEASUREMENT IN PROGRESS",
            "title": "Verified outcomes are pending",
            "body": "ATLAS does not present certified decisions as realized returns. Results remain unpublished until measured observations pass the customer publication gate.",
            "benchmark": "SPY comparison pending", "methodology": "Registered horizons only",
            "provenance": "Source-bound observations required"}


def render_customer_report_card_preview(publication: Mapping[str, Any] | None = None) -> dict[str, str]:
    preview = customer_report_card_preview(publication)
    st.markdown("## Report Card Preview")
    st.markdown(
        '<section class="atlas-report-preview atlas-report-card-summary" data-atlas-qa="home-report-card-preview" '
        f'data-atlas-report-card-preview-state="{html.escape(preview["state"])}">'
        '<div class="atlas-report-preview-mark" aria-hidden="true">RC</div><div>'
        f'<small>{html.escape(preview["eyebrow"])}</small><h3>{html.escape(preview["title"])}</h3>'
        f'<p>{html.escape(preview["body"])}</p>'
        '<div class="atlas-report-preview-grid" aria-label="Pending Report Card requirements">'
        f'<span><small>BENCHMARK</small><b>{html.escape(preview.get("benchmark", "Published"))}</b></span>'
        f'<span><small>METHODOLOGY</small><b>{html.escape(preview.get("methodology", "Published"))}</b></span>'
        f'<span><small>PROVENANCE</small><b>{html.escape(preview.get("provenance", "Published"))}</b></span></div>'
        '<span class="atlas-report-preview-status">Unproven · no success rate or return is claimed</span>'
        '</div></section>', unsafe_allow_html=True)
    return preview


__all__ = ["customer_report_card_preview", "render_customer_report_card_preview"]
