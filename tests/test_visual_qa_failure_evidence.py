"""Failures remain failures, with finalized auditable evidence and exact route state."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from agents.atlas_visual_crawler_v1 import AtlasVisualCrawler, GlobalCrawlFailure, _async_main


def test_unchecked_research_radio_is_not_route_even_when_menu_contains_research():
    class Radio:
        first = property(lambda self:self)
        async def count(self): return 1
        async def is_checked(self): return False
    scope=SimpleNamespace(get_by_role=lambda *a,**k:Radio())
    with patch('agents.atlas_visual_crawler_v1._scopes',return_value=[scope]), patch(
        'agents.atlas_visual_crawler_v1._visible_text',new=AsyncMock(return_value='Home Research Watchlist Ask ATLAS')):
        assert asyncio.run(AtlasVisualCrawler._current_route_visible(object(),object(),'Research Any Ticker')) is False


def test_tablet_timeout_records_viewport_and_failure_then_remains_fatal():
    crawler=object.__new__(AtlasVisualCrawler)
    crawler._page_visit=AsyncMock(side_effect=asyncio.TimeoutError())
    crawler._shot=AsyncMock(return_value='tablet-failure.png')
    crawler._record=AsyncMock()
    page=SimpleNamespace(set_viewport_size=AsyncMock())
    with pytest.raises(GlobalCrawlFailure, match='TABLET_NAVIGATION_TIMEOUT'):
        asyncio.run(crawler._customer_tablet_visual_evidence(page))
    record=crawler._record.call_args.kwargs
    assert record['passed'] is False and record['viewport']=='tablet_1024'
    assert record['screenshots']==('tablet-failure.png',)
    assert record['page_name']=='Home'
    assert crawler._page_visit.await_count==1  # no retry or assertion relaxation


def test_fatal_tablet_result_is_finalized_and_returns_nonzero(tmp_path):
    crawler=SimpleNamespace(run=AsyncMock(side_effect=GlobalCrawlFailure('TABLET_NAVIGATION_TIMEOUT')),
                            _write_artifacts=lambda **kwargs:written.append(kwargs))
    written=[]
    args=SimpleNamespace(url='https://stock-ai-dashboard.streamlit.app/',output=str(tmp_path),root='.',headed=False,phase='all')
    with patch('agents.atlas_visual_crawler_v1.AtlasVisualCrawler',return_value=crawler):
        assert asyncio.run(_async_main(args))==3
    assert written==[{'final':True}]
