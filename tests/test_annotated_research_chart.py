"""Generated fixtures only: financial data/scoring and ledgers are never written."""
from copy import deepcopy
from datetime import date,timedelta
import ast
from pathlib import Path
import pytest
from services.annotated_research_chart import build_annotated_research_chart


def bars(n=80):
    return [{'date':str(date(2026,1,1)+timedelta(days=i)), 'open':100+i, 'high':102+i,
             'low':99+i,'close':101+i,'volume':1000+i} for i in range(n)]


def test_four_panel_candles_and_annotation_identity_preserve_supplied_evidence():
    source=bars();before=deepcopy(source)
    fig,meta=build_annotated_research_chart(source,ticker='FIXTURE',levels=[('Support',100,'dot'),('Resistance',185,'dot')])
    assert source==before and meta['candles']
    assert fig.data[0].type=='candlestick'
    assert list(fig.data[0].close)==[b['close'] for b in source]
    assert {t.yaxis for t in fig.data}=={'y','y2','y3','y4'}
    assert any('Support · $100.00'==a.text for a in fig.layout.annotations)
    assert any('Resistance · $185.00'==a.text for a in fig.layout.annotations)
    assert meta['classification']=='EDUCATIONAL_NON_SCORING'
    assert build_annotated_research_chart(source,ticker='FIXTURE',levels=[('Support',100,'dot'),('Resistance',185,'dot')])[1]['evidence_digest']==meta['evidence_digest']


def test_incomplete_ohlc_or_volume_is_honest_and_short_lookback_not_fabricated():
    fig,meta=build_annotated_research_chart([{'date':'2026-10-01','close':50}],ticker='FIXTURE')
    assert not meta['candles'] and not meta['volume_available']
    assert fig.data[0].type=='scatter'
    assert all(y is None for t in fig.data if t.name.startswith('SMA') or t.name.startswith('RSI') for y in t.y)
    assert 'pending' in meta['outlook']


@pytest.mark.parametrize('bad', ['duplicate','reversed','negative','nonfinite','badvolume'])
def test_invalid_source_fails_closed(bad):
    source=bars(3)
    if bad=='duplicate': source[1]['date']=source[0]['date']
    if bad=='reversed': source.reverse()
    if bad=='negative': source[0]['close']=-1
    if bad=='nonfinite': source[0]['close']=float('nan')
    if bad=='badvolume': source[0]['volume']=-5
    with pytest.raises(ValueError):build_annotated_research_chart(source,ticker='FIXTURE')


def test_report_card_layout_preserves_existing_support_resistance_annotations():
    # Evaluate the ACTUAL layout assignment against a Plotly figure with shape
    # annotations. Baseline replaced them with the footer; candidate preserves all.
    import plotly.graph_objects as go
    root=Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'ui/internal_report_card.py').read_text())
    keyword=next(k for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                 and n.func.attr=='update_layout' for k in n.keywords if k.arg=='annotations')
    fig=go.Figure();fig.add_hrect(y0=10,y1=11,annotation_text='Support');fig.add_hrect(y0=15,y1=16,annotation_text='Resistance')
    value=eval(compile(ast.Expression(keyword.value),'actual_layout','eval'),{'fig':fig,'visible_series':['Price']})
    fig.update_layout(annotations=value)
    assert [a.text for a in fig.layout.annotations]==['Support','Resistance','Price']


def test_explicit_cross_ticker_bars_are_rejected():
    source=bars(3);source[0]['ticker']='OTHER'
    with pytest.raises(ValueError,match='OWNERSHIP'):
        build_annotated_research_chart(source,ticker='FIXTURE')
