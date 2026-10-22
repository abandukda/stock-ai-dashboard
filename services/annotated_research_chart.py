"""Provider-free educational chart presentation; never changes financial scoring."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from services.report_card_chart import _technical_indicators, _linear_trend, _sma


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def build_annotated_research_chart(bars: list[dict[str, Any]], *, ticker: str, levels=()):
    """Render only supplied evidence, with explicit lookbacks and data limitations."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    if not bars or any(not b.get('date') or (_number(b.get('close')) or 0) <= 0 for b in bars):
        raise ValueError('CHART_PRICE_EVIDENCE_INVALID')
    if any(b.get('ticker') and str(b['ticker']).upper() != ticker.upper() for b in bars):
        raise ValueError('CHART_TICKER_OWNERSHIP_MISMATCH')
    dates = [str(b['date']) for b in bars]
    if len(dates) != len(set(dates)) or dates != sorted(dates):
        raise ValueError('CHART_DATES_NOT_ORDERED_UNIQUE')
    closes = [float(b['close']) for b in bars]
    candles = all(
        all((_number(b.get(k)) or 0) > 0 for k in ('open','high','low'))
        and float(b['low']) <= min(float(b['open']),float(b['close']))
        and float(b['high']) >= max(float(b['open']),float(b['close']))
        for b in bars
    )
    volume = [_number(b.get('volume')) for b in bars]
    if any(v is not None and v < 0 for v in volume):
        raise ValueError('CHART_VOLUME_EVIDENCE_INVALID')
    indicators = _technical_indicators([{'close':c} for c in closes])
    fig = make_subplots(rows=4,cols=1,shared_xaxes=True,vertical_spacing=.045,
                        row_heights=[.55,.14,.15,.16])
    if candles:
        fig.add_trace(go.Candlestick(x=dates,open=[b['open'] for b in bars],high=[b['high'] for b in bars],
                                     low=[b['low'] for b in bars],close=closes,name=f'{ticker} OHLC',
                                     increasing_line_color='#34d399',decreasing_line_color='#fb7185'),row=1,col=1)
    else:
        fig.add_trace(go.Scatter(x=dates,y=closes,name=f'{ticker} verified close',mode='lines',
                                 line={'color':'#5eead4','width':2}),row=1,col=1)
    indicators['sma200'] = _sma(closes, 200)
    for key,name,color in [('sma20','SMA (20 bars)','#22d3ee'),('sma50','SMA (50 bars)','#fbbf24'),('sma200','SMA (200 bars)','#fb7185')]:
        fig.add_trace(go.Scatter(x=dates,y=indicators[key],name=name,mode='lines',line={'color':color,'width':1.5}),row=1,col=1)
    trend = _linear_trend([{'close':c} for c in closes])
    if trend:
        fig.add_trace(go.Scatter(x=[dates[0],dates[-1]],y=[trend['start'],trend['end']],name='Descriptive trend',
                                 mode='lines',line={'color':'#facc15','dash':'dash'}),row=1,col=1)
    for label,value,dash in levels:
        value=_number(value)
        if value is None or value <= 0:
            continue
        color='#34d399' if label=='Support' else '#60a5fa' if label=='Resistance' else '#cbd5e1'
        fig.add_hline(y=value,row=1,col=1,line_dash=dash,line_color=color,line_width=1,
                      annotation_text=f'{label} · ${value:,.2f}',annotation_position='top left',
                      annotation_font_color=color,annotation_bgcolor='#0f1c2e')
    fig.add_trace(go.Bar(x=dates,y=volume,name='Volume',marker_color='rgba(94,234,212,.55)'),row=2,col=1)
    fig.add_trace(go.Scatter(x=dates,y=indicators['rsi14'],name='RSI (14 bars)',mode='lines',line={'color':'#22d3ee'}),row=3,col=1)
    for value,color in [(70,'#fb7185'),(30,'#34d399')]:
        fig.add_hline(y=value,row=3,col=1,line_dash='dot',line_color=color)
    for key,name,color in [('macd','MACD (12/26)','#a78bfa'),('macd_signal','Signal (9)','#fbbf24')]:
        fig.add_trace(go.Scatter(x=dates,y=indicators[key],name=name,mode='lines',line={'color':color,'width':1.25}),row=4,col=1)
    fig.add_trace(go.Bar(x=dates,y=indicators['macd_histogram'],name='MACD difference',marker_color='rgba(167,139,250,.5)'),row=4,col=1)
    fig.update_layout(template='plotly_dark',height=820,margin={'l':8,'r':8,'t':24,'b':16},
                      paper_bgcolor='#08111f',plot_bgcolor='#08111f',hovermode='x unified',
                      font={'color':'#e2e8f0'},legend={'orientation':'h','font':{'size':10}})
    for row,title in [(1,'Price'),(2,'Volume'),(3,'RSI'),(4,'MACD')]:
        fig.update_yaxes(title_text=title,row=row,col=1,gridcolor='rgba(71,85,105,.3)')
    fig.update_yaxes(range=[0,100],row=3,col=1)
    fig.update_xaxes(rangeslider_visible=False)
    digest=hashlib.sha256(json.dumps({'ticker':ticker.upper(),'bars':bars,'levels':list(levels),'version':'EDUCATIONAL_CHART_V1'},
                                   sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
    average=indicators['sma20'][-1]
    outlook=(f'Latest supplied close ${closes[-1]:,.2f} is '+('above' if closes[-1]>average else 'below' if closes[-1]<average else 'at')+f' the 20-bar average (${average:,.2f}).' if average is not None else 'Fewer than20bars: the 20-bar average is pending.')
    return fig, {'outlook':outlook,'candles':candles,'bars':len(bars),'evidence_digest':digest,
                 'classification':'EDUCATIONAL_NON_SCORING',
                 'volume_available':any(v is not None for v in volume),
                 'methodology':'SMA20/50/200 and Wilder RSI14 use bars of the selected interval. MACD uses EMA12/26, signal9, seeded from the first supplied close. Trend is descriptive OLS; no forecast or rating change.'}
