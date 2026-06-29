
"""
Atlas UI Components — Sprint 3.1
"""

from __future__ import annotations

import html
import streamlit as st

from ui.theme import (
    ATLAS_AMBER,
    ATLAS_BLUE,
    ATLAS_BORDER,
    ATLAS_BORDER_BRIGHT,
    ATLAS_CARD,
    ATLAS_GREEN,
    ATLAS_PURPLE,
    ATLAS_RED,
    GRADIENT_BUY,
    GRADIENT_CARD,
    GRADIENT_HERO,
    SHADOW_CARD,
    SHADOW_GLOW_BLUE,
    SHADOW_GLOW_GREEN,
    SHADOW_SOFT,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def status_color(text: str) -> str:
    t = str(text).upper()
    if "BUY" in t or "SUCCESS" in t or "POSITIVE" in t or "ELITE" in t or "RISK-ON" in t:
        return ATLAS_GREEN
    if "WATCH" in t or "HOLD" in t or "MIXED" in t or "GRADUAL" in t or "CONSTRUCTIVE" in t:
        return ATLAS_AMBER
    if "AVOID" in t or "SELL" in t or "FAIL" in t or "RISK" in t:
        return ATLAS_RED
    if "AI" in t or "ATLAS" in t:
        return ATLAS_PURPLE
    return ATLAS_BLUE


def status_pill(text: str, subtle: bool = False) -> str:
    color = status_color(text)
    bg = f"{color}18" if subtle else f"{color}24"
    return f"""
    <span style="
        display:inline-flex; align-items:center; gap:7px;
        padding:8px 13px;
        border-radius:999px;
        background:{bg};
        border:1px solid {color}66;
        color:{TEXT_PRIMARY};
        font-size:13px;
        font-weight:850;
        white-space:nowrap;
    ">{_esc(text)}</span>
    """


def atlas_shell_header():
    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:18px;
            margin-bottom:18px;
        ">
            <div style="display:flex; align-items:center; gap:14px;">
                <div style="
                    width:44px; height:44px; border-radius:16px;
                    background:{GRADIENT_HERO};
                    border:1px solid {ATLAS_BORDER_BRIGHT};
                    display:flex; align-items:center; justify-content:center;
                    box-shadow:{SHADOW_GLOW_BLUE};
                    font-size:23px;
                ">🧭</div>
                <div>
                    <div style="
                        color:{TEXT_PRIMARY};
                        font-size:24px;
                        font-weight:950;
                        letter-spacing:-0.055em;
                    ">ATLAS</div>
                    <div style="
                        color:{TEXT_MUTED};
                        font-size:12px;
                        font-weight:800;
                        letter-spacing:.13em;
                        text-transform:uppercase;
                    ">AI Investment Intelligence</div>
                </div>
            </div>
            <div style="display:flex; gap:10px; flex-wrap:wrap; justify-content:flex-end;">
                {status_pill("Research Platform", True)}
                {status_pill("Client Experience", True)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def atlas_dashboard_hero(
    greeting: str = "Good Evening",
    user_name: str = "Asif",
    market_tone: str = "Constructive",
    top_idea: str = "PODD",
    scan_count: str = "150",
    prescreen_count: str = "650",
    last_scan: str = "Latest completed scan",
):
    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            position:relative;
            overflow:hidden;
            border:1px solid {ATLAS_BORDER_BRIGHT};
            border-radius:32px;
            background:{GRADIENT_HERO};
            padding:34px;
            box-shadow:{SHADOW_SOFT};
            margin:12px 0 24px 0;
        ">
            <div style="
                position:absolute;
                width:420px; height:420px;
                right:-140px; top:-170px;
                border-radius:999px;
                background:rgba(34,197,94,0.18);
                filter:blur(4px);
            "></div>
            <div style="
                position:absolute;
                width:340px; height:340px;
                left:42%; bottom:-210px;
                border-radius:999px;
                background:rgba(167,139,250,0.18);
            "></div>

            <div style="position:relative; z-index:2;">
                <div style="
                    color:{ATLAS_BLUE};
                    font-size:12px;
                    font-weight:950;
                    letter-spacing:.17em;
                    text-transform:uppercase;
                    margin-bottom:12px;
                ">ATLAS DAILY BRIEF</div>

                <div style="
                    color:{TEXT_PRIMARY};
                    font-size:46px;
                    font-weight:950;
                    letter-spacing:-0.06em;
                    line-height:1.05;
                    max-width:820px;
                ">{_esc(greeting)}, {_esc(user_name)}</div>

                <div style="
                    color:{TEXT_SECONDARY};
                    font-size:17px;
                    margin-top:12px;
                    max-width:860px;
                    line-height:1.55;
                ">
                    Your personal investment research department. Atlas scanned the market and surfaced the strongest opportunities, risks, and intelligence signals for review.
                </div>

                <div style="display:flex; gap:11px; flex-wrap:wrap; margin-top:22px;">
                    {status_pill("Market Tone: " + market_tone)}
                    {status_pill("Top Opportunity: " + top_idea)}
                    {status_pill(scan_count + " stocks fully scanned", True)}
                    {status_pill(prescreen_count + " prescreened", True)}
                </div>

                <div style="
                    margin-top:20px;
                    color:{TEXT_MUTED};
                    font-size:13px;
                    font-weight:650;
                ">Updated: {_esc(last_scan)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def atlas_metric_tile(label: str, value: str, note: str = "", icon: str = "●", tone: str = "info"):
    color_map = {
        "success": ATLAS_GREEN,
        "warning": ATLAS_AMBER,
        "danger": ATLAS_RED,
        "ai": ATLAS_PURPLE,
        "info": ATLAS_BLUE,
    }
    color = color_map.get(tone, ATLAS_BLUE)
    note_html = (
        f'<div style="color:{TEXT_MUTED}; font-size:12px; line-height:1.35; margin-top:7px;">{_esc(note)}</div>'
        if note
        else ""
    )

    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            background:{GRADIENT_CARD};
            border:1px solid {ATLAS_BORDER};
            border-radius:22px;
            padding:20px;
            box-shadow:{SHADOW_CARD};
            min-height:138px;
            position:relative;
            overflow:hidden;
        ">
            <div style="
                position:absolute; right:-46px; top:-46px;
                width:118px; height:118px; border-radius:999px;
                background:{color}18;
            "></div>
            <div style="position:relative;">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:10px;">
                    <div style="
                        color:{TEXT_MUTED};
                        font-size:12px;
                        font-weight:900;
                        text-transform:uppercase;
                        letter-spacing:.10em;
                    ">{_esc(label)}</div>
                    <div style="
                        width:34px; height:34px;
                        border-radius:12px;
                        background:{color}1C;
                        border:1px solid {color}55;
                        display:flex; align-items:center; justify-content:center;
                    ">{icon}</div>
                </div>
                <div style="
                    color:{TEXT_PRIMARY};
                    font-size:34px;
                    font-weight:950;
                    letter-spacing:-0.055em;
                    margin-top:10px;
                ">{_esc(value)}</div>
                {note_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def opportunity_card(
    ticker: str,
    company: str,
    recommendation: str,
    conviction: str,
    upside: str,
    entry: str = "",
    target: str = "",
):
    color = status_color(recommendation)
    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            background:{GRADIENT_CARD};
            border:1px solid {ATLAS_BORDER};
            border-radius:24px;
            padding:22px;
            box-shadow:{SHADOW_CARD};
            margin-bottom:14px;
            position:relative;
            overflow:hidden;
        ">
            <div style="
                position:absolute; right:-72px; top:-72px;
                width:180px; height:180px; border-radius:999px;
                background:{color}1F;
            "></div>

            <div style="position:relative;">
                <div style="display:flex; justify-content:space-between; gap:14px; align-items:flex-start;">
                    <div>
                        <div style="
                            color:{TEXT_PRIMARY};
                            font-size:26px;
                            font-weight:950;
                            letter-spacing:-.05em;
                        ">{_esc(ticker)}</div>
                        <div style="color:{TEXT_MUTED}; font-size:13px; margin-top:3px;">{_esc(company)}</div>
                    </div>
                    {status_pill(recommendation)}
                </div>

                <div style="
                    display:grid;
                    grid-template-columns: repeat(3, minmax(0, 1fr));
                    gap:12px;
                    margin-top:18px;
                ">
                    <div>
                        <div style="color:{TEXT_FAINT}; font-size:11px; font-weight:850; text-transform:uppercase;">Atlas Conviction™</div>
                        <div style="color:{TEXT_PRIMARY}; font-size:24px; font-weight:950;">{_esc(conviction)}</div>
                    </div>
                    <div>
                        <div style="color:{TEXT_FAINT}; font-size:11px; font-weight:850; text-transform:uppercase;">Modeled Upside</div>
                        <div style="color:{ATLAS_GREEN}; font-size:24px; font-weight:950;">{_esc(upside)}</div>
                    </div>
                    <div>
                        <div style="color:{TEXT_FAINT}; font-size:11px; font-weight:850; text-transform:uppercase;">Target</div>
                        <div style="color:{TEXT_PRIMARY}; font-size:24px; font-weight:950;">{_esc(target or 'Review')}</div>
                    </div>
                </div>

                <div style="
                    color:{TEXT_MUTED};
                    font-size:13px;
                    margin-top:16px;
                    border-top:1px solid {ATLAS_BORDER};
                    padding-top:14px;
                ">Entry zone: {_esc(entry or 'Review setup')} · Open full research report →</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(icon: str, title: str, subtitle: str | None = None):
    subtitle_html = (
        f'<div style="color:{TEXT_MUTED}; font-size:14px; margin-top:4px;">{_esc(subtitle)}</div>'
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div style="margin-top:30px; margin-bottom:16px;">
            <div style="display:flex; align-items:center; gap:12px;">
                <div style="
                    width:44px; height:44px; border-radius:15px;
                    background:{GRADIENT_HERO};
                    border:1px solid {ATLAS_BORDER};
                    display:flex; align-items:center; justify-content:center;
                    box-shadow:{SHADOW_CARD};
                    font-size:22px;
                ">{icon}</div>
                <div>
                    <div style="
                        color:{TEXT_PRIMARY};
                        font-size:30px;
                        font-weight:950;
                        letter-spacing:-0.055em;
                    ">{_esc(title)}</div>
                    {subtitle_html}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_card(title: str, body: str, icon: str = "ℹ️"):
    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            border:1px solid {ATLAS_BORDER};
            border-radius:22px;
            padding:21px 22px;
            background:{GRADIENT_CARD};
            margin:14px 0;
            box-shadow:{SHADOW_CARD};
        ">
            <div style="display:flex; gap:13px; align-items:flex-start;">
                <div style="
                    min-width:40px; width:40px; height:40px;
                    border-radius:14px;
                    background:rgba(56,189,248,0.13);
                    border:1px solid rgba(56,189,248,0.26);
                    display:flex; align-items:center; justify-content:center;
                    font-size:20px;
                ">{icon}</div>
                <div>
                    <div style="font-size:20px; font-weight:950; color:{TEXT_PRIMARY}; margin-bottom:8px;">
                        {_esc(title)}
                    </div>
                    <div style="color:{TEXT_SECONDARY}; font-size:15px; line-height:1.70;">
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
        f'<div style="color:{TEXT_MUTED}; font-size:12px; margin-top:8px; line-height:1.35;">{_esc(note)}</div>'
        if note
        else ""
    )
    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            border:1px solid {ATLAS_BORDER};
            border-radius:20px;
            padding:18px;
            background:{GRADIENT_CARD};
            min-height:118px;
            box-shadow:{SHADOW_CARD};
        ">
            <div style="color:{TEXT_MUTED}; font-size:12px; font-weight:900; text-transform:uppercase; letter-spacing:.09em;">
                {_esc(label)}
            </div>
            <div style="font-size:31px; font-weight:950; color:{TEXT_PRIMARY}; margin-top:8px; letter-spacing:-.055em;">
                {_esc(value)}
            </div>
            {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def recommendation_card(recommendation: str, classification: str, confidence: str):
    color = status_color(recommendation)
    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            border:1px solid {color}99;
            border-radius:30px;
            padding:30px;
            background:{GRADIENT_BUY if color == ATLAS_GREEN else GRADIENT_CARD};
            margin:16px 0 24px 0;
            box-shadow:{SHADOW_GLOW_GREEN if color == ATLAS_GREEN else SHADOW_CARD};
            position:relative;
            overflow:hidden;
        ">
            <div style="
                position:absolute; top:-90px; right:-90px; width:260px; height:260px;
                background:{color}22; border-radius:999px;
            "></div>
            <div style="position:relative;">
                <div style="
                    color:{TEXT_MUTED};
                    font-size:12px;
                    font-weight:950;
                    letter-spacing:.15em;
                    text-transform:uppercase;
                ">Atlas AI Verdict</div>
                <div style="
                    color:{TEXT_PRIMARY};
                    font-size:46px;
                    font-weight:950;
                    margin-top:7px;
                    letter-spacing:-.06em;
                    line-height:1.03;
                ">{_esc(recommendation)}</div>
                <div style="display:flex; gap:12px; margin-top:20px; flex-wrap:wrap;">
                    {status_pill(classification)}
                    {status_pill("Atlas Confidence™ " + confidence)}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def warning_card(title: str, body: str):
    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            border:1px solid {ATLAS_AMBER}88;
            border-radius:20px;
            padding:19px 21px;
            background:rgba(245,158,11,0.11);
            margin:14px 0;
            box-shadow:{SHADOW_CARD};
        ">
            <div style="font-size:20px; font-weight:950; color:{TEXT_PRIMARY};">⚠️ {_esc(title)}</div>
            <div style="color:#FDE68A; font-size:15px; line-height:1.65; margin-top:8px;">
                {_esc(body)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bullet_list(title: str, bullets: list[str], icon: str = "✅"):
    items = "".join(
        f"""
        <div style="display:flex; gap:9px; align-items:flex-start; margin:11px 0;">
            <div style="color:{ATLAS_GREEN}; font-weight:900;">•</div>
            <div style="color:{TEXT_SECONDARY}; font-size:15px; line-height:1.55;">{_esc(b)}</div>
        </div>
        """
        for b in bullets
    )

    st.markdown(
        f"""
        <div class="atlas-fade-in" style="
            border:1px solid {ATLAS_BORDER};
            border-radius:22px;
            padding:20px 22px;
            background:{GRADIENT_CARD};
            margin:12px 0;
            box-shadow:{SHADOW_CARD};
            min-height:236px;
        ">
            <div style="font-size:22px; font-weight:950; color:{TEXT_PRIMARY}; margin-bottom:12px;">
                {icon} {_esc(title)}
            </div>
            {items}
        </div>
        """,
        unsafe_allow_html=True,
    )


def divider():
    st.markdown(
        f"<hr style='border:0; border-top:1px solid {ATLAS_BORDER}; margin:30px 0;'>",
        unsafe_allow_html=True,
    )
