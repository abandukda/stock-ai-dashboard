"""Reference-aligned presentation of already admitted Home facts; no data acquisition."""
from html import escape
import math


def market_cards_html(context, *, money, timestamp, show_empty_notice=True):
    cards=[]
    for item in list(context.get('instruments') or ())[:4]:
        value=item.get('change_pct')
        try:
            numeric=float(value)
            change=f'{numeric:+.2f}%' if math.isfinite(numeric) else 'Unavailable'
        except (TypeError,ValueError):
            numeric=0;change='Unavailable'
        tone='positive' if numeric>0 else 'negative' if numeric<0 else 'neutral'
        try:
            price=float(item.get('price'));price_label=money(price) if math.isfinite(price) and price>0 else 'Unavailable'
        except (TypeError,ValueError):price_label='Unavailable'
        cards.append('<article class="atlas-reference-index"><small>'+escape(str(item.get('symbol') or item.get('label') or 'Market'))+'</small><strong>'+escape(price_label)+'</strong><span class="'+tone+'">'+escape(change)+'</span></article>')
    body='<div class="atlas-reference-indices">'+''.join(cards)+'</div>' if cards else ('<p class="atlas-reference-market-empty">Current governed market readings unavailable.</p>' if show_empty_notice else '')
    return '<section data-atlas-qa="home-reference-markets" data-atlas-non-scoring="true"><header><h2>U.S. market context</h2><span>'+escape(timestamp(context.get('as_of')))+'</span></header><p class="atlas-reference-source">ETF market proxies · reference only · no inferred index levels</p>'+body+'</section>'


def opportunity_table_html(cards, *, money, score):
    rows=[]
    for card in cards:
        upside=card.get('live_implied_upside_pct')
        if upside is None:upside=card.get('atlas_expected_return')
        rows.append('<tr><td data-label="Rank">'+escape(str(card.get('production_rank') or '—'))+'</td><th scope="row">'+escape(str(card.get('ticker') or 'Unavailable'))+'<small>'+escape(str(card.get('company') or 'Company unavailable'))+'</small></th><td data-label="Dated close">'+escape(money(card.get('display_price')))+'</td><td data-label="ATLAS Fair Value">'+escape(money(card.get('atlas_fair_value')))+'</td><td data-label="Potential">'+escape(score(upside,suffix='%'))+'</td><td data-label="Confidence">'+escape(score(card.get('decision_confidence'),suffix='%'))+'</td></tr>')
    return '<section class="atlas-reference-shortlist" data-atlas-qa="home-reference-shortlist"><h3>Top published opportunities</h3><div role="region" aria-label="Published opportunity comparison" tabindex="0"><table><thead><tr><th>Rank</th><th>Company</th><th>Dated close</th><th>ATLAS Fair Value</th><th>Potential</th><th>Confidence</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></section>'


def published_inventory_html(count, *, timestamp):
    """Present the admitted count and product target separately; never pad inventory."""
    return ('<div class="atlas-home-inventory-note" data-atlas-qa="home-published-inventory-note">'
            '<strong>' + escape(str(count)) + ' published BUY NOW opportunities</strong>'
            '<span>Top 15 is the target capacity; only admitted opportunities are shown.</span>'
            '<span>Retained certified snapshot · ' + escape(timestamp) + ' · Not a live refresh.</span></div>')
