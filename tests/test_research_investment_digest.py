from copy import deepcopy
import pytest
from services.research_investment_digest import build_investment_digest
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
