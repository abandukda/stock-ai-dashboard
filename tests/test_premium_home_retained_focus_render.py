"""Provider-free command-center acceptance; not production or licensed data evidence."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from ui.home_reference_components import published_inventory_html, opportunity_table_html
from ui.home_guidance_vnext import _money, _score


class RetainedHomeComposition(unittest.TestCase):
    def test_inventory_capacity_and_snapshot_date_remain_distinct(self):
        html = published_inventory_html(11, timestamp='Oct 4, 2026 · 12:21 PM ET')
        self.assertIn('11 published BUY NOW opportunities', html)
        self.assertIn('Top 15 is the target capacity', html)
        self.assertIn('Not a live refresh', html)
        self.assertIn('Oct 4, 2026', html)
        self.assertNotIn('15 published', html)

    def test_shortlist_preserves_admitted_values_and_rank_with_mobile_labels(self):
        cards = [{'ticker':'NVDA', 'production_rank':1, 'display_price':233.99,
                  'atlas_fair_value':346.05, 'atlas_expected_return':47.9},
                 {'ticker':'MSFT', 'production_rank':5, 'display_price':517.57}]
        before = deepcopy(cards)
        html = opportunity_table_html(cards, money=_money, score=_score)
        self.assertIn('$233.99', html)
        self.assertIn('$346.05', html)
        self.assertIn('data-label="ATLAS Fair Value"', html)
        self.assertIn('Unavailable', html)
        self.assertLess(html.index('NVDA'), html.index('MSFT'))
        self.assertEqual(cards, before)

    def test_missing_market_uses_compact_mode_without_duplicate_empty_panels(self):
        import ui.home_guidance_vnext as ui
        output = []
        with patch.object(ui.st, 'markdown', lambda value, **_kwargs: output.append(value)):
            ui._render_daily_brief({'scan_timestamp':'2026-10-04T16:21:00Z'})
        html = ''.join(output)
        self.assertIn('atlas-command-retained-focus', html)
        self.assertIn('Market context:', html)
        self.assertNotIn('atlas-reference-market-empty', html)
        self.assertIn('Oct 4, 2026', html)
        self.assertIn('AI model not invoked', html)

    def test_full_apptest_retained_inventory_and_research_click(self):
        from streamlit.testing.v1 import AppTest
        source = '''
import streamlit as st
from ui.home_guidance_vnext import render_home_guidance_vnext
cards=[{'ticker':'TEST'+chr(65+i),'company':'Generated test company','guidance':'BUY_NOW',
'production_rank':i+1,'display_price':101+i,'atlas_fair_value':121+i,
'decision_as_of':'2026-10-04T16:21:00Z','decision_confidence':85} for i in range(11)]
render_home_guidance_vnext({'cards':cards,'home_featured_cards':cards,'scan_timestamp':'2026-10-04T16:21:00Z',
'home_runtime_contract':{'runtime_ready':True,'inventory_authority':{'publishable_buy_now_count':11}}},emit_interactive=lambda:None)
'''
        app = AppTest.from_string(source, default_timeout=30).run()
        self.assertFalse(app.exception)
        html = '\n'.join(item.value for item in app.markdown)
        self.assertIn('11 published BUY NOW opportunities', html)
        self.assertIn('Not a live refresh', html)
        self.assertIn('atlas-command-retained-focus', html)
        self.assertEqual(html.count('data-atlas-qa="home-actionable-card"'), 3)
        self.assertIn('Entry plan not published', html)
        app.button(key='home_top_idea_actionable_0_TESTA').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['active_research_ticker'], 'TESTA')
