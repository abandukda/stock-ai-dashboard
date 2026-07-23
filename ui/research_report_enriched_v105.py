from __future__ import annotations
from html import escape
from typing import Any, Mapping
import pandas as pd
import streamlit as st
from engines.research_enrichment_v105 import build_enriched_research_report

def _score(v):
    try: return f"{float(v):.1f}"
    except (TypeError, ValueError): return "Under review"

def _pct(v):
    try: return f"{float(v):.1f}%"
    except (TypeError, ValueError): return "Under review"

def _money(v):
    try: return f"${float(v):,.2f}"
    except (TypeError, ValueError): return "Under review"

def _meta(section: Mapping[str, Any]):
    st.caption(
        f"Status: {section.get('status','unavailable')} · "
        f"Source: {section.get('source','Unknown')} · "
        f"As of: {section.get('as_of','Unknown')}"
    )

def _grid(data, money_keys=(), pct_keys=()):
    scalar = [(k,v) for k,v in data.items() if not isinstance(v,(list,dict))]
    if not scalar:
        st.info("This section is unavailable in the current Atlas payload.")
        return
    for start in range(0,len(scalar),4):
        cols=st.columns(4)
        for col,(key,value) in zip(cols,scalar[start:start+4]):
            label=key.replace("_"," ").title()
            display=_money(value) if key in money_keys else _pct(value) if key in pct_keys else value
            col.metric(label,display)

def render_v105_enriched_research(row: Mapping[str, Any]) -> None:
    report=build_enriched_research_report(row)
    st.markdown(f"# {escape(report['ticker'])} Institutional Research")
    st.caption(
        f"{escape(report['company'])} · {escape(report['sector'])} · "
        f"{str(report['committee_verdict']).replace('_',' ').title()}"
    )
    c=st.columns(4)
    c[0].metric("Opportunity",_score(report.get("opportunity_score")))
    c[1].metric("Confidence",_pct(report.get("confidence_pct")))
    c[2].metric("Suggested Allocation",report.get("position_size_range"))
    c[3].metric("Research Version","V105")

    if report.get("executive_summary"):
        st.markdown("## Executive Summary")
        st.write(report["executive_summary"])

    tabs=st.tabs([
        "Financials","Wall Street","Earnings & Transcript","Recent News",
        "Political","Ownership & Insiders","Technicals","Decision"
    ])

    with tabs[0]:
        section=report["financials"]; st.markdown("### Financial Intelligence"); _meta(section)
        _grid(section.get("data") or {},
              money_keys={"free_cash_flow","cash","debt"},
              pct_keys={"revenue_growth_pct","eps_growth_pct","gross_margin_pct","operating_margin_pct","net_margin_pct","roe_pct","roic_pct"})
    with tabs[1]:
        section=report["analysts"]; st.markdown("### Wall Street & Analyst Intelligence"); _meta(section)
        data=section.get("data") or {}
        _grid(data,money_keys={"average_target","high_target","low_target","top_analyst_target","highest_published_target"})
        if data.get("label_note"): st.info(data["label_note"])
    with tabs[2]:
        section=report["earnings"]; st.markdown("### Earnings & Transcript Intelligence"); _meta(section)
        data=section.get("data") or {}
        _grid(data,pct_keys={"eps_surprise_pct","revenue_surprise_pct"})
        for key in ("guidance","management_tone","transcript_summary","important_quote"):
            if data.get(key):
                st.markdown(f"#### {key.replace('_',' ').title()}"); st.write(data[key])
    with tabs[3]:
        section=report["news"]; st.markdown("### Recent News & Catalysts"); _meta(section)
        items=section.get("data") or []
        if not items: st.info("No current news items were included in the saved Atlas payload.")
        for item in items:
            with st.container(border=True):
                st.markdown(f"**{item.get('headline','Headline unavailable')}**")
                detail=" · ".join(x for x in (item.get("source"),item.get("date"),item.get("sentiment")) if x)
                if detail: st.caption(detail)
                if item.get("summary"): st.write(item["summary"])
                if item.get("impact") is not None: st.metric("Impact Score",_score(item["impact"]))
    with tabs[4]:
        section=report["political"]; st.markdown("### Political & Government Intelligence"); _meta(section)
        data=section.get("data") or {}; _grid(data,pct_keys={"political_support_score"})
        if data.get("transactions"):
            st.markdown("#### Recent Political Transactions")
            st.dataframe(pd.DataFrame(data["transactions"]),hide_index=True,use_container_width=True)
    with tabs[5]:
        section=report["ownership"]; st.markdown("### Institutional Ownership & Insider Activity"); _meta(section)
        data=section.get("data") or {}
        _grid(data,pct_keys={"institutional_ownership_pct","institutional_change_pct"})
        if data.get("major_holders"):
            st.markdown("#### Major Holders")
            st.dataframe(pd.DataFrame(data["major_holders"]),hide_index=True,use_container_width=True)
        if data.get("insider_transactions"):
            st.markdown("#### Insider Transactions")
            st.dataframe(pd.DataFrame(data["insider_transactions"]),hide_index=True,use_container_width=True)
    with tabs[6]:
        section=report["technical"]; st.markdown("### Technical Intelligence"); _meta(section)
        _grid(section.get("data") or {},money_keys={"price","sma20","sma50","sma200","support","resistance"})
    with tabs[7]:
        st.markdown("### Atlas Decision")
        bull,bear=st.columns(2)
        with bull:
            st.markdown("#### Why Atlas Selected It")
            for item in report.get("positive_drivers") or []: st.success(str(item))
        with bear:
            st.markdown("#### What Prevents a Stronger Rating")
            for item in report.get("reasons_to_wait") or []: st.warning(str(item))
        st.markdown("### Data Availability")
        rows=[]
        for key in ("financials","analysts","earnings","news","political","ownership","technical"):
            section=report[key]
            rows.append({"Section":key.title(),"Status":section.get("status"),"Source":section.get("source"),"As Of":section.get("as_of")})
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)

__all__=["render_v105_enriched_research"]
