"""Full Scan VNext: faithful presentation of the persisted production scan."""
from __future__ import annotations

from html import escape
from typing import Any, Callable, Final, Mapping

import pandas as pd
import streamlit as st

from engines.full_scan_decision_story import (
    FULL_SCAN_DECISION_STORY_VERSION, NO_PRIOR_SCAN_COMPARISON,
    build_full_scan_decision_story,
)
from services.session_stability import emit_page_interactive


FULL_SCAN_VNEXT_VERSION: Final = "ATLAS_FULL_SCAN_VNEXT_V1"


def _source_row(value: Any) -> dict[str, Any]:
    return dict(value) if hasattr(value, "items") else {}


def _display(value: Any, fallback: str = "Unavailable") -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return fallback
    result = str(value).strip()
    return result or fallback


def _number(value: Any, *, money: bool = False, pct: bool = False, signed: bool = False) -> str:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return "Unavailable"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _display(value)
    if money:
        return f"-${abs(number):,.2f}" if number < 0 else f"${number:,.2f}"
    if pct:
        return f"{number:+.1f}%" if signed else f"{number:.1f}%"
    return f"{number:,.1f}"


def _ratio_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:+,.1f}%"
    except (TypeError, ValueError):
        return "Unavailable"


def _production_stories(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    stories = []
    for fallback_rank, (_, row) in enumerate(frame.iterrows(), start=1):
        wrapper = _source_row(row)
        try:
            production_rank = int(wrapper.get("Production Rank"))
        except (TypeError, ValueError):
            production_rank = fallback_rank
        story = build_full_scan_decision_story(wrapper, production_rank=production_rank)
        raw = wrapper.get("Raw") if isinstance(wrapper.get("Raw"), Mapping) else wrapper
        story["_sector"] = _display(raw.get("sector") or wrapper.get("Sector"), "Unavailable")
        stories.append(story)
    return sorted(stories, key=lambda story: int(story["production_rank"]))


def _filter_stories(
    stories: list[dict[str, Any]], *, search: str = "", state: str = "All",
    sector: str = "All", technical: str = "All", evidence: str = "All",
    require_opportunity: bool = False, minimum_opportunity: float = 0,
) -> list[dict[str, Any]]:
    query = search.strip().lower()
    filtered: list[dict[str, Any]] = []
    for story in stories:
        identity = story["identity"]
        raw_sector = str(story.get("_sector") or "Unavailable")
        tech = story["technical_state"].get("state") or "State not published"
        state_value = story.get("canonical_state") or "Decision unavailable"
        health = story["evidence_health"]
        opportunity = story.get("opportunity")
        if query and query not in f"{identity['ticker']} {identity['company']}".lower():
            continue
        if state != "All" and state_value != state:
            continue
        if sector != "All" and raw_sector != sector:
            continue
        if technical != "All" and tech != technical:
            continue
        if evidence == "High" and health["available"] < max(1, health["total"] - 1):
            continue
        if evidence == "Partial" and not (0 < health["available"] < max(1, health["total"] - 1)):
            continue
        if evidence == "Unavailable" and health["available"]:
            continue
        if require_opportunity and opportunity is None:
            continue
        if opportunity is not None and float(opportunity) < minimum_opportunity:
            continue
        filtered.append(story)
    for position, story in enumerate(filtered, start=1):
        story["filtered_position"] = position
    return filtered


def _inject_css() -> None:
    st.markdown(
        """
<style>
body:has([data-atlas-full-scan-version]) [data-testid="stAppViewContainer"]{overflow-x:hidden}
.atlas-full-scan-snapshot{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin:.4rem 0 1rem}
.atlas-full-scan-stat,.atlas-full-scan-card{border:1px solid rgba(148,163,184,.22);border-radius:1rem;background:rgba(15,23,42,.42)}
.atlas-full-scan-stat{padding:.75rem}.atlas-full-scan-stat span{display:block;color:#94a3b8;font-size:.76rem}.atlas-full-scan-stat b{font-size:1.05rem}
.atlas-full-scan-card{padding:1rem;margin:.7rem 0}.atlas-full-scan-rank{color:#93c5fd;font-size:.8rem;font-weight:800;letter-spacing:.04em;text-transform:uppercase}
.atlas-full-scan-card h3{margin:.18rem 0 .3rem}.atlas-full-scan-state{font-weight:750;margin:.2rem 0 .65rem}
.atlas-full-scan-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.45rem}.atlas-full-scan-metric{border:1px solid rgba(148,163,184,.16);border-radius:.65rem;padding:.5rem;min-width:0}
.atlas-full-scan-metric span{display:block;color:#94a3b8;font-size:.72rem}.atlas-full-scan-metric b{display:block;overflow-wrap:anywhere}
.atlas-full-scan-why{margin:.7rem 0 .35rem}.atlas-full-scan-constraint{color:#fda4af}.atlas-full-scan-desktop-summary{display:block}.atlas-full-scan-mobile-summary{display:none}
@media(max-width:700px){
 body:has([data-atlas-full-scan-version]) [data-testid="stRadio"]:has([role="radiogroup"]){position:sticky!important;top:3.75rem!important;z-index:990!important;margin-top:.35rem!important;background:var(--background-color,#0e1117)}
 body:has([data-atlas-full-scan-version]) [data-testid="stRadio"] [role="radiogroup"]{flex-wrap:nowrap!important;overflow-x:auto!important}
 body:has([data-atlas-full-scan-version]) [data-testid="stRadio"] [role="radiogroup"] label{flex:0 0 auto!important;white-space:nowrap}
 .atlas-full-scan-snapshot{grid-template-columns:repeat(2,minmax(0,1fr));gap:.35rem}.atlas-full-scan-card{padding:.7rem;margin:.45rem 0 1rem;margin-right:4.75rem}
 .atlas-full-scan-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:.3rem}.atlas-full-scan-metric{padding:.4rem}.atlas-full-scan-desktop-summary{display:none}.atlas-full-scan-mobile-summary{display:block}
 body:has([data-atlas-full-scan-version]) [data-testid="stButton"]{margin-right:5.25rem}
 body:has([data-atlas-full-scan-version]) [data-testid="stMainBlockContainer"]{padding-top:.25rem!important;padding-bottom:6rem!important}
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _metric(label: str, value: str) -> str:
    return f'<div class="atlas-full-scan-metric"><span>{escape(label)}</span><b>{escape(value)}</b></div>'


def _evidence_rows(values: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for key, value in values.items():
        if value is None or isinstance(value, (Mapping, list, tuple, set)):
            continue
        label = key.replace("_", " ").title()
        if key in {"revenue_growth", "earnings_growth", "gross_margin", "operating_margin"}:
            display = _ratio_pct(value)
        elif key in {"free_cash_flow", "cash", "debt"}:
            display = _number(value, money=True)
        elif key.endswith("_pct"):
            display = _number(value, pct=True, signed=True)
        else:
            display = _display(value)
        rows.append({"Evidence": label, "Value": display})
    return pd.DataFrame(rows)


def _render_story(story: Mapping[str, Any], *, total_filtered: int, open_research: Callable[[str], Any]) -> None:
    identity = story["identity"]
    ticker = identity["ticker"]
    decision = story["production_decision"]
    valuation = story["valuation"]
    technical = story["technical_state"]
    availability = story.get("decision_availability") or {}
    why = list(story.get("why_ranked") or ())
    constraints = list(story.get("constraints") or ())
    st.markdown(
        '<span data-atlas-full-scan-candidate="true" '
        f'data-atlas-ticker="{escape(ticker)}" '
        f'data-atlas-production-rank="{int(story["production_rank"])}" '
        f'data-atlas-filtered-position="{int(story["filtered_position"])}" '
        f'data-atlas-decision-status="{escape(str(story.get("canonical_state_status") or "DATA_UNAVAILABLE"))}" '
        f'data-atlas-recommendation="{escape(str(decision.get("recommendation") or ""))}" '
        f'data-atlas-opportunity="{escape(str(story.get("opportunity") if story.get("opportunity") is not None else ""))}" '
        f'data-atlas-confidence="{escape(str(story.get("confidence") if story.get("confidence") is not None else ""))}" '
        f'data-atlas-evidence-available="{int(story["evidence_health"]["available"])}" '
        f'data-atlas-evidence-total="{int(story["evidence_health"]["total"])}" '
        'aria-hidden="true" style="display:none"></span>', unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="atlas-full-scan-card">'
        f'<div class="atlas-full-scan-rank">Production Rank #{story["production_rank"]} · '
        f'Filtered Position #{story["filtered_position"]} of {total_filtered}</div>'
        f'<h3>{escape(ticker)} · {escape(identity["company"])}</h3>'
        f'<div class="atlas-full-scan-state">{escape(_display(story.get("canonical_state"), "Decision unavailable"))} · '
        f'{escape(story["actionability"]["state"])}</div>'
        '<div class="atlas-full-scan-metrics">'
        + _metric("Opportunity", _number(story.get("opportunity")))
        + _metric(_display(availability.get("confidence_label"), "Confidence"), _number(story.get("confidence"), pct=True))
        + _metric("Atlas FV", _number(valuation.get("atlas_fair_value"), money=True))
        + _metric("Expected Return", _number(valuation.get("expected_return"), pct=True, signed=True))
        + _metric("Technical state", _display(technical.get("state"), "State not published"))
        + _metric("Evidence health", story["evidence_health"]["label"])
        + '</div>'
        '<div class="atlas-full-scan-why"><b>Why Ranked Here</b><br>'
        + escape(" · ".join(why) if why else "No persisted factor explanation is available.") + '</div>'
        f'<div class="atlas-full-scan-constraint"><b>Primary constraint:</b> '
        f'{escape(constraints[0] if constraints else "No specific persisted constraint is available.")}</div>'
        '</div>', unsafe_allow_html=True,
    )
    if not availability.get("decision_available"):
        st.info(_display(availability.get("customer_reason"), story["actionability"]["explanation"]))
        evidence_present = list(availability.get("evidence_present") or ())
        missing = list(availability.get("missing_confirmation") or ())
        waiting = list(availability.get("what_atlas_is_waiting_for") or ())
        if evidence_present:
            st.caption("Evidence present: " + " · ".join(map(str, evidence_present)))
        if missing:
            st.caption("Missing confirmation: " + " · ".join(map(str, missing)))
        if waiting:
            st.caption("What ATLAS is waiting for: " + " · ".join(map(str, waiting)))
    if st.button(f"View Investment Case — {ticker}", key=f"full_scan_research_{ticker}_{story['production_rank']}", width="stretch"):
        open_research(ticker)
    with st.expander(f"Evidence details — {ticker}", expanded=False):
        st.caption(NO_PRIOR_SCAN_COMPARISON)
        tabs = st.tabs(["Fundamentals / Earnings", "Analyst / Valuation", "Catalysts / News", "Risk / Recovery", "Provenance"])
        progressive = story["progressive_evidence"]
        with tabs[0]:
            frame = _evidence_rows(progressive["fundamentals_earnings"])
            st.dataframe(frame, hide_index=True, use_container_width=True) if not frame.empty else st.caption("Fundamental and earnings detail is unavailable.")
        with tabs[1]:
            st.markdown(f"**Atlas FV:** {_number(valuation.get('atlas_fair_value'), money=True)}")
            st.markdown(f"**Expected Return:** {_number(valuation.get('expected_return'), pct=True, signed=True)}")
            st.markdown(f"**Wall Street consensus:** {_number(valuation.get('wall_street_mean'), money=True)}")
            st.caption(f"Wall Street range: {_number(valuation.get('wall_street_low'), money=True)}–{_number(valuation.get('wall_street_high'), money=True)}")
            st.caption("Wall Street evidence is contextual and remains separate from Atlas valuation.")
        with tabs[2]:
            items = progressive["catalysts_news"]["items"]
            if items:
                for item in items:
                    headline = item.get("headline") or item.get("title") or "Headline unavailable"
                    publisher = item.get("publisher_name") or item.get("publisher") or item.get("source") or "Publisher unavailable"
                    st.markdown(f"- {_display(headline)} — {_display(publisher)}")
            else:
                st.caption("Verified catalyst/news detail is unavailable.")
        with tabs[3]:
            for item in constraints:
                st.markdown(f"- {_display(item)}")
            recovery = progressive["recovery"]
            if recovery.get("score") is not None or recovery.get("label"):
                st.caption(f"Recovery context: {_display(recovery.get('label'))} · score {_number(recovery.get('score'))}")
            else:
                st.caption("Canonical Recovery evidence is unavailable for this row.")
        with tabs[4]:
            st.caption(f"Scan time: {_display(story['provenance'].get('scan_time'))}")
            st.caption(story["evidence_health"]["label"])
            st.caption("Full Scan VNext reads persisted evidence only; no provider acquisition occurs on entry.")


def render_full_scan_vnext(
    frame: pd.DataFrame,
    *,
    open_research: Callable[[str], Any],
    emit_interactive: Callable[[], Any] | None = None,
) -> None:
    """Render the authoritative Full Scan customer presentation."""
    _inject_css()
    stories = _production_stories(frame)
    st.markdown(
        f'<span data-atlas-full-scan-version="{FULL_SCAN_VNEXT_VERSION}" '
        f'data-atlas-story-version="{FULL_SCAN_DECISION_STORY_VERSION}" '
        f'data-atlas-production-population="{len(stories)}" aria-hidden="true" style="display:none"></span>',
        unsafe_allow_html=True,
    )
    st.title("Full Scan Intelligence")
    st.caption("The persisted production ranking, presented without recalculating investment authority.")
    if not stories:
        st.info("No persisted Full Scan candidates are available.")
        (emit_interactive or (lambda: emit_page_interactive(st, "Full Ranked Scan")))()
        return

    states = sorted({_display(item.get("canonical_state"), "Decision unavailable") for item in stories})
    sectors = sorted({str(item.get("_sector") or "Unavailable") for item in stories})
    technicals = sorted({_display(item["technical_state"].get("state"), "State not published") for item in stories})
    c1, c2, c3 = st.columns(3)
    search = c1.text_input("Search ticker/company", key="full_scan_vnext_search")
    state = c2.selectbox("Canonical ATLAS state", ["All", *states], key="full_scan_vnext_state")
    sector = c3.selectbox("Sector", ["All", *sectors], key="full_scan_vnext_sector")
    c4, c5, c6 = st.columns(3)
    technical = c4.selectbox("Technical state", ["All", *technicals], key="full_scan_vnext_technical")
    evidence = c5.selectbox("Evidence completeness", ["All", "High", "Partial", "Unavailable"], key="full_scan_vnext_evidence")
    require_opportunity = c6.checkbox("Require published Opportunity", key="full_scan_vnext_require_opportunity")
    minimum_opportunity = st.slider("Minimum published Opportunity", 0, 100, 0, disabled=not require_opportunity, key="full_scan_vnext_min_opportunity")
    filtered = _filter_stories(
        stories, search=search, state=state, sector=sector, technical=technical,
        evidence=evidence, require_opportunity=require_opportunity,
        minimum_opportunity=minimum_opportunity,
    )
    scan_time = next((item["provenance"].get("scan_time") for item in stories if item["provenance"].get("scan_time")), None)
    st.markdown(
        '<div class="atlas-full-scan-snapshot">'
        f'<div class="atlas-full-scan-stat"><span>Production population</span><b>{len(stories)}</b></div>'
        f'<div class="atlas-full-scan-stat"><span>Current filtered count</span><b>{len(filtered)}</b></div>'
        f'<div class="atlas-full-scan-stat"><span>Scan timestamp</span><b>{escape(_display(scan_time))}</b></div>'
        '<div class="atlas-full-scan-stat"><span>Status</span><b>Persisted production snapshot</b></div>'
        '</div>', unsafe_allow_html=True,
    )
    st.info("Filters alter only the visible subset. Production Rank never changes.")
    st.caption("Atlas FV is shown separately from Wall Street consensus; neither is recalculated on this page.")
    st.caption(NO_PRIOR_SCAN_COMPARISON)
    mark_interactive = emit_interactive or (lambda: emit_page_interactive(st, "Full Ranked Scan"))
    if not filtered:
        st.warning("No persisted candidates match the current presentation filters.")
        mark_interactive()
        return
    _render_story(filtered[0], total_filtered=len(filtered), open_research=open_research)
    mark_interactive()
    for story in filtered[1:]:
        _render_story(story, total_filtered=len(filtered), open_research=open_research)


__all__ = [
    "FULL_SCAN_VNEXT_VERSION", "render_full_scan_vnext",
    "_filter_stories", "_production_stories",
]
