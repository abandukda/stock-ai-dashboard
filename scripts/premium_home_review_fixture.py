"""Generated presentation fixture. Not production, market data or certification."""
import streamlit as st
from ui.home_guidance_vnext import render_home_guidance_vnext

st.set_page_config(layout='wide',page_title='ATLAS generated review fixture')
st.warning('GENERATED FIXTURE — NOT MARKET DATA OR PRODUCTION VERIFICATION')
cards=[]
for rank,ticker in enumerate(('FIXTURE_A','FIXTURE_B','FIXTURE_C','FIXTURE_D'),start=1):
    cards.append({'ticker':ticker,'company':'Generated company '+str(rank),'guidance':'BUY_NOW',
        'production_rank':rank,'display_price':100+rank,'display_price_label':'Dated fixture price',
        'atlas_fair_value':120+rank,'atlas_expected_return':19.8,'opportunity':80-rank,
        'decision_confidence':85,'decision_as_of':'2026-10-04T16:21:00Z',
        'certified_summary_facts':{'business_driver':'Generated recurring revenue supports this illustrative investment case',
            'primary_risk':'Generated valuation assumptions could prove too optimistic'}})
render_home_guidance_vnext({'cards':cards,'home_featured_cards':cards,'scan_timestamp':'2026-10-04T16:21:00Z',
    'home_runtime_contract':{'runtime_ready':True,'inventory_authority':{'publishable_buy_now_count':4}},
    'market_today':{'status':'DATA_UNAVAILABLE','interpretation':'No current governed market context is supplied to this generated fixture.'}},
    emit_interactive=lambda: st.markdown('<span data-fixture-ready="true">Fixture ready</span>',unsafe_allow_html=True))
