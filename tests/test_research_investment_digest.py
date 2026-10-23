from copy import deepcopy
import pytest
from services.research_investment_digest import build_investment_digest, build_reasoning_packet
from ui.research_reference_components import executive_digest_html, comprehensive_analysis_html


@pytest.mark.parametrize('ticker',['NVDA','MSFT','META','ANET'])
def test_digest_preserves_company_specific_answers_dates_authority_and_rights(ticker):
    page={'status':'AVAILABLE','ticker':ticker,'company':ticker+' generated company',
          'header':{'price_timestamp':'2026-10-02','fair_value':120},
          'reading_views':{'evidence_ids':['fixture:'+ticker], 'simple_view':{'questions':[
              {'answer':ticker+' designs generated systems.'}, {'answer':ticker+' has retained valuation support.'},
              {'answer':'Generated revenue evidence.'}, {'answer':'Execution risk.'},
              {'answer':'Fair Value is an estimate.'}, {'answer':'No new catalyst verified.'},
              {'answer':'No verified upcoming event.'},{'answer':'Watch for weaker retained cash flow.'}]}},
          'wall_street':{'status':'DISABLED','target_average':999999,'consensus':'100% Buy'},
          'recent_changes':{'items':[{'headline':ticker+' generated development','article_publisher':'FIXTURE_SOURCE','article_timestamp':'2026-10-01T20:00:00Z'}]}}
    original=deepcopy(page); digest=build_investment_digest(page)
    assert page==original and digest['external_model_active'] is False
    assert len(digest['answers'])==6 and digest['evidence_ids']==('fixture:'+ticker,)
    text=str(digest)
    assert ticker+' generated development' in text and 'FIXTURE_SOURCE' in text and '2026-10-01' in text
    assert '999999' not in text and '100% Buy' not in text
    assert digest['mode']=='DETERMINISTIC_GROUNDED_FALLBACK'
    markup=executive_digest_html({**page,'investment_digest':digest})+comprehensive_analysis_html({'investment_digest':digest})
    assert 'External AI not invoked' in markup and 'research-executive-digest' in markup
    assert all(a['question'] in markup for a in digest['answers'])


def test_unavailable_evidence_does_not_invent_recent_news_or_raise_for_invalid_target():
    page={'status':'AVAILABLE','wall_street':{'status':'AVAILABLE','target_average':float('nan')}}
    d=build_investment_digest(page)
    assert len(d['answers'])==6 and 'nan' not in str(d)
    assert 'No dated, display-permitted company update' in d['answers'][1]['answer']
    assert build_investment_digest({'status':'WITHHELD'})['answers']==()
    escaped=executive_digest_html({'company':'<script>bad()</script>','investment_digest':d})
    assert '<script>' not in escaped and '&lt;script&gt;' in escaped


def test_rendered_dates_are_readable_while_exact_source_timestamps_are_unchanged():
    from copy import deepcopy
    page={'company':'Generated company','investment_digest':{'status':'AVAILABLE','as_of':'2026-10-02T00:00:00+00:00',
          'executive_digest':['Dated update 2026-10-15T20:00:00Z'],
          'answers':[{'key':'changes','question':'What changed?','answer':'Updated 2026-10-15T20:00:00Z'}]}}
    before=deepcopy(page);body=executive_digest_html(page)+comprehensive_analysis_html(page)
    assert 'Oct 02, 2026' in body and 'Oct 15, 2026, 04:00 PM EDT' in body
    assert '2026-10-02T' not in body and '2026-10-15T' not in body
    assert page==before


def test_reasoning_distinguishes_observed_price_estimate_and_known_answer_arithmetic():
    page={'status':'AVAILABLE','header':{'price':100, 'fair_value':120,
          'price_timestamp':'2026-10-02T20:00:00Z','price_source':'RETAINED_TEST_CLOSE',
          'fair_value_gap_pct':999}, 'identity':{'evaluation_snapshot':'generated-snapshot'},
          'reading_views':{'evidence_ids':['generated-evidence']}}
    before=deepcopy(page)
    packet=build_reasoning_packet(page)
    assert [item['kind'] for item in packet['items']] == [
        'RETAINED_FACT','MODEL_ESTIMATE','DETERMINISTIC_CALCULATION']
    calculation=packet['items'][2]
    assert calculation['value']==pytest.approx(20)
    assert calculation['input_values']=={'fair_value':120,'certified_close':100}
    assert calculation['evidence_ids']==('generated-evidence',)
    assert packet['items'][1]['as_of'] is None  # Close timestamp must not become valuation date.
    assert packet['identity']==page['identity'] and page==before
    assert 'neither an expected return nor a probability' in calculation['text']
    assert 'No growth, margin or discount-rate driver is inferred' in ' '.join(packet['limitations'])
    assert 'Strong reported earnings do not guarantee' in ' '.join(packet['limitations'])
    rendered=comprehensive_analysis_html({'investment_digest':build_investment_digest(page)})
    assert 'research-reasoning-context' in rendered
    assert 'RETAINED_FACT' in rendered and 'DETERMINISTIC_CALCULATION' in rendered
    assert '999' not in rendered


@pytest.mark.parametrize('price,fv',[(None,120),(0,120),(-1,120),(True,120),
                                  (float('nan'),120),(100,float('inf')),(100,False),(10**1000,120)])
def test_invalid_comparison_never_creates_a_numeric_interpretation(price,fv):
    packet=build_reasoning_packet({'status':'AVAILABLE','header':{'price':price,'fair_value':fv}})
    assert not any(item['kind']=='DETERMINISTIC_CALCULATION' for item in packet['items'])
    assert 'currentness cannot be established' in ' '.join(packet['limitations'])


def test_below_price_estimate_is_not_presented_as_upside_and_withheld_is_empty():
    packet=build_reasoning_packet({'status':'AVAILABLE','header':{'price':200,'fair_value':100}})
    calc=packet['items'][2]
    assert calc['value']==-50 and '50.0% below' in calc['text']
    assert build_reasoning_packet({'status':'RATING_NOT_PUBLISHED','header':{'price':100,'fair_value':120}})['items']==()


def test_only_published_projection_assumptions_are_explained_and_content_is_literal():
    page={'status':'AVAILABLE','header':{'price':100,'fair_value':120},
          'financial_depth':{'valuation_models':[
              {'name':'Forward earnings','methodology_id':'GENERATED_PE','value':120,
               'fiscal_period':'FY2026','source':'CERTIFIED_ATLAS_VALUATION','assumptions':{'forward_eps':8}},
              {'name':'<script>untrusted()</script>','value':999,'source':'UNVERIFIED',
               'assumptions':{'future_growth':999}},
          ]}}
    before=deepcopy(page)
    packet=build_reasoning_packet(page)
    assert len(packet['valuation_assumptions'])==1
    assert packet['valuation_assumptions'][0]['assumptions']=={'forward_eps':8}
    assert not any('does not disclose' in item for item in packet['limitations'])
    page['financial_depth']['valuation_models'][0]['name']='<script>literal()</script>'
    body=comprehensive_analysis_html({'investment_digest':build_investment_digest(page)})
    assert '<script>' not in body and '&lt;script&gt;literal()' in body
    assert 'forward eps = 8' in body and '999' not in body
    assert before['financial_depth']['valuation_models'][0]['name']=='Forward earnings'


def test_deteriorating_fundamentals_and_earnings_price_divergence_are_not_overridden_by_gap():
    page={'status':'AVAILABLE','header':{'price':100,'fair_value':120},
          'reading_views':{'simple_view':{'questions':[
              {'answer':'Synthetic company sells software.'},
              {'answer':'Operating margin declined from 20% to 10%.'},
              {'answer':'Revenue rose 10% but operating margin declined.'},
              {'answer':'Higher costs remain a risk.'},
              {'answer':'The retained valuation is an estimate.'}]}},
          'recent_changes':{'items':[{'headline':'Reported earnings rose while shares fell.',
              'article_publisher':'SYNTHETIC_TEST','article_timestamp':'2026-10-02T20:00:00Z'}]}}
    digest=build_investment_digest(page)
    text=str(digest)
    assert 'Operating margin declined from 20% to 10%' in text
    assert 'Reported earnings rose while shares fell' in text
    assert 'guarantee a rising share price' in text
    assert digest['external_model_active'] is False


def test_nonfinite_missing_or_ambiguous_assumption_values_do_not_become_drivers():
    page={'status':'AVAILABLE','financial_depth':{'valuation_models':[
        {'source':'CERTIFIED_ATLAS_VALUATION','name':'Synthetic valuation','value':120,
         'assumptions':{'growth':float('nan'),'margin':float('inf'),'missing':None,
                        'approved':True,'nested':{'value':8},'blank':''}},
    ]}}
    packet=build_reasoning_packet(page)
    assert packet['valuation_assumptions']==()
    assert any('does not disclose' in item for item in packet['limitations'])
