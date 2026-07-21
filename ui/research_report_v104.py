"""
Atlas V104.1 — Polished Institutional Research Cards

Drop-in replacement for ui/research_report_v104.py.
Public exports remain unchanged.
"""

from __future__ import annotations

from html import escape
from typing import Any, Mapping

import streamlit as st


def _number(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "Under review"


def _percent(value: Any, signed: bool = False) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Under review"
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.1f}%"


def _verdict_label(value: Any) -> str:
    return str(value or "MONITOR").replace("_", " ").title()


def _verdict_class(value: Any) -> str:
    verdict = str(value or "MONITOR").upper()
    return {
        "BUY_NOW": "atlas-v104-verdict-buy",
        "ACCUMULATE": "atlas-v104-verdict-accumulate",
        "AVOID": "atlas-v104-verdict-avoid",
    }.get(verdict, "atlas-v104-verdict-monitor")


def _score_class(value: Any) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "atlas-v104-score-neutral"
    if score >= 80:
        return "atlas-v104-score-strong"
    if score >= 68:
        return "atlas-v104-score-good"
    if score >= 58:
        return "atlas-v104-score-watch"
    return "atlas-v104-score-risk"


def _list_html(items: list[str], empty_text: str) -> str:
    clean = [str(item).strip() for item in items if str(item).strip()]
    if not clean:
        clean = [empty_text]
    return "".join(
        f"<li>{escape(item)}</li>"
        for item in clean[:4]
    )


def inject_v104_polish_css() -> None:
    st.markdown(
        """
        <style>
        .atlas-v104-card {
            border: 1px solid rgba(120, 145, 185, 0.28);
            border-radius: 22px;
            padding: 22px 24px 18px 24px;
            margin: 0 0 18px 0;
            background:
                radial-gradient(circle at top right,
                    rgba(44, 116, 190, 0.12), transparent 36%),
                linear-gradient(145deg,
                    rgba(12, 25, 42, 0.98),
                    rgba(8, 17, 31, 0.98));
            box-shadow: 0 14px 38px rgba(0, 0, 0, 0.22);
        }
        .atlas-v104-card-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 16px;
        }
        .atlas-v104-rank {
            color: #91a4bd;
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.13em;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        .atlas-v104-ticker {
            color: #f7f9fc;
            font-size: 2rem;
            line-height: 1;
            font-weight: 850;
        }
        .atlas-v104-company {
            color: #aeb9c8;
            font-size: 0.98rem;
            margin-top: 7px;
        }
        .atlas-v104-verdict {
            border-radius: 999px;
            padding: 8px 13px;
            font-size: 0.76rem;
            font-weight: 850;
            letter-spacing: 0.06em;
            white-space: nowrap;
            border: 1px solid transparent;
        }
        .atlas-v104-verdict-buy {
            color: #d7ffe8;
            background: rgba(24, 150, 83, 0.20);
            border-color: rgba(60, 214, 127, 0.42);
        }
        .atlas-v104-verdict-accumulate {
            color: #e2f0ff;
            background: rgba(27, 113, 191, 0.22);
            border-color: rgba(71, 157, 236, 0.42);
        }
        .atlas-v104-verdict-monitor {
            color: #fff1c4;
            background: rgba(179, 127, 20, 0.20);
            border-color: rgba(239, 188, 74, 0.42);
        }
        .atlas-v104-verdict-avoid {
            color: #ffd8df;
            background: rgba(177, 45, 64, 0.20);
            border-color: rgba(238, 85, 108, 0.42);
        }
        .atlas-v104-metrics {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 10px;
            margin-bottom: 17px;
        }
        .atlas-v104-metric {
            border: 1px solid rgba(118, 141, 174, 0.20);
            border-radius: 14px;
            background: rgba(4, 13, 26, 0.58);
            padding: 12px 13px;
            min-height: 74px;
        }
        .atlas-v104-metric-label {
            color: #8f9caf;
            font-size: 0.72rem;
            margin-bottom: 7px;
        }
        .atlas-v104-metric-value {
            color: #f6f8fc;
            font-size: 1.05rem;
            font-weight: 820;
        }
        .atlas-v104-score-strong { color: #67df9a; }
        .atlas-v104-score-good { color: #7cbcff; }
        .atlas-v104-score-watch { color: #f1c567; }
        .atlas-v104-score-risk { color: #f28496; }
        .atlas-v104-score-neutral { color: #f6f8fc; }
        .atlas-v104-thesis {
            color: #d3dbe7;
            line-height: 1.58;
            font-size: 0.94rem;
            padding: 13px 15px;
            border-radius: 14px;
            background: rgba(20, 40, 65, 0.42);
            border-left: 3px solid rgba(92, 169, 247, 0.72);
            margin-bottom: 15px;
        }
        .atlas-v104-columns {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }
        .atlas-v104-evidence {
            border: 1px solid rgba(118, 141, 174, 0.17);
            border-radius: 14px;
            background: rgba(5, 15, 29, 0.52);
            padding: 13px 15px;
        }
        .atlas-v104-evidence h4 {
            color: #f3f6fb;
            font-size: 0.82rem;
            margin: 0 0 9px 0;
        }
        .atlas-v104-evidence ul {
            margin: 0;
            padding-left: 18px;
            color: #b7c2d1;
            line-height: 1.55;
            font-size: 0.86rem;
        }
        .atlas-v104-report-hero {
            border: 1px solid rgba(108, 150, 202, 0.30);
            border-radius: 24px;
            padding: 24px;
            background:
                linear-gradient(135deg,
                    rgba(15, 40, 66, 0.98),
                    rgba(7, 18, 34, 0.98));
            margin-bottom: 18px;
        }
        .atlas-v104-report-title {
            font-size: 2.2rem;
            font-weight: 900;
            color: #f7f9fd;
        }
        .atlas-v104-report-subtitle {
            color: #aab8ca;
            margin-top: 6px;
        }
        .atlas-v104-section-title {
            color: #f5f7fb;
            font-size: 1.12rem;
            font-weight: 820;
            margin: 4px 0 12px 0;
        }
        @media (max-width: 900px) {
            .atlas-v104-metrics {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .atlas-v104-columns {
                grid-template-columns: 1fr;
            }
            .atlas-v104-ticker {
                font-size: 1.55rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_candidate_card(
    row: Mapping[str, Any],
    *,
    key_prefix: str,
) -> None:
    inject_v104_polish_css()

    ticker = str(row.get("ticker") or "UNKNOWN")
    company = str(row.get("company") or ticker)
    verdict = row.get("committee_verdict") or "MONITOR"
    rank = row.get("overall_rank") or "—"
    universe = row.get("universe_count") or "—"
    thesis = str(
        row.get("investment_thesis")
        or "Atlas selected this company for deeper research based on its "
           "relative score, evidence alignment, and portfolio relevance."
    )

    html = f"""
    <div class="atlas-v104-card">
      <div class="atlas-v104-card-head">
        <div>
          <div class="atlas-v104-rank">Research priority #{escape(str(rank))} of {escape(str(universe))}</div>
          <div class="atlas-v104-ticker">{escape(ticker)}</div>
          <div class="atlas-v104-company">{escape(company)} · {escape(str(row.get("sector") or "Unknown"))}</div>
        </div>
        <div class="atlas-v104-verdict {_verdict_class(verdict)}">{escape(_verdict_label(verdict))}</div>
      </div>

      <div class="atlas-v104-metrics">
        <div class="atlas-v104-metric">
          <div class="atlas-v104-metric-label">Opportunity</div>
          <div class="atlas-v104-metric-value {_score_class(row.get("opportunity_score"))}">{_number(row.get("opportunity_score"))}</div>
        </div>
        <div class="atlas-v104-metric">
          <div class="atlas-v104-metric-label">Confidence</div>
          <div class="atlas-v104-metric-value">{_percent(row.get("confidence_pct"))}</div>
        </div>
        <div class="atlas-v104-metric">
          <div class="atlas-v104-metric-label">Validated Return</div>
          <div class="atlas-v104-metric-value">{_percent(row.get("expected_return_pct"), signed=True)}</div>
        </div>
        <div class="atlas-v104-metric">
          <div class="atlas-v104-metric-label">Evidence Coverage</div>
          <div class="atlas-v104-metric-value">{_percent(row.get("component_coverage_pct"))}</div>
        </div>
        <div class="atlas-v104-metric">
          <div class="atlas-v104-metric-label">Suggested Position</div>
          <div class="atlas-v104-metric-value">{escape(str(row.get("position_size_range") or "0–2%"))}</div>
        </div>
      </div>

      <div class="atlas-v104-thesis">{escape(thesis)}</div>

      <div class="atlas-v104-columns">
        <div class="atlas-v104-evidence">
          <h4>Why Atlas selected it</h4>
          <ul>{_list_html(list(row.get("positive_drivers") or []), "Ranks highly relative to the reviewed universe.")}</ul>
        </div>
        <div class="atlas-v104-evidence">
          <h4>What keeps it from a stronger rating</h4>
          <ul>{_list_html(list(row.get("reasons_to_wait") or []), "No major blocker identified.")}</ul>
        </div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

    left, right = st.columns([3, 1])
    with left:
        if st.button(
            f"Open full institutional research — {ticker}",
            key=f"{key_prefix}_{ticker}_research",
            use_container_width=True,
            type="primary",
        ):
            st.session_state["v104_research_ticker"] = ticker
            st.rerun()
    with right:
        st.caption(
            f"{row.get('top_percentile_text') or 'Rank pending'} · "
            f"{row.get('opportunity_tier') or 'Under review'}"
        )


def render_full_research_report(
    row: Mapping[str, Any],
) -> None:
    inject_v104_polish_css()

    ticker = str(row.get("ticker") or "UNKNOWN")
    company = str(row.get("company") or ticker)
    verdict = row.get("committee_verdict") or "MONITOR"

    st.markdown(
        f"""
        <div class="atlas-v104-report-hero">
          <div class="atlas-v104-rank">Atlas institutional research</div>
          <div class="atlas-v104-report-title">{escape(ticker)}</div>
          <div class="atlas-v104-report-subtitle">{escape(company)} · {escape(str(row.get("sector") or "Unknown"))} · {_verdict_label(verdict)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Committee Verdict", _verdict_label(verdict))
    c2.metric("Opportunity", _number(row.get("opportunity_score")))
    c3.metric("Confidence", _percent(row.get("confidence_pct")))
    c4.metric("Position Range", row.get("position_size_range") or "0–2%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Current Price", _money(row.get("current_price")))
    c6.metric("Validated Fair Value", _money(row.get("validated_fair_value")))
    c7.metric("Expected Return", _percent(row.get("expected_return_pct"), signed=True))
    c8.metric("Evidence Coverage", _percent(row.get("component_coverage_pct")))

    st.markdown('<div class="atlas-v104-section-title">Investment Committee Thesis</div>', unsafe_allow_html=True)
    thesis = row.get("investment_thesis")
    if thesis:
        st.info(str(thesis))
    else:
        st.info(
            "A structured investment thesis was not included in the current "
            "saved scan. Atlas is displaying the available evidence scorecard."
        )

    bull, bear = st.columns(2)
    with bull:
        st.markdown("### Bull Case")
        positives = list(row.get("positive_drivers") or [])
        if positives:
            for item in positives:
                st.success(str(item), icon="✓")
        else:
            st.caption("No structured positive drivers are available.")

    with bear:
        st.markdown("### Risks / Reasons to Wait")
        waits = list(row.get("reasons_to_wait") or [])
        if waits:
            for item in waits:
                st.warning(str(item), icon="!")
        else:
            st.caption("No structured blockers are available.")

    st.markdown("### Evidence Scorecard")
    components = row.get("components") or {}
    visible = [
        (name, value)
        for name, value in components.items()
        if value is not None
    ]
    if visible:
        for name, value in visible:
            try:
                numeric = max(0.0, min(100.0, float(value)))
            except (TypeError, ValueError):
                continue
            st.progress(
                numeric / 100.0,
                text=f"{name.replace('_', ' ').title()}: {numeric:.1f}",
            )
    else:
        st.caption("No component-level evidence is available.")

    st.markdown("### Decision Conditions")
    blocker = row.get("primary_blocker")
    if verdict == "BUY_NOW":
        st.success(
            "Required evidence is sufficiently aligned for a BUY NOW verdict. "
            "Position sizing must still respect portfolio concentration rules."
        )
    elif blocker:
        st.warning(f"Primary blocker: {blocker}")
    else:
        st.info(
            "Atlas requires stronger evidence alignment before upgrading "
            "this company to BUY NOW."
        )

    if st.button(
        "Close full research",
        use_container_width=True,
        key=f"close_v104_research_{ticker}",
    ):
        st.session_state.pop("v104_research_ticker", None)
        st.rerun()


__all__ = [
    "inject_v104_polish_css",
    "render_candidate_card",
    "render_full_research_report",
]
