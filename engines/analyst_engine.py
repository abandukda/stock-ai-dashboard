
"""
Atlas Analyst Intelligence Engine

Purpose:
- Turn analyst/Wall Street data into a clear customer-facing summary.
- Show aggregate consensus first.
- Keep individual analyst evidence expandable.
- Designed to work with scan-row data now, and live FMP analyst detail later.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.components import info_card, metric_card
from engines.report_sections.formatting import fmt_money, fmt_pct, safe_num, safe_text


def _pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() and str(value).lower() not in {"nan", "none", "null", "n/a"}:
            return value
    return default


def _rating_label(buy: float, hold: float, sell: float) -> str:
    total = buy + hold + sell
    if total <= 0:
        return "Coverage Limited"

    buy_pct = buy / total

    if buy_pct >= 0.75 and sell <= max(1, total * 0.10):
        return "Strong Buy Consensus"
    if buy_pct >= 0.60:
        return "Positive Consensus"
    if buy_pct >= 0.45:
        return "Mixed but Constructive"
    if sell > buy:
        return "Cautious Consensus"
    return "Mixed Consensus"


def build_analyst_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    buy = safe_num(
        _pick(
            row,
            "Analyst Buy Count",
            "Buy Ratings",
            "Buy",
            "Analyst Buys",
            "num_buy_ratings",
            default=0,
        )
    )
    hold = safe_num(
        _pick(
            row,
            "Analyst Hold Count",
            "Hold Ratings",
            "Hold",
            "Analyst Holds",
            "num_hold_ratings",
            default=0,
        )
    )
    sell = safe_num(
        _pick(
            row,
            "Analyst Sell Count",
            "Sell Ratings",
            "Sell",
            "Analyst Sells",
            "num_sell_ratings",
            default=0,
        )
    )

    consensus_target = _pick(
        row,
        "Consensus Target",
        "Analyst Target",
        "Average Analyst Target",
        "Price Target",
        "Target",
        "AI / Analyst Target",
        default=None,
    )

    high_target = _pick(
        row,
        "High Target",
        "Highest Target",
        "Analyst High Target",
        "Target High",
        default=None,
    )

    low_target = _pick(
        row,
        "Low Target",
        "Lowest Target",
        "Analyst Low Target",
        "Target Low",
        default=None,
    )

    upside = _pick(
        row,
        "Analyst Upside %",
        "Target Upside %",
        "Upside",
        "Upside %",
        default=None,
    )

    analyst_score = _pick(
        row,
        "Analyst Score",
        "Analyst Support Score",
        "Wall Street Score",
        "Research Confidence",
        default=None,
    )

    rating = safe_text(
        _pick(
            row,
            "Analyst Rating",
            "Analyst View",
            "Analyst Support",
            "Consensus Rating",
            default="",
        ),
        "",
    )

    if not rating:
        rating = _rating_label(buy, hold, sell)

    return {
        "buy": buy,
        "hold": hold,
        "sell": sell,
        "rating": rating,
        "consensus_target": consensus_target,
        "high_target": high_target,
        "low_target": low_target,
        "upside": upside,
        "analyst_score": analyst_score,
    }


def build_analyst_summary(row: dict[str, Any]) -> str:
    snap = build_analyst_snapshot(row)

    buy = snap["buy"]
    hold = snap["hold"]
    sell = snap["sell"]
    total = buy + hold + sell

    existing = _pick(row, "Analyst Summary", "Wall Street Summary", default=None)
    if existing:
        return safe_text(existing)

    if total <= 0:
        return (
            "Analyst coverage details are limited in the latest scan. Atlas will treat Wall Street sentiment "
            "as a supporting signal only until more analyst data is available."
        )

    rating = snap["rating"]
    target_text = fmt_money(snap["consensus_target"])
    upside_text = fmt_pct(snap["upside"])

    if buy >= hold and buy > sell:
        tone = "Wall Street sentiment appears constructive"
    elif sell > buy:
        tone = "Wall Street sentiment appears cautious"
    else:
        tone = "Wall Street sentiment appears mixed"

    return (
        f"{tone}. Current analyst data shows {buy:.0f} Buy, {hold:.0f} Hold, and {sell:.0f} Sell ratings, "
        f"which Atlas classifies as {rating}. The consensus target is {target_text}, implying approximately "
        f"{upside_text} modeled upside based on the latest scan. Analyst views are supportive evidence, "
        f"but they should be weighed alongside financial quality, earnings trends, technical setup, and risk."
    )


def _mock_or_row_analyst_table(row: dict[str, Any]) -> pd.DataFrame:
    """
    Uses row-level data today. Later this can be replaced with FMP analyst-grade/history endpoint output.
    """
    raw_details = row.get("Analyst Details") or row.get("Analyst Ratings Detail")

    if isinstance(raw_details, list) and raw_details:
        try:
            return pd.DataFrame(raw_details)
        except Exception:
            pass

    snap = build_analyst_snapshot(row)

    rows = []

    rating = safe_text(snap["rating"], "Coverage Limited")
    target = fmt_money(snap["consensus_target"])

    if snap["buy"] or snap["hold"] or snap["sell"]:
        rows.append(
            {
                "Source": "Wall Street Consensus",
                "Rating": rating,
                "Target": target,
                "Context": f"{snap['buy']:.0f} Buy / {snap['hold']:.0f} Hold / {snap['sell']:.0f} Sell",
            }
        )

    if snap["high_target"]:
        rows.append(
            {
                "Source": "Target Range",
                "Rating": "Highest Target",
                "Target": fmt_money(snap["high_target"]),
                "Context": "Upper end of analyst target range.",
            }
        )

    if snap["low_target"]:
        rows.append(
            {
                "Source": "Target Range",
                "Rating": "Lowest Target",
                "Target": fmt_money(snap["low_target"]),
                "Context": "Lower end of analyst target range.",
            }
        )

    if not rows:
        rows.append(
            {
                "Source": "Atlas",
                "Rating": "Pending",
                "Target": "N/A",
                "Context": "Individual analyst details will appear here when available from the data source.",
            }
        )

    return pd.DataFrame(rows)


def render_analyst_intelligence(row: dict[str, Any]) -> None:
    """
    Customer-facing analyst section.
    Summary first, evidence second.
    """
    snap = build_analyst_snapshot(row)

    info_card(
        "Atlas Analyst Summary",
        build_analyst_summary(row),
        icon="🏛",
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        metric_card("Consensus", safe_text(snap["rating"], "Limited"))
    with c2:
        metric_card("Buy / Hold / Sell", f"{snap['buy']:.0f} / {snap['hold']:.0f} / {snap['sell']:.0f}")
    with c3:
        metric_card("Avg. Target", fmt_money(snap["consensus_target"]))
    with c4:
        metric_card("Upside", fmt_pct(snap["upside"]))

    c5, c6, c7 = st.columns(3)
    with c5:
        metric_card("High Target", fmt_money(snap["high_target"]))
    with c6:
        metric_card("Low Target", fmt_money(snap["low_target"]))
    with c7:
        metric_card("Analyst Score", f"{safe_num(snap['analyst_score']):.0f}/100")

    with st.expander("🔎 View Analyst Evidence", expanded=False):
        st.caption(
            "This section shows the analyst evidence behind the Atlas summary. "
            "Detailed analyst-by-analyst history will expand as live analyst endpoints are connected."
        )
        df = _mock_or_row_analyst_table(row)
        st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("📚 How to Read Analyst Ratings", expanded=False):
        st.markdown(
            """
            **Buy ratings** suggest analysts believe the stock may outperform or appreciate from current levels.

            **Hold ratings** usually mean analysts see balanced upside and downside.

            **Sell ratings** indicate analysts believe downside risk may outweigh upside.

            Atlas does not treat analyst ratings as a standalone buy signal. They are one input combined with
            financial quality, earnings trends, technical setup, news, political activity, and risk controls.
            """
        )
