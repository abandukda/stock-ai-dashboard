"""Actual Streamlit widget interactions against isolated temporary SQLite."""
from streamlit.testing.v1 import AppTest


def app_source(root):
    return f'''
from datetime import datetime, timedelta, timezone
from pathlib import Path
import streamlit as st
from services.customer.models import PlanTier
from services.customer.service import CustomerService
from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository
from services.customer.watchlist_controller import PersonalWatchlistController, VerifiedWatchlistSubject
from ui.personal_watchlists import render_personal_watchlists
now = datetime(2026,10,22,19,tzinfo=timezone.utc)
service = CustomerService(PrivateSQLiteCustomerRepository(Path({str(root)!r})), clock=lambda:now)
# Test-only registration fixture. Production controller never registers accounts.
service.register('test:alice', plan=PlanTier.PREMIUM)
controller = PersonalWatchlistController(service, resolve_verified_subject=lambda:VerifiedWatchlistSubject('test:alice', now+timedelta(hours=1)), catalog=[{{'ticker':'NVDA','company':'Nvidia','security_id':'nvda'}}], clock=lambda:now)
st.caption('Generated isolated test application — not production')
render_personal_watchlists(controller=controller)
'''


def by_label(elements, label):
    return next(item for item in elements if item.label == label)


def test_actual_create_search_add_restart_rename_remove_delete(tmp_path):
    script = app_source(tmp_path/'private')
    app = AppTest.from_string(script).run()
    assert not app.exception
    by_label(app.text_input, 'Watchlist name').set_value('My research')
    by_label(app.button, 'Create watchlist').click().run()
    assert not app.exception
    by_label(app.text_input, 'Find a ticker or company').set_value('nvda').run()
    by_label(app.button, 'Add ticker').click().run()
    assert not app.exception
    assert by_label(app.button, 'Open Research — NVDA').disabled
    restarted = AppTest.from_string(script).run()
    assert not restarted.exception
    assert by_label(restarted.button, 'Remove NVDA')
    by_label(restarted.text_input, 'Rename watchlist').set_value('Long term')
    by_label(restarted.button, 'Save name').click().run()
    assert not restarted.exception
    assert any('Long term' in item.value for item in restarted.markdown)
    by_label(restarted.button, 'Remove NVDA').click().run()
    assert not restarted.exception
    assert not any(item.label == 'Remove NVDA' for item in restarted.button)
    by_label(restarted.checkbox, 'Confirm deletion of this watchlist').check().run()
    by_label(restarted.button, 'Delete watchlist').click().run()
    assert not restarted.exception
    assert any('Your watchlists are empty' in item.value for item in restarted.info)


def test_default_pending_ignores_forged_browser_identity():
    app = AppTest.from_string('''
import streamlit as st
from ui.personal_watchlists import render_personal_watchlists
st.session_state['user_id']='another-user'
st.session_state['auth_subject']='forged'
render_personal_watchlists()
''').run()
    assert not app.exception
    assert len(app.button)==0
    assert any('Shared-password sessions cannot use personal saved lists' in item.value for item in app.info)


def test_actual_account_switch_clears_old_private_widgets(tmp_path, monkeypatch):
    # Test-only trusted server module; identity is never sourced from UI state.
    import sys
    from types import ModuleType
    state = ModuleType('_atlas_test_watchlist_verifier')
    state.subject = 'test:alice'
    monkeypatch.setitem(sys.modules, state.__name__, state)
    script = app_source(tmp_path/'private').replace("service.register('test:alice', plan=PlanTier.PREMIUM)", "service.register('test:alice', plan=PlanTier.PREMIUM)\nservice.register('test:bob', plan=PlanTier.PREMIUM)\nimport _atlas_test_watchlist_verifier as trusted_server")
    script = script.replace("VerifiedWatchlistSubject('test:alice', now+timedelta(hours=1))", "VerifiedWatchlistSubject(trusted_server.subject, now+timedelta(hours=1))")
    app = AppTest.from_string(script).run()
    by_label(app.text_input, 'Watchlist name').set_value('Alice confidential')
    by_label(app.button, 'Create watchlist').click().run()
    old_keys = {key for key in app.session_state.filtered_state if str(key).startswith('atlas_personal_watchlists:') and str(key)!='atlas_personal_watchlists:view_owner'}
    state.subject = 'test:bob'
    app.run()
    assert not app.exception
    assert not app.selectbox
    assert not any('Alice confidential' in str(item.value) for item in app.markdown)
    assert not old_keys.intersection(app.session_state.filtered_state)
    assert by_label(app.text_input, 'Watchlist name').value == ''


def test_personal_names_are_literal_without_changing_saved_content(tmp_path):
    from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository
    script = app_source(tmp_path/'private')
    name = '![private](https://example.invalid/pixel) <img src=x>'
    app = AppTest.from_string(script).run()
    by_label(app.text_input, 'Watchlist name').set_value(name)
    by_label(app.button, 'Create watchlist').click().run()
    assert not app.exception
    heading = next(item.value for item in app.markdown if 'atlas-personal-watchlist-name' in item.value)
    assert name.replace('<img src=x>', '&lt;img src=x&gt;') in heading
    assert '<img src=x>' not in heading
    repo = PrivateSQLiteCustomerRepository(tmp_path/'private')
    user = repo.user_by_auth_subject('test:alice')[0]
    assert repo.list_watchlists(user.user_id)[0].name == name


def test_expired_or_revoked_session_clears_private_ui_on_next_render(tmp_path, monkeypatch):
    import sys
    from types import ModuleType
    for mode in ('expired', 'revoked'):
        state = ModuleType('_atlas_session_boundary_fixture')
        state.mode = 'valid'
        monkeypatch.setitem(sys.modules, state.__name__, state)
        script = app_source(tmp_path/mode).replace(
            "controller = PersonalWatchlistController",
            "import _atlas_session_boundary_fixture as trusted_server\ncontroller = PersonalWatchlistController",
        ).replace(
            "VerifiedWatchlistSubject('test:alice', now+timedelta(hours=1))",
            "VerifiedWatchlistSubject('test:alice', now+timedelta(hours=-1 if trusted_server.mode=='expired' else 1), revoked=trusted_server.mode=='revoked')",
        )
        app = AppTest.from_string(script).run()
        by_label(app.text_input, 'Watchlist name').set_value('Private session list')
        by_label(app.button, 'Create watchlist').click().run()
        assert not app.exception
        assert any('Private session list' in str(item.value) for item in app.markdown)
        state.mode = mode
        app.run()
        assert not app.exception
        assert not app.button and not app.selectbox
        assert not any('Private session list' in str(item.value) for item in app.markdown)
        assert not any(str(key).startswith('atlas_personal_watchlists:') for key in app.session_state.filtered_state)
        assert any('individual account access' in item.value for item in app.info)
