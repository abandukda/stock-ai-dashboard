"""Warm-import regressions preserve the financial projection and security gates."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from services.presentation_source import presentation_module


def test_warm_home_style_module_refreshes_stale_import_once(monkeypatch):
    import ui.premium_home_styles as styles
    import services.presentation_source as loader
    monkeypatch.setattr(styles, 'PREMIUM_HOME_CSS', 'OLD_IMPORTED_CSS')
    monkeypatch.delattr(styles, '__atlas_presentation_source_sha256__', raising=False)
    with patch.object(loader.importlib,'reload',wraps=loader.importlib.reload) as reload:
        current=presentation_module('ui.premium_home_styles')
        assert 'atlas-reference-command' in current.PREMIUM_HOME_CSS
        assert 'atlas-reference-shortlist' in current.PREMIUM_HOME_CSS
        assert presentation_module('ui.premium_home_styles') is current
        assert reload.call_count==1


@pytest.mark.parametrize('name',['services.customer_research_v2','services.customer_authority',
    'services.report_card_ledger','os','ui.customer_research_v2'])
def test_financial_auth_ledger_and_arbitrary_modules_cannot_be_reloaded(name):
    with pytest.raises(ValueError,match='NOT_ALLOWED'): presentation_module(name)


def test_active_renderer_restores_digest_for_legacy_projection_without_authority_mutation(monkeypatch):
    import runpy
    import ui.customer_research_v2 as ui
    source=runpy.run_path('tests/test_customer_research_v2.py')['report']()
    from services.customer_research_view import build_customer_research_view
    view=build_customer_research_view(source)
    page=view.as_mapping();page.pop('investment_digest',None);before=deepcopy(page)
    # This is the observed compatibility case: an existing projection without
    # the field added by PR120 must still show a digest and all six answers.
    from types import SimpleNamespace
    legacy_view=SimpleNamespace(as_mapping=lambda:deepcopy(page), availability=view.availability)
    monkeypatch.setattr(ui,'build_customer_research_view',lambda _:legacy_view)
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_function(_render_legacy,kwargs={'source':source},default_timeout=30).run()
    assert not app.exception
    body=''.join(str(m.value) for m in app.markdown)
    assert 'research-executive-digest' in body
    assert 'research-comprehensive-analysis' in body
    assert all(key in body for key in ['business','changes','case','valuation','catalysts_risks','change_conditions'])
    assert 'External AI not invoked' in body
    assert page==before


def _render_legacy(source):
    from ui.customer_research_v2 import render_customer_research_v2
    render_customer_research_v2(source,ask_cta=lambda _:None)


def test_production_gate_rejects_missing_or_unstyled_presentation(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from agents import atlas_visual_crawler_v1 as module
    crawler=object.__new__(module.AtlasVisualCrawler)
    crawler.root=Path.cwd();crawler._record=AsyncMock()
    monkeypatch.setattr(module,'_scopes',lambda _:[])
    assert asyncio.run(crawler._premium_render_evidence(object(),surface='Home',viewport='desktop')) is False
    assert asyncio.run(crawler._premium_render_evidence(object(),surface='Research Any Ticker',viewport='desktop',ticker='NVDA')) is False
    assert all(call.kwargs['passed'] is False for call in crawler._record.call_args_list)
    assert all(call.kwargs.get('required',True) is True for call in crawler._record.call_args_list)


def test_home_marker_with_valid_hash_cannot_pass_when_grid_is_unstyled(monkeypatch):
    import asyncio,hashlib
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from agents import atlas_visual_crawler_v1 as module
    expected=hashlib.sha256(Path('ui/premium_home_styles.py').read_bytes()).hexdigest()
    class Node:
        first=property(lambda self:self)
        async def count(self):return 1
        async def get_attribute(self,name):return expected
        async def evaluate(self,script):return False
    monkeypatch.setattr(module,'_scopes',lambda _:[SimpleNamespace(locator=lambda _:Node())])
    crawler=object.__new__(module.AtlasVisualCrawler);crawler.root=Path.cwd();crawler._record=AsyncMock()
    assert asyncio.run(crawler._premium_render_evidence(object(),surface='Home',viewport='desktop')) is False
    assert '"marker": true' in crawler._record.call_args.kwargs['observed']
