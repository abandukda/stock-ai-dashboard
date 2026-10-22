"""Old imported Home helpers must not crash a newly deployed renderer."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest


def _render(story):
    from ui.home_guidance_vnext import render_home_guidance_vnext
    render_home_guidance_vnext(story, emit_interactive=lambda: None)


def test_warm_home_helpers_refresh_without_financial_reload_or_source_mutation(monkeypatch):
    import ui.home_reference_components as reference
    import services.presentation_source as loader
    import ui.research_reference_components as shared
    cards = [{'ticker':'TEST'+chr(65+i), 'company':'Generated test company',
              'guidance':'BUY_NOW', 'production_rank':i+1, 'display_price':101+i,
              'atlas_fair_value':121+i, 'decision_confidence':85} for i in range(11)]
    story = {'cards':cards, 'home_featured_cards':cards,
             'scan_timestamp':'2026-10-04T16:21:00Z',
             'home_runtime_contract':{'runtime_ready':True,
                 'inventory_authority':{'publishable_buy_now_count':11}}}
    before = deepcopy(story)
    def old_market_cards(context, *, money, timestamp):
        return 'STALE_HOME_MARKETS'
    monkeypatch.setattr(reference, 'market_cards_html', old_market_cards)
    monkeypatch.setattr(reference, 'opportunity_table_html', lambda *a, **k: 'STALE_HOME_SHORTLIST')
    monkeypatch.delattr(reference, 'published_inventory_html')
    for name in ('market_cards_html', 'opportunity_table_html', 'published_inventory_html'):
        monkeypatch.delattr(shared, name)
    monkeypatch.delattr(shared, '__atlas_presentation_source_sha256__', raising=False)
    with patch.object(loader.importlib, 'reload', wraps=loader.importlib.reload) as reload:
        app = AppTest.from_function(_render, kwargs={'story':story}, default_timeout=30).run()
    assert not app.exception
    body = '\n'.join(str(item.value) for item in app.markdown)
    assert 'STALE_HOME_' not in body
    assert '11 published BUY NOW opportunities' in body
    assert 'Not a live refresh' in body
    assert 'ATLAS Fair Value' in body
    assert body.count('data-atlas-qa="home-actionable-card"') == 3
    assert story == before
    names = [call.args[0].__name__ for call in reload.call_args_list]
    assert names.count('ui.research_reference_components') == 1
    assert all(name in loader._ALLOWED for name in names)
    assert loader._ALLOWED == frozenset({'ui.premium_home_styles', 'ui.research_reference_components', 'services.research_investment_digest'})


@pytest.mark.parametrize('name', ['services.home_market_intelligence',
    'services.research_market_read_model', 'services.customer_authority',
    'services.report_card_ledger', 'ui.home_guidance_vnext'])
def test_home_repair_does_not_admit_financial_or_stateful_reload(name):
    from services.presentation_source import presentation_module
    with pytest.raises(ValueError, match='NOT_ALLOWED'):
        presentation_module(name)
