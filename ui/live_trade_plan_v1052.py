from __future__ import annotations
from typing import Any, Callable, Mapping
import streamlit as st
from engines.trade_plan_v1052 import build_trade_plan
from engines.individualized_scoring_v1052 import calculate_individualized_scores
from engines.evidence_synthesis_v1052 import build_ai_guidance
from services.quote_refresh_v1052 import get_quotes_with_fallback

def _money(v):
    try: return f"${float(v):,.2f}"
    except (TypeError,ValueError): return "Unavailable"

def render_trade_plan_panel(row: Mapping[str,Any],quote: Mapping[str,Any],report: Mapping[str,Any] | None=None) -> None:
    plan=build_trade_plan(row,quote)
    scores=calculate_individualized_scores(row)
    guidance=build_ai_guidance(report or {},plan,scores)
    st.markdown("### Atlas Entry, Exit & Risk Plan")
    if not plan.get("actionable"):
        st.warning(plan.get("reason","Trade plan unavailable."))
        return
    c=st.columns(5)
    c[0].metric("Latest Price",_money(plan.get("current_price")))
    c[1].metric("Entry Zone",f"{_money(plan.get('entry_low'))}–{_money(plan.get('entry_high'))}")
    c[2].metric("Stop",_money(plan.get("stop_loss")))
    c[3].metric("Target 1",_money(plan.get("target_1")))
    c[4].metric("Target 2",_money(plan.get("target_2")))
    c=st.columns(5)
    c[0].metric("Atlas Target",_money(plan.get("atlas_target")))
    c[1].metric("Analyst Avg.",_money(plan.get("analyst_average_target")))
    c[2].metric("Do Not Chase",_money(plan.get("do_not_chase")))
    c[3].metric("R/R to T1",plan.get("risk_reward_target_1"))
    c[4].metric("Horizon",(plan.get("horizon") or {}).get("primary"))
    st.caption(
        f"Price as of {quote.get('price_as_of','Unknown')} · "
        f"Source: {quote.get('quote_source','Unknown')} · "
        f"Market: {quote.get('market_status','Unknown')} · Refresh interval: 30 minutes"
    )
    st.info(guidance["summary"])
    st.caption(guidance["educational_disclaimer"])

def render_research_quote_fragment(
    row: Mapping[str,Any],
    report: Mapping[str,Any],
    fetcher: Callable,
    provider_key: str,
) -> None:
    ticker=str(row.get("ticker") or "").upper()
    @st.fragment(run_every="30m")
    def _fragment():
        prior=st.session_state.get(f"last_quote_{ticker}",{})
        result=get_quotes_with_fallback([ticker],fetcher,provider_key,prior)
        quote=(result.get("quotes") or {}).get(ticker)
        if quote:
            st.session_state[f"last_quote_{ticker}"]={ticker:quote}
            render_trade_plan_panel(row,quote,report)
        else:
            st.warning("Quote unavailable. Atlas retained the last valid research data and did not generate a price plan.")
    _fragment()

__all__=["render_trade_plan_panel","render_research_quote_fragment"]
