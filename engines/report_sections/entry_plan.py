"""Entry plan section."""
from __future__ import annotations
from typing import Any
import streamlit as st
from ui.components import metric_card, section_header
from engines.report_sections.formatting import fmt_money, safe_text

def render_entry_plan(row: dict[str, Any]) -> None:
    section_header("🎯", "Entry Plan", "Suggested trade structure from the latest scan.")
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("Entry Zone", safe_text(row.get("Entry") or row.get("Entry Range") or row.get("Buy Zone"), "Review setup"))
    with c2:
        metric_card("Stop / Risk Control", safe_text(row.get("Stop") or row.get("Stop Loss"), "Use risk controls"))
    with c3:
        metric_card("Target", safe_text(row.get("Target") or row.get("AI / Analyst Target") or fmt_money(row.get("AI Fair Value")), "Review target"))
