from copy import deepcopy
from datetime import date,timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import asyncio
import pandas as pd
from ui import customer_research_v2 as renderer
from services.customer_research_v2 import _chart_projection
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler


def test_active_customer_adapter_renders_four_panels_from_selected_evidence(monkeypatch):
    rows=pd.DataFrame([{'date':pd.Timestamp(date(2026,1,1)+timedelta(days=i)), 'adjusted_close':100+i}
                       for i in range(60)])
    before=rows.copy(deep=True); figures=[]; markers=[];captions=[]
    st=SimpleNamespace(markdown=lambda value,**k:markers.append(value),
                       plotly_chart=lambda fig,**k:figures.append(fig),caption=captions.append,
                       warning=lambda value:(_ for _ in ()).throw(AssertionError(value)))
    monkeypatch.setattr(renderer,'st',st)
    price=rows.set_index('date')[['adjusted_close']].rename(columns={'adjusted_close':'NVDA'})
    source={'sections':{'technical':{'data':{'support':99,'resistance':165}}}}
    original=deepcopy(source)
    renderer._annotated_customer_price_chart(price,rows=rows,date_key='date',close_key='adjusted_close',
                                            ticker='NVDA',chart={},report=source,key='research-price-chart-NVDA')
    assert source==original and rows.equals(before)
    assert {trace.yaxis for trace in figures[0].data}=={'y','y2','y3','y4'}
    assert list(figures[0].data[0].y)==list(range(100,160))
    assert any('research-v2-annotated-chart' in m and 'data-atlas-ticker="NVDA"' in m for m in markers)
    assert any('Close-only' in caption for caption in captions)


def test_missing_source_high_low_are_not_manufactured_from_close():
    projected=_chart_projection({}, {}, {'historical_ohlcv':{
        'payload':{'timestamps':['2026-10-01'],'open':[100],'close':[101]},
        'provenance':{'raw_evidence_id':'fixture','source':'GENERATED_FIXTURE'}}})
    assert projected['status']=='AVAILABLE'
    assert projected['series'][0]['high'] is None and projected['series'][0]['low'] is None


def test_new_live_chart_gate_fails_required_when_active_renderer_marker_absent():
    crawler=object.__new__(AtlasVisualCrawler);crawler._record=AsyncMock()
    with patch('agents.atlas_visual_crawler_v1._scopes',return_value=[]):
        assert asyncio.run(crawler._annotated_chart_evidence(object(),'NVDA','desktop')) is False
    record=crawler._record.call_args.kwargs
    assert record['required'] is True and record['passed'] is False
    assert record['screenshots']==('',)
