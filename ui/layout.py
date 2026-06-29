
"""
Atlas layout and global CSS.

Call inject_css() once near the top of app.py when ready.
Current components also carry inline styles, so this file is safe even before full integration.
"""

import streamlit as st

from ui.theme import ATLAS_BG, ATLAS_BORDER, ATLAS_CARD, TEXT_PRIMARY, TEXT_SECONDARY


def inject_css():
    st.markdown(
        f"""
        <style>
            .stApp {{
                background:
                    radial-gradient(circle at top left, rgba(34,197,94,0.10), transparent 30%),
                    radial-gradient(circle at top right, rgba(56,189,248,0.10), transparent 28%),
                    {ATLAS_BG};
                color: {TEXT_PRIMARY};
            }}

            section[data-testid="stSidebar"] {{
                background: #07111F;
                border-right: 1px solid {ATLAS_BORDER};
            }}

            div[data-testid="stMetric"] {{
                background: {ATLAS_CARD};
                border: 1px solid {ATLAS_BORDER};
                padding: 14px;
                border-radius: 16px;
            }}

            div[data-testid="stExpander"] {{
                border: 1px solid {ATLAS_BORDER};
                border-radius: 18px;
                background: rgba(15, 23, 42, 0.72);
                box-shadow: 0 8px 22px rgba(0,0,0,0.16);
                margin-bottom: 12px;
            }}

            div[data-testid="stExpander"] summary {{
                font-weight: 800;
                color: {TEXT_PRIMARY};
                font-size: 16px;
            }}

            .stDataFrame {{
                border-radius: 18px;
                overflow: hidden;
                border: 1px solid {ATLAS_BORDER};
            }}

            h1, h2, h3 {{
                letter-spacing: -0.03em;
            }}

            p, li {{
                color: {TEXT_SECONDARY};
                line-height: 1.62;
            }}

            button[kind="primary"] {{
                border-radius: 999px !important;
                font-weight: 800 !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )
