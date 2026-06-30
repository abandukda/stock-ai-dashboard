"""
Atlas V60.3 Mobile Cards.
Mobile-friendly Top AI Ideas cards.
"""

from __future__ import annotations

from typing import Any
import pandas as pd
import streamlit as st


def _pick(row: dict[str, Any], *keys: str, default: str = "—") -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "null", "n/a", "na"}:
            return text
    return default


def inject_mobile_card_css() -> None:
    st.markdown(
        """
        <style>
        .atlas-mobile-card {
            border: 1px solid rgba(148,163,184,.25);
            background: linear-gradient(145deg, rgba(15,23,42,.98), rgba(17,24,39,.93));
            border-radius: 22px;
            padding: 18px 18px;
            margin: 12px 0;
            box-shadow: 0 12px 28px rgba(0,0,0,.24);
        }
        .atlas-mobile-top {display:flex; justify-content:space-between; gap:12px; align-items:flex-start;}
        .atlas-mobile-ticker {color:#F8FAFC; font-weight:950; font-size:25px; letter-spacing:-.05em;}
        .atlas-mobile-company {color:#94A3B8; font-size:13px; margin-top:3px;}
        .atlas-mobile-pill {
            border-radius:999px; padding:7px 10px; background:rgba(34,197,94,.14);
            border:1px solid rgba(34,197,94,.45); color:#F8FAFC; font-size:12px; font-weight:850; white-space:nowrap;
        }
        .atlas-mobile-grid {display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; margin-top:16px;}
        .atlas-mobile-label {color:#64748B; font-size:10px; text-transform:uppercase; font-weight:850; letter-spacing:.08em;}
        .atlas-mobile-value {color:#F8FAFC; font-size:19px; font-weight:900; margin-top:3px;}
        .atlas-mobile-footer {border-top:1px solid rgba(148,163,184,.18); margin-top:15px; padding-top:12px; color:#CBD5E1; font-size:13px; line-height:1.45;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_mobile_top_ai_cards(df: pd.DataFrame | None, max_rows: int = 10) -> None:
    if df is None or df.empty:
        st.info("No Top AI Ideas available yet.")
        return

    inject_mobile_card_css()

    st.markdown("### 📱 Card View")
    st.caption("Use this view on mobile instead of scrolling a wide table.")

    for row in df.head(max_rows).to_dict("records"):
        ticker = _pick(row, "ticker", "Ticker", "symbol", "Symbol")
        company = _pick(row, "company", "Company", "company_name", "name", default="")
        recommendation = _pick(row, "Recommendation", "recommendation", "decision_rating", default="Review")
        classification = _pick(row, "Classification", "classification", "setup_type", default="Setup")
        opportunity = _pick(row, "Opportunity", "opportunity", "final_agent_score", "score")
        quality = _pick(row, "Quality", "quality", "financial_score")
        confidence = _pick(row, "Confidence", "confidence", "conviction_score")
        upside = _pick(row, "target_upside_pct", "expected_upside_pct", "Upside", "upside")
        entry = _pick(row, "Entry", "entry_range", "entry_low", default="Review")
        target = _pick(row, "Target", "target", "target_mean_price", default="Review")

        st.markdown(
            f"""
            <div class="atlas-mobile-card">
                <div class="atlas-mobile-top">
                    <div>
                        <div class="atlas-mobile-ticker">{ticker}</div>
                        <div class="atlas-mobile-company">{company}</div>
                    </div>
                    <div class="atlas-mobile-pill">{recommendation}</div>
                </div>
                <div class="atlas-mobile-footer">{classification}</div>
                <div class="atlas-mobile-grid">
                    <div><div class="atlas-mobile-label">Opportunity</div><div class="atlas-mobile-value">{opportunity}</div></div>
                    <div><div class="atlas-mobile-label">Quality</div><div class="atlas-mobile-value">{quality}</div></div>
                    <div><div class="atlas-mobile-label">Confidence</div><div class="atlas-mobile-value">{confidence}</div></div>
                    <div><div class="atlas-mobile-label">Upside</div><div class="atlas-mobile-value">{upside}</div></div>
                    <div><div class="atlas-mobile-label">Entry</div><div class="atlas-mobile-value">{entry}</div></div>
                    <div><div class="atlas-mobile-label">Target</div><div class="atlas-mobile-value">{target}</div></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
