"""Generated admitted projection through actual individual app composition."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_customer_research_v2 import report
from tests.test_home_runtime_contract import _story
from tests.test_personal_account_ui import composition_script, composition_server
from tests.test_personal_watchlists_ui import by_label
from ui.customer_runtime import _render_personal_home


def home_story():
    """Synthetic authority for UI acceptance only, never production data."""
    story = _story()
    row = report()
    card = {
        'ticker': 'NVDA', 'company': 'GENERATED NVIDIA', 'guidance': 'BUY_NOW',
        'customer_guidance': 'BUY_NOW', 'production_rank': 1,
        'display_price': 186.09, 'atlas_fair_value': 346.05,
        'opportunity': 85.96, 'decision_confidence': 87.46,
        'decision_as_of': '2026-10-08T20:00:00Z',
        'certified_customer_evaluation': deepcopy(row['certified_customer_evaluation']),
        'market_evidence': {'status': 'LAST_KNOWN'},
    }
    story.update(cards=[card], home_featured_cards=[deepcopy(card)],
                 scan_timestamp='2026-10-08T20:00:00Z',
                 market_today={'version': 'MARKET_TODAY_V1', 'status': 'UNAVAILABLE',
                               'major_market_news': []},
                 watchlist_cards=[{'ticker': 'PRIVATE_OTHER_ACCOUNT'}])
    story['home_action_count_contract']['customer_publication_count'] = 1
    return story


def personal_home_script(root, cache_root):
    source = composition_script(root, cache_root)
    source = source.replace('from tests.test_customer_research_v2 import report',
                            'from tests.test_customer_research_v2 import report\nfrom tests.test_personal_home_runtime import home_story')
    return source.replace('research_rows=(report(),))', 'research_rows=(report(),), home_story=home_story())')


def test_home_requires_existing_projection_and_admitted_cards_without_mutation(monkeypatch):
    ui = Mock()
    monkeypatch.setattr('ui.customer_runtime.st', ui)
    monkeypatch.setattr('ui.customer_runtime.emit_page_interactive', lambda *_: None)
    def compatible_renderer(story, *, authorized_internal=False, navigation_routes=None):
        pass
    render = Mock(spec=compatible_renderer, wraps=compatible_renderer)
    # Signature is an enforceable presentation boundary, not a permissive **kwargs fallback.
    import inspect
    render.__signature__ = inspect.signature(compatible_renderer)
    monkeypatch.setattr('ui.home_guidance_vnext.render_home_guidance_vnext', render)
    source = home_story()
    before = deepcopy(source)
    assert _render_personal_home(source, routes=('Research', 'Watchlist')) == {'status': 'HOME_RENDERED'}
    assert source == before
    emitted = render.call_args.args[0]
    assert emitted['cards'] == source['cards']
    assert emitted['watchlist_cards'] == []
    assert emitted['home_runtime_contract']['runtime_ready'] is True
    assert render.call_args.kwargs == {'authorized_internal': False, 'navigation_routes': ('Research', 'Watchlist')}
    malformed = [None, {}, {**source, 'runtime_projection_contract': {}},
                 {**source, 'cards': source['cards'] * 2},
                 {**source, 'home_featured_cards': [{'ticker': 'UNBOUND'}]}]
    withheld = deepcopy(source)
    withheld['cards'][0]['certified_customer_evaluation']['customer_publication_allowed'] = False
    malformed.append(withheld)
    unready = deepcopy(source)
    unready['home_action_count_contract']['reconciled'] = False
    malformed.append(unready)
    for item in malformed:
        render.reset_mock()
        assert _render_personal_home(item, routes=('Research',)) == {'status': 'HOME_UNAVAILABLE'}
        render.assert_not_called()


def test_actual_individual_home_opportunity_reaches_correct_research_and_preserves_private_lists(tmp_path, monkeypatch):
    server = composition_server(monkeypatch)
    server.logged_in = True
    app = AppTest.from_string(personal_home_script(tmp_path/'private', tmp_path/'cache'), default_timeout=30).run()
    assert not app.exception
    by_label(app.text_input, 'Watchlist name').set_value('Alice private')
    by_label(app.button, 'Create watchlist').click().run()
    by_label(app.radio, 'Navigate').set_value('Home').run()
    assert not app.exception
    assert any('Retained admitted snapshot' in item.value for item in app.caption)
    assert not any('PRIVATE_OTHER_ACCOUNT' in str(item.value) for item in app.markdown)
    assert not any(button.label == 'Ask ATLAS' for button in app.button)
    candidates = [b for b in app.button if 'View' in b.label and ('Research' in b.label or 'Investment Case' in b.label)]
    assert candidates, [b.label for b in app.button]
    candidates[0].click().run()
    assert not app.exception
    assert by_label(app.radio, 'Navigate').value == 'Research'
    assert by_label(app.text_input, 'Ticker').value == 'NVDA'
    assert any('research-production-authority' in item.value and 'NVDA' in item.value for item in app.markdown)
    app.session_state['home_buy_now_search'] = 'Alice private search'
    app.session_state['home_remaining_buy_now_ticker'] = 'NVDA'
    app.session_state['home_chart_range_alice'] = '1Y'
    server.subject = 'bob'
    app.run()
    assert not app.exception
    assert by_label(app.radio, 'Navigate').value == 'Watchlist'
    assert not any('Alice private' in str(item.value) for item in app.markdown)
    assert not any('research-production-authority' in str(item.value) for item in app.markdown)
    assert not app.selectbox
    for key in ('home_buy_now_search', 'home_remaining_buy_now_ticker', 'home_chart_range_alice'):
        assert key not in app.session_state.filtered_state
    assert by_label(app.text_input, 'Watchlist name').value == ''


def test_home_missing_binding_and_free_account_research_denial_are_honest(tmp_path, monkeypatch):
    server = composition_server(monkeypatch)
    server.logged_in = True
    server.subject = 'free'
    source = personal_home_script(tmp_path/'private', tmp_path/'cache')
    app = AppTest.from_string(source, default_timeout=30).run()
    by_label(app.radio, 'Navigate').set_value('Home').run()
    assert not app.exception
    assert not any('View' in b.label and ('Research' in b.label or 'Investment Case' in b.label) for b in app.button)
    # Home is entitled; Full Research is not. No CTA grants it indirectly.
    by_label(app.radio, 'Navigate').set_value('Research').run()
    assert any('feature is not enabled' in item.value for item in app.info)
    missing = AppTest.from_string(composition_script(tmp_path/'missing', tmp_path/'cache'), default_timeout=30).run()
    by_label(missing.radio, 'Navigate').set_value('Home').run()
    assert not missing.exception
    assert any('opportunity snapshot is unavailable' in item.value for item in missing.info)


def test_navigation_account_switch_denies_home_before_projection_render(tmp_path, monkeypatch):
    server = composition_server(monkeypatch)
    server.logged_in = True
    source = personal_home_script(tmp_path/'private', tmp_path/'cache')
    source = source.replace("ns['render_v73_top_nav']=ns['v784_top_nav']", """
def switch_after_navigation(pages):
    user['sub']='bob'
    return 'Home'
ns['render_v73_top_nav']=switch_after_navigation
""")
    app = AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    assert any('account session is unavailable' in item.value for item in app.warning)
    assert not any('Retained admitted snapshot' in item.value for item in app.caption)
    assert not any('GENERATED NVIDIA' in str(item.value) for item in app.markdown)


def test_home_navigation_scope_resets_after_renderer_exception(monkeypatch):
    import ui.home_guidance_vnext as home
    original = home._PERSONAL_NAVIGATION_ROUTES.get()
    def fail(*a, **k):
        assert home._PERSONAL_NAVIGATION_ROUTES.get() == ('Watchlist',)
        raise RuntimeError('GENERATED_RENDER_FAILURE')
    monkeypatch.setattr(home, '_render_home_guidance_vnext', fail)
    with pytest.raises(RuntimeError, match='GENERATED_RENDER_FAILURE'):
        home.render_home_guidance_vnext({}, navigation_routes=('Watchlist',))
    assert home._PERSONAL_NAVIGATION_ROUTES.get() is original


@pytest.mark.parametrize("mode", ["held_old", "noncallable"])
def test_cached_old_home_renderer_cannot_drop_navigation_boundary(monkeypatch, mode):
    ui = Mock()
    monkeypatch.setattr('ui.customer_runtime.st', ui)
    monkeypatch.setattr('ui.customer_runtime.emit_page_interactive', lambda *_: None)
    calls = []
    def held_old_renderer(story, *, authorized_internal=False):
        calls.append(story)
    monkeypatch.setattr('ui.home_guidance_vnext.render_home_guidance_vnext', held_old_renderer if mode == 'held_old' else None)
    assert _render_personal_home(home_story(), routes=('Watchlist',)) == {'status': 'HOME_UNAVAILABLE'}
    assert calls == []
    assert any('renderer updates' in str(call.args[0]) for call in ui.info.call_args_list)


def test_home_admission_security_fault_is_not_misclassified_as_missing(monkeypatch):
    def denied(*a, **k):
        raise PermissionError('GENERATED_SECURITY_DENIAL')
    monkeypatch.setattr('services.home_runtime_contract.build_home_runtime_contract', denied)
    with pytest.raises(PermissionError, match='GENERATED_SECURITY_DENIAL'):
        _render_personal_home(home_story(), routes=('Watchlist',))


@pytest.mark.parametrize('missing', ['HOME', 'TODAYS_OPPORTUNITIES'])
def test_home_requires_both_existing_capabilities_before_projection(tmp_path, monkeypatch, missing):
    server = composition_server(monkeypatch)
    server.logged_in = True
    render = Mock(side_effect=AssertionError('Home renderer must not run for a withheld capability'))
    monkeypatch.setattr('ui.customer_runtime._render_personal_home', render)
    source = personal_home_script(tmp_path/'private', tmp_path/'cache')
    source = source.replace('controller=bind_personal_watchlists', f"""
from dataclasses import replace
from services.customer.models import Capability
original_entitlements=service.entitlements
def test_entitlements(owner):
 value=original_entitlements(owner)
 return replace(value, capabilities=value.capabilities-frozenset([Capability[{missing!r}]]))
service.entitlements=test_entitlements
controller=bind_personal_watchlists""")
    app = AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    by_label(app.radio, 'Navigate').set_value('Home').run()
    assert not app.exception
    assert any('feature is not enabled' in item.value for item in app.info)
    render.assert_not_called()
