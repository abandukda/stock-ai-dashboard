import asyncio
from types import SimpleNamespace
from agents import atlas_visual_crawler_v1 as module


def test_declared_ticker_owner_never_falls_back_to_nearby_button(monkeypatch):
    class Marker:
        async def get_attribute(self,key):return 'compact_cta_home_governed_quick_CODA'
    class Markers:
        async def count(self):return 1
        def nth(self,index):return Marker()
    class MissingButton:
        async def count(self):return 0
    class Container:
        def get_by_role(self,*args,**kwargs):return MissingButton()
    class Scope:
        def locator(self,selector):return Container() if selector.startswith('[class~=') else Markers()
        def get_by_role(self,*args,**kwargs):raise AssertionError('Unrelated button fallback forbidden')
    monkeypatch.setattr(module,'_scopes',lambda _:[Scope()])
    crawler=object.__new__(module.AtlasVisualCrawler)
    assert asyncio.run(crawler._visible_home_card_action(object(),'CODA','owned-coda'))==(None,None)
