import streamlit as st


def section_header(icon: str, title: str, subtitle: str | None = None):
    st.markdown(
        f"""
        <div style="margin-top:28px; margin-bottom:16px;">
            <div style="display:flex; align-items:center; gap:12px;">
                <span style="font-size:28px;">{icon}</span>
                <span style="font-size:34px; font-weight:800;">{title}</span>
            </div>
            {f'<div style="color:#9CA3AF; font-size:15px; margin-top:4px;">{subtitle}</div>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_card(title: str, body: str, icon: str = "ℹ️"):
    st.markdown(
        f"""
        <div style="
            border:1px solid #30363D;
            border-radius:16px;
            padding:18px;
            background:#111827;
            margin:12px 0;
        ">
            <div style="font-size:20px; font-weight:700; margin-bottom:8px;">
                {icon} {title}
            </div>
            <div style="color:#D1D5DB; font-size:15px; line-height:1.6;">
                {body}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, note: str | None = None):
    st.markdown(
        f"""
        <div style="
            border:1px solid #30363D;
            border-radius:14px;
            padding:16px;
            background:#0F172A;
            min-height:105px;
        ">
            <div style="color:#9CA3AF; font-size:13px;">{label}</div>
            <div style="font-size:28px; font-weight:800; margin-top:6px;">{value}</div>
            {f'<div style="color:#9CA3AF; font-size:12px; margin-top:6px;">{note}</div>' if note else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def recommendation_card(recommendation: str, classification: str, confidence: str):
    st.markdown(
        f"""
        <div style="
            border:1px solid #22C55E;
            border-radius:18px;
            padding:22px;
            background:linear-gradient(135deg,#052E16,#111827);
            margin:14px 0 22px 0;
        ">
            <div style="color:#9CA3AF; font-size:14px;">Recommendation</div>
            <div style="font-size:34px; font-weight:900; margin-top:4px;">{recommendation}</div>

            <div style="display:flex; gap:14px; margin-top:16px; flex-wrap:wrap;">
                <span style="
                    padding:8px 12px;
                    border-radius:999px;
                    background:#1F2937;
                    border:1px solid #374151;
                    font-weight:700;
                ">{classification}</span>

                <span style="
                    padding:8px 12px;
                    border-radius:999px;
                    background:#1F2937;
                    border:1px solid #374151;
                    font-weight:700;
                ">Confidence: {confidence}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def warning_card(title: str, body: str):
    st.markdown(
        f"""
        <div style="
            border:1px solid #F59E0B;
            border-radius:16px;
            padding:18px;
            background:#1F1A0A;
            margin:12px 0;
        ">
            <div style="font-size:20px; font-weight:800;">⚠️ {title}</div>
            <div style="color:#FDE68A; font-size:15px; line-height:1.6; margin-top:8px;">
                {body}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def bullet_list(title: str, bullets: list[str], icon: str = "✅"):
    st.markdown(f"### {icon} {title}")
    for b in bullets:
        st.markdown(f"- {b}")


def divider():
    st.markdown("<hr style='border:0; border-top:1px solid #30363D; margin:24px 0;'>", unsafe_allow_html=True)