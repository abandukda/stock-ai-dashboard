
"""
Atlas UI Components

Reusable Streamlit/HTML components for a more premium web-app feel.
"""

from __future__ import annotations

import html
from typing import Iterable

import streamlit as st

from ui.theme import (
    ATLAS_AMBER,
    ATLAS_BG,
    ATLAS_BLUE,
    ATLAS_BORDER,
    ATLAS_CARD,
    ATLAS_CARD_SOFT,
    ATLAS_GREEN,
    ATLAS_PANEL,
    ATLAS_PURPLE,
    ATLAS_RED,
    GRADIENT_BUY,
    GRADIENT_CARD,
    GRADIENT_HERO,
    SHADOW_GLOW_GREEN,
    SHADOW_SOFT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def section_header(icon: str, title: str, subtitle: str | None = None):
    subtitle_html = (
        f'<div style="color:{TEXT_MUTED}; font-size:15px; margin-top:5px; line-height:1.45;">{_esc(subtitle)}</div>'
        if subtitle
        else ""
    )

    st.markdown(
        f"""
        <div style="margin-top:30px; margin-bottom:16px;">
            <div style="display:flex; align-items:center; gap:12px;">
                <div style="
                    width:42px; height:42px; border-radius:14px;
                    background:{GRADIENT_HERO};
                    display:flex; align-items:center; justify-content:center;
                    border:1px solid {ATLAS_BORDER};
                    box-shadow:{SHADOW_SOFT};
                    font-size:22px;
                ">{icon}</div>
                <div>
                    <div style="font-size:30px; font-weight:850; letter-spacing:-0.03em; color:{TEXT_PRIMARY};">
                        {_esc(title)}
                    </div>
                    {subtitle_html}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def atlas_banner(title: str, subtitle: str, eyebrow: str = "ATLAS INTELLIGENCE™"):
    st.markdown(
        f"""
        <div style="
            background:{GRADIENT_HERO};
            border:1px solid {ATLAS_BORDER};
            border-radius:26px;
            padding:30px 34px;
            margin:10px 0 26px 0;
            box-shadow:{SHADOW_SOFT};
        ">
            <div style="
                color:{ATLAS_CYAN if 'ATLAS_CYAN' in globals() else ATLAS_BLUE};
                font-size:12px;
                font-weight:900;
                letter-spacing:0.16em;
                text-transform:uppercase;
                margin-bottom:10px;
            ">{_esc(eyebrow)}</div>
            <div style="
                color:{TEXT_PRIMARY};
                font-size:42px;
                font-weight:900;
                letter-spacing:-0.05em;
                line-height:1.06;
            ">{_esc(title)}</div>
            <div style="
                color:{TEXT_SECONDARY};
                font-size:17px;
                line-height:1.55;
                max-width:900px;
                margin-top:12px;
            ">{_esc(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_card(title: str, body: str, icon: str = "ℹ️"):
    st.markdown(
        f"""
        <div class="atlas-card" style="
            border:1px solid {ATLAS_BORDER};
            border-radius:20px;
            padding:20px 22px;
            background:{GRADIENT_CARD};
            margin:14px 0;
            box-shadow:{SHADOW_SOFT};
        ">
            <div style="display:flex; gap:12px; align-items:flex-start;">
                <div style="
                    min-width:38px; width:38px; height:38px;
                    border-radius:13px;
                    background:rgba(56,189,248,0.10);
                    border:1px solid rgba(56,189,248,0.22);
                    display:flex; align-items:center; justify-content:center;
                    font-size:19px;
                ">{icon}</div>
                <div>
                    <div style="font-size:19px; font-weight:850; color:{TEXT_PRIMARY}; margin-bottom:8px;">
                        {_esc(title)}
                    </div>
                    <div style="color:{TEXT_SECONDARY}; font-size:15px; line-height:1.68;">
                        {_esc(body)}
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, note: str | None = None):
    note_html = (
        f'<div style="color:{TEXT_MUTED}; font-size:12px; margin-top:7px; line-height:1.35;">{_esc(note)}</div>'
        if note
        else ""
    )
    st.markdown(
        f"""
        <div class="atlas-metric-card" style="
            border:1px solid {ATLAS_BORDER};
            border-radius:18px;
            padding:17px 18px;
            background:{ATLAS_CARD_SOFT};
            min-height:116px;
            box-shadow:{SHADOW_SOFT};
        ">
            <div style="color:{TEXT_MUTED}; font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:0.08em;">
                {_esc(label)}
            </div>
            <div style="font-size:30px; font-weight:900; color:{TEXT_PRIMARY}; margin-top:8px; letter-spacing:-0.03em;">
                {_esc(value)}
            </div>
            {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_color(text: str) -> str:
    t = str(text).upper()
    if "BUY NOW" in t or "BUY" in t or "STRONG" in t or "ELITE" in t:
        return ATLAS_GREEN
    if "WATCH" in t or "HOLD" in t or "GRADUAL" in t or "MIXED" in t:
        return ATLAS_AMBER
    if "AVOID" in t or "SELL" in t or "RISK" in t:
        return ATLAS_RED
    return ATLAS_BLUE


def status_pill(text: str):
    color = status_color(text)
    return f"""
        <span style="
            display:inline-flex; align-items:center; gap:6px;
            padding:8px 12px;
            border-radius:999px;
            background:{color}1A;
            border:1px solid {color}66;
            color:{TEXT_PRIMARY};
            font-size:13px;
            font-weight:850;
            white-space:nowrap;
        ">{_esc(text)}</span>
    """


def recommendation_card(recommendation: str, classification: str, confidence: str):
    color = status_color(recommendation)
    st.markdown(
        f"""
        <div class="atlas-recommendation-card" style="
            border:1px solid {color}99;
            border-radius:26px;
            padding:26px 28px;
            background:{GRADIENT_BUY if color == ATLAS_GREEN else GRADIENT_CARD};
            margin:16px 0 24px 0;
            box-shadow:{SHADOW_GLOW_GREEN if color == ATLAS_GREEN else SHADOW_SOFT};
            position:relative;
            overflow:hidden;
        ">
            <div style="
                position:absolute; top:-70px; right:-70px; width:220px; height:220px;
                background:{color}22; border-radius:999px; filter:blur(8px);
            "></div>

            <div style="position:relative;">
                <div style="
                    color:{TEXT_MUTED};
                    font-size:12px;
                    font-weight:900;
                    letter-spacing:0.14em;
                    text-transform:uppercase;
                ">Atlas AI Verdict</div>

                <div style="
                    color:{TEXT_PRIMARY};
                    font-size:42px;
                    font-weight:950;
                    margin-top:6px;
                    letter-spacing:-0.055em;
                    line-height:1.05;
                ">{_esc(recommendation)}</div>

                <div style="display:flex; gap:12px; margin-top:18px; flex-wrap:wrap;">
                    {status_pill(classification)}
                    {status_pill("Atlas Confidence™ " + _esc(confidence))}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def warning_card(title: str, body: str):
    st.markdown(
        f"""
        <div style="
            border:1px solid {ATLAS_AMBER}88;
            border-radius:18px;
            padding:18px 20px;
            background:rgba(245,158,11,0.10);
            margin:14px 0;
            box-shadow:{SHADOW_SOFT};
        ">
            <div style="font-size:19px; font-weight:900; color:{TEXT_PRIMARY};">⚠️ {_esc(title)}</div>
            <div style="color:#FDE68A; font-size:15px; line-height:1.65; margin-top:8px;">
                {_esc(body)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bullet_list(title: str, bullets: list[str], icon: str = "✅"):
    st.markdown(
        f"""
        <div style="
            border:1px solid {ATLAS_BORDER};
            border-radius:18px;
            padding:18px 20px;
            background:{ATLAS_CARD_SOFT};
            margin:12px 0;
            box-shadow:{SHADOW_SOFT};
            min-height:230px;
        ">
            <div style="font-size:20px; font-weight:900; color:{TEXT_PRIMARY}; margin-bottom:12px;">
                {icon} {_esc(title)}
            </div>
        """,
        unsafe_allow_html=True,
    )

    for b in bullets:
        st.markdown(f"- {b}")

    st.markdown("</div>", unsafe_allow_html=True)


def divider():
    st.markdown(
        f"<hr style='border:0; border-top:1px solid {ATLAS_BORDER}; margin:28px 0;'>",
        unsafe_allow_html=True,
    )


def score_stars(score: float) -> str:
    try:
        score = float(score)
    except Exception:
        score = 0
    stars = round(max(0, min(100, score)) / 20)
    return "★" * stars + "☆" * (5 - stars)
