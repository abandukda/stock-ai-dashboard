"""Source-bound presentation regression: no new data or ranking authority."""
from copy import deepcopy


def test_editorial_brief_separates_clocks_and_model_status(monkeypatch):
    import ui.home_guidance_vnext as ui
    output=[]
    monkeypatch.setattr(ui.st,'markdown',lambda value,**kw: output.append(value))
    story={'scan_timestamp':'2026-10-04T16:21:00Z','market_today':{'as_of':'2026-10-21T20:00:00Z','interpretation':'Verified retained market sentence.'}}
    original=deepcopy(story)
    ui._render_daily_brief(story)
    ui._render_market_strip(story)
    body=''.join(output)
    assert 'Two evidence clocks.' in body
    assert 'Oct 4, 2026' in body and 'Oct 21, 2026' in body
    assert 'AI model not invoked' in body and 'data-atlas-model-status="NOT_INVOKED"' in body
    assert 'Verified retained market sentence.' in body
    assert story==original


def test_featured_case_preserves_values_narrative_and_research_identity(monkeypatch):
    import ui.home_guidance_vnext as ui
    output=[]; actions=[]
    monkeypatch.setattr(ui.st,'markdown',lambda value,**kw: output.append(value))
    monkeypatch.setattr(ui,'_open_research',lambda ticker,key,**kw: actions.append((ticker,key)))
    card={'ticker':'NVDA','company':'NVIDIA','guidance':'BUY_NOW','display_price':233.99,'display_price_label':'Last-known Price','atlas_fair_value':346.05,'decision_confidence':87.5,'production_rank':1,'certified_summary_facts':{'business_driver':'Retained evidence supports the investment case','primary_risk':'Valuation compression'}}
    original=deepcopy(card)
    ui._compact_opportunity_card(card,key='actionable_0',first=True)
    body=''.join(output)
    assert 'atlas-home-featured-case' in body
    assert '$233.99' in body and '$346.05' in body and '87.5%' in body
    assert 'Last-known Price' in body and 'Valuation compression.' in body
    assert actions==[('NVDA','home_top_idea_actionable_0_NVDA')]
    assert card==original


def test_missing_evidence_stays_unavailable_and_unsafe_copy_is_escaped(monkeypatch):
    import ui.home_guidance_vnext as ui
    output=[]
    monkeypatch.setattr(ui.st,'markdown',lambda value,**kw: output.append(value))
    monkeypatch.setattr(ui,'_open_research',lambda *a,**kw: None)
    ui._compact_opportunity_card({'ticker':'<script>x</script>','guidance':'BUY_NOW'},key='test',first=True)
    body=''.join(output)
    assert '<script>' not in body and '&lt;script&gt;' in body
    assert 'Unavailable' in body and '$0.00' not in body


def test_full_inventory_search_preserves_authority_and_order():
    from ui.home_guidance_vnext import _filter_published_opportunities
    cards=[{'ticker':'FIRST','company':'Alpha Works','production_rank':1,'display_price':12.5},
           {'ticker':'LAST','company':'Beta Works','production_rank':9,'display_price':None}]
    original=deepcopy(cards)
    assert _filter_published_opportunities(cards,'') == cards
    assert _filter_published_opportunities(cards,' FIRST ') == [cards[0]]
    assert _filter_published_opportunities(cards,'works') == cards
    assert _filter_published_opportunities(cards,'beta') == [cards[1]]
    assert _filter_published_opportunities(cards,'not found') == []
    assert cards == original
