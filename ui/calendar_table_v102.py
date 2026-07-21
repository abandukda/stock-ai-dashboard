"""
Atlas V102.1 Compact Market Calendar
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import pandas as pd
import streamlit as st


def render_compact_calendar_table(
    events: Sequence[Mapping[str, Any]],
    *,
    max_rows: int = 12,
) -> None:
    rows = []
    for item in events or []:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Date": (
                    item.get("Date")
                    or item.get("date")
                    or item.get("datetime")
                    or "Upcoming"
                ),
                "Event": (
                    item.get("Event")
                    or item.get("event")
                    or item.get("name")
                    or "Economic event"
                ),
                "Consensus": (
                    item.get("Estimate")
                    or item.get("estimate")
                    or item.get("Consensus")
                    or item.get("consensus")
                    or "—"
                ),
                "Actual": (
                    item.get("Actual")
                    or item.get("actual")
                    or "—"
                ),
                "Impact": (
                    item.get("Impact")
                    or item.get("impact")
                    or "Medium"
                ),
            }
        )

    if not rows:
        st.info("No upcoming economic events were available.")
        return

    st.dataframe(
        pd.DataFrame(rows[:max_rows]),
        hide_index=True,
        use_container_width=True,
    )
