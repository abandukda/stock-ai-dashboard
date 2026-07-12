"""Executive summary and bottom line sections."""
from __future__ import annotations
from typing import Any
from ui.components import info_card
from engines.report_sections.formatting import clean_recommendation_text, fmt_pct, fmt_score, safe_text

def build_executive_summary(row: dict[str, Any], ticker: str, recommendation: str, classification: str) -> str:
    existing_summary = row.get("Executive Summary") or row.get("Research Summary")
    thesis = row.get("Investment Thesis")
    if thesis and "*" not in str(thesis):
        existing_summary = existing_summary or thesis
    if existing_summary:
        return safe_text(existing_summary)
    clean_reco = clean_recommendation_text(recommendation)
    return (
        f"Atlas currently rates {ticker} as {clean_reco} and classifies it as {classification}. "
        f"The latest scan shows an opportunity score of {fmt_score(row.get('Opportunity') or row.get('Final Conviction') or row.get('Score'))}, "
        f"quality score of {fmt_score(row.get('Quality') or row.get('Financial Health') or row.get('Finance Agent Score'))}, "
        f"and modeled upside of {fmt_pct(row.get('Target Upside %') or row.get('Upside'))}. "
        f"The report below summarizes the thesis, risks, entry plan, and supporting evidence in plain English."
    )

def render_executive_summary(row: dict[str, Any], ticker: str, recommendation: str, classification: str) -> None:
    info_card("Executive Summary", build_executive_summary(row, ticker, recommendation, classification), icon="🤖")

def render_bottom_line(row: dict[str, Any], ticker: str, recommendation: str) -> None:
    info_card(
        "Bottom Line",
        safe_text(
            row.get("Bottom Line")
            or (
                f"{ticker} currently receives a {recommendation} rating based on the latest completed scan. "
                f"The thesis should be reviewed alongside position sizing, earnings risk, valuation, and supporting evidence."
            )
        ),
        icon="🧭",
    )
