"""Shared Streamlit renderer for page-wide plain-English intelligence."""
from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

from services.atlas_explains import ATLAS_EXPLAINS_VERSION, PageExplanation
from ui.market_timestamp import format_market_timestamp_et


def _display_source_date(value: str) -> str:
    """Format customer evidence dates while retaining the canonical value upstream."""
    text = str(value or "").strip()
    if not text:
        return "Date unavailable"
    if "T" in text or " " in text:
        return format_market_timestamp_et(text, unavailable="Date unavailable")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return "Date unavailable"
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def _rows(sections) -> str:
    customer_labels = {
        "SOURCE_FACT": "Verified fact",
        "CALCULATION": "ATLAS calculation",
        "INTERPRETATION": "What it means",
        "SCENARIO": "What to watch",
        "LIMITATION": "Important limitation",
    }
    return "".join(
        '<article class="atlas-explains-row" '
        f'data-atlas-classification="{html.escape(section.classification)}">'
        f'<small>{html.escape(customer_labels[section.classification])}</small>'
        f'<h4>{html.escape(section.label)}</h4><p>{html.escape(section.text)}</p>'
        + (
            '<footer>Evidence: ' + html.escape(" · ".join(section.evidence_ids)) + '</footer>'
            if section.evidence_ids else ""
        )
        + '</article>'
        for section in sections
    )


def render_atlas_explains(explanation: PageExplanation) -> None:
    st.markdown(
        """<style>
        .atlas-explains{border:1px solid rgba(94,234,212,.24);border-radius:18px;padding:1rem 1.05rem;margin:.35rem 0 1rem;background:linear-gradient(145deg,rgba(8,17,31,.97),rgba(15,31,48,.9))}.atlas-explains>small{color:#5eead4;font-weight:850;letter-spacing:.12em}.atlas-explains h2{font-size:1.35rem;margin:.18rem 0}.atlas-explains-lead{font-size:1rem;line-height:1.5;color:#dbe7f4;margin:.2rem 0}.atlas-explains-meta{font-size:.72rem;color:#94a3b8}.atlas-explains-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}.atlas-explains-row{padding:.65rem .72rem;border:1px solid rgba(148,163,184,.17);border-radius:12px;background:rgba(15,23,42,.5)}.atlas-explains-row small{color:#7dd3fc;font-size:.6rem;letter-spacing:.09em}.atlas-explains-row h4{font-size:.88rem;margin:.15rem 0}.atlas-explains-row p{font-size:.8rem;line-height:1.45;color:#cbd5e1;margin:0}.atlas-explains-row footer{margin-top:.45rem;color:#8493a7;font-size:.65rem;line-height:1.35;overflow-wrap:anywhere}@media(max-width:600px){.atlas-explains{padding:.78rem}.atlas-explains-grid{grid-template-columns:1fr}.atlas-explains h2{font-size:1.12rem}.atlas-explains-lead{font-size:.9rem}}
        </style>""", unsafe_allow_html=True,
    )
    st.markdown(
        f'<section class="atlas-explains" data-atlas-qa="atlas-explains" '
        f'data-atlas-explains-version="{ATLAS_EXPLAINS_VERSION}" '
        f'data-atlas-page="{html.escape(explanation.page)}" '
        f'data-atlas-synthesis-mode="{html.escape(explanation.synthesis_mode)}" '
        f'data-atlas-external-model-active="{str(explanation.external_model_active).lower()}" '
        f'data-atlas-non-scoring="{str(explanation.non_scoring).lower()}">'
        '<small>ATLAS EXPLAINS · 30-SECOND TAKEAWAY</small>'
        f'<h2>{html.escape(explanation.title)}</h2>'
        f'<p class="atlas-explains-lead">{html.escape(explanation.takeaway)}</p>'
        f'<div class="atlas-explains-meta">Evidence date: {html.escape(_display_source_date(explanation.source_date))} · '
        'Grounded deterministic fallback · external model inactive</div></section>',
        unsafe_allow_html=True,
    )
    # Keep the takeaway above the fold on compact screens. Both reading levels
    # remain an explicit action away and in the accessibility tree.
    with st.expander("Explore the two-minute explanation and supporting evidence", expanded=False):
        simple, detailed = st.tabs(["Simple View · 2 min", "Detailed View · evidence"])
        with simple:
            st.markdown(f'<div class="atlas-explains-grid">{_rows(explanation.simple)}</div>', unsafe_allow_html=True)
        with detailed:
            st.markdown(f'<div class="atlas-explains-grid">{_rows(explanation.detailed)}</div>', unsafe_allow_html=True)


__all__ = ["render_atlas_explains"]
