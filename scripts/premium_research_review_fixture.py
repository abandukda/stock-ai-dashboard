"""Full customer renderer with generated evidence. Never production or certification."""
from datetime import date, timedelta
import streamlit as st
from ui.customer_research_v2 import render_customer_research_v2

st.set_page_config(layout='wide', page_title='ATLAS generated Research review')
st.warning('GENERATED FIXTURE — NOT MARKET DATA OR PRODUCTION VERIFICATION')
ticker=str(st.query_params.get('ticker','NVDA')).upper()
if ticker not in {'NVDA','MSFT','META','ANET'}: st.stop()
warm_admission = st.query_params.get('warm_admission') == '1'
if warm_admission:
    # Reproduce a new UI meeting an already-imported older financial dependency.
    import services.research_market_read_model as financial
    if hasattr(financial, 'public_admission_marker_values'):
        delattr(financial, 'public_admission_marker_values')
    st.markdown('<span data-warm-admission-fixture="true"></span>', unsafe_allow_html=True)
def field(name,value):
    return {'name':name,'value':value,'certification_status':'CERTIFIED', 'source':'GENERATED_FIXTURE',
            'as_of':'2026-10-02T20:00:00Z','evidence_ids':['generated:'+ticker+':'+name],'unit':'PER_SHARE'}
certified={'ticker':ticker,'customer_publication_allowed':True,
           'decision':{'action':'BUY_NOW','opportunity':79,'decision_confidence':81,
                       'six_pillars':{'valuation_quality':80,'fundamental_quality':78}},
           'fields':{'price':field('price',101),'atlas_fair_value':field('atlas_fair_value',121)},
           'digests':{'evaluation_snapshot_id':'generated-snapshot-'+ticker}}
rows=[]
for i in range(125):
    day=date(2026,5,1)+timedelta(days=i)
    if day.weekday()<5:
        close=80+i*.15
        rows.append({'date':str(day),'close':close,'open':close-.2,'high':close+1,'low':close-1,'volume':1000+i})
report={'ticker':ticker,'company':ticker+' · Generated demonstration company','sector':'Generated sector',
        'candidate_digest':'generated-candidate','publication_digest':'generated-publication','source_sha':'generated-source',
        'certified_customer_evaluation':certified,
        'publication_certification':{'publication_digest':'generated-publication','source_sha':'generated-source'},
        'canonical_investment_evaluation':{'evidence_ids':['generated:'+ticker+':decision']},
        'six_pillar_weights':{'valuation_quality':.6,'fundamental_quality':.4},
        'company_evidence':{'business_summary':'This generated company supplies demonstration systems. This is fixture copy, not a description of the actual company.'},
        'intelligence':{'why_atlas_supports_it':['Generated retained valuation support.'], 'key_risks':['Generated execution risk.']},
        'guidance_summary':{'thesis_change_conditions':{'invalidate':['Generated cash flow evidence weakens.']}},
        'sections':{'technical':{'history':rows,'history_provenance':{'source':'GENERATED_FIXTURE','evidence_ids':['generated:'+ticker+':history']}}}}
# Exercise the actual missing-field compatibility case in all hosted captures.
from dataclasses import replace
from types import MappingProxyType
import ui.customer_research_v2 as renderer
if not hasattr(renderer,'_fixture_original_customer_view'):
    renderer._fixture_original_customer_view=renderer.build_customer_research_view
def legacy_projection(value):
    view=renderer._fixture_original_customer_view(value)
    payload = {k:v for k,v in view.as_mapping().items() if k!='investment_digest'}
    if warm_admission:
        payload['market_context'] = dict(payload.get('market_context') or {})
        payload['market_context'].pop('admission_receipt', None)
    return replace(view,payload=MappingProxyType(payload))
renderer.build_customer_research_view=legacy_projection
render_customer_research_v2(report,ask_cta=lambda _:None)
st.markdown('<span data-fixture-complete="true">Generated Research fixture complete</span>',unsafe_allow_html=True)
