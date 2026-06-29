
"""
Atlas Global Layout CSS — Sprint 3.1
"""

from __future__ import annotations

import streamlit as st

from ui.theme import ATLAS_BORDER, GRADIENT_APP, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

            html, body, [class*="css"] {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
            }}

            .stApp {{
                background: {GRADIENT_APP};
                color: {TEXT_PRIMARY};
            }}

            .block-container {{
                padding-top: 2rem !important;
                padding-bottom: 4rem !important;
                max-width: 1480px !important;
            }}

            h1, h2, h3 {{
                letter-spacing: -0.045em !important;
                color: {TEXT_PRIMARY} !important;
            }}

            p, li, label, span {{
                line-height: 1.58;
            }}

            section[data-testid="stSidebar"] {{
                background: rgba(5,11,20,0.96);
                border-right: 1px solid {ATLAS_BORDER};
                backdrop-filter: blur(18px);
            }}

            section[data-testid="stSidebar"] * {{
                color: {TEXT_SECONDARY};
            }}

            div[data-testid="stExpander"] {{
                border: 1px solid {ATLAS_BORDER} !important;
                border-radius: 18px !important;
                background: rgba(15, 23, 42, 0.76) !important;
                box-shadow: 0 10px 28px rgba(0,0,0,0.22);
                overflow: hidden;
            }}

            div[data-testid="stExpander"] summary {{
                font-weight: 850 !important;
                color: {TEXT_PRIMARY} !important;
                font-size: 16px !important;
                padding: 16px 18px !important;
            }}

            div[data-testid="stMetric"] {{
                background: linear-gradient(145deg, rgba(15,23,42,0.96), rgba(17,24,39,0.94));
                border: 1px solid {ATLAS_BORDER};
                border-radius: 18px;
                padding: 18px;
                box-shadow: 0 10px 28px rgba(0,0,0,0.22);
            }}

            div[data-testid="stMetricLabel"] {{
                color: {TEXT_MUTED} !important;
                font-size: 12px !important;
                font-weight: 800 !important;
                letter-spacing: .08em !important;
                text-transform: uppercase !important;
            }}

            div[data-testid="stMetricValue"] {{
                color: {TEXT_PRIMARY} !important;
                font-weight: 900 !important;
                letter-spacing: -0.045em !important;
            }}

            .stDataFrame {{
                border-radius: 18px;
                overflow: hidden;
                border: 1px solid {ATLAS_BORDER};
            }}

            div[data-testid="stHorizontalBlock"] {{
                gap: 1.15rem;
            }}

            button {{
                border-radius: 999px !important;
                font-weight: 800 !important;
            }}

            .atlas-fade-in {{
                animation: atlasFadeIn .45s ease both;
            }}

            @keyframes atlasFadeIn {{
                from {{ opacity: 0; transform: translateY(8px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )
