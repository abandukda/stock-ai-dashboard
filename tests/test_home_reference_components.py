from copy import deepcopy
from ui.home_reference_components import market_cards_html,opportunity_table_html
from ui.home_guidance_vnext import _money,_score,_timestamp


def test_market_cards_keep_actual_symbols_prices_and_independent_date():
    source={'as_of':'2026-10-21T20:00:00Z','instruments':[{'symbol':'SPY','price':123.45,'change_pct':.53},{'symbol':'QQQ','price':234.56,'change_pct':-.25}]}
    before=deepcopy(source);body=market_cards_html(source,money=_money,timestamp=_timestamp)
    assert '$123.45' in body and '$234.56' in body and '+0.53%' in body and '-0.25%' in body
    assert 'SPY' in body and 'QQQ' in body and 'Oct 21, 2026' in body
    assert 'ETF market proxies' in body and 'no inferred index levels' in body
    assert 'data-atlas-non-scoring="true"' in body
    assert '<svg' not in body and 'Bullish' not in body and source==before


def test_market_missing_and_nonfinite_values_never_become_quotes_or_sparklines():
    missing=market_cards_html({},money=_money,timestamp=_timestamp)
    assert 'unavailable' in missing.lower() and '$0.00' not in missing
    body=market_cards_html({'instruments':[{'symbol':'<script>x</script>','price':float('nan'),'change_pct':float('inf')}]},money=_money,timestamp=_timestamp)
    assert '<script>' not in body and '&lt;script&gt;' in body
    assert '$nan' not in body and 'inf%' not in body and 'Unavailable' in body


def test_comparison_table_never_reorders_reclassifies_or_fills_missing_values():
    cards=[{'ticker':'MSFT','company':'Microsoft','production_rank':5,'display_price':101.25,'atlas_expected_return':12,'decision_confidence':85},
           {'ticker':'NVDA','company':'<script>','production_rank':9}]
    before=deepcopy(cards);body=opportunity_table_html(cards,money=_money,score=_score)
    assert body.index('MSFT')<body.index('NVDA')
    assert '$101.25' in body and '12.0%' in body and '85.0%' in body
    assert 'Unavailable' in body and '$0.00' not in body
    assert '<script>' not in body and '&lt;script&gt;' in body
    assert 'tabindex="0"' in body and 'scope="row"' in body and cards==before
