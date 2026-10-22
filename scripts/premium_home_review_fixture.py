"""Generated presentation fixture. Not production, market data or certification."""
import streamlit as st
from ui.home_guidance_vnext import render_home_guidance_vnext

st.set_page_config(layout='wide',page_title='ATLAS generated review fixture')
st.warning('GENERATED FIXTURE — NOT MARKET DATA OR PRODUCTION VERIFICATION')
# Reproduce an already-imported stylesheet surviving a code deployment.
import ui.premium_home_styles as stale_styles
stale_styles.PREMIUM_HOME_CSS='/* GENERATED STALE IMPORT CASE */'
if hasattr(stale_styles,'__atlas_presentation_source_sha256__'):
    del stale_styles.__atlas_presentation_source_sha256__
cards=[]
for rank,ticker in enumerate(('FIXTURE_A','FIXTURE_B','FIXTURE_C','CODA'),start=1):
    cards.append({'ticker':ticker,'company':'Generated company '+str(rank),'guidance':'BUY_NOW',
        'production_rank':rank,'display_price':100+rank,'display_price_label':'Dated fixture price',
        'atlas_fair_value':120+rank,'atlas_expected_return':19.8,'opportunity':80-rank,
        'decision_confidence':85,'decision_as_of':'2026-10-04T16:21:00Z',
        'certified_summary_facts':{'business_driver':'Generated recurring revenue supports this illustrative investment case',
            'primary_risk':'Generated valuation assumptions could prove too optimistic'}})
render_home_guidance_vnext({'cards':cards,'home_featured_cards':cards,'scan_timestamp':'2026-10-04T16:21:00Z',
    'home_runtime_contract':{'runtime_ready':True,'inventory_authority':{'publishable_buy_now_count':4}},
    'market_today':{'status':'GENERATED_FIXTURE','as_of':'2026-10-15T20:00:00Z','instruments':[{'symbol':'FIXTURE_'+str(i),'price':100+i,'change_pct':.25*i} for i in range(1,5)],'interpretation':'Generated illustrative market context, not current market evidence.'}},
    emit_interactive=lambda: st.markdown('<span data-fixture-ready="true">Fixture ready</span>',unsafe_allow_html=True))

st.markdown('<span data-fixture-complete="true">Fixture complete</span>',unsafe_allow_html=True)

st.markdown('<span data-fixture-selected-ticker="'+str(st.session_state.get('active_research_ticker',''))+'"></span>',unsafe_allow_html=True)
