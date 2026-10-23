"""Actual widgets with server-owned synthetic identity and temporary persistence."""
from types import ModuleType
import sys
from streamlit.testing.v1 import AppTest
from tests.test_personal_watchlists_ui import by_label


def script(root):
    return f'''
from datetime import datetime,timezone
from pathlib import Path
import streamlit as st
import _atlas_account_server_fixture as server
from services.customer.service import CustomerService
from services.customer.sqlite_repository import PrivateSQLiteCustomerRepository
from services.customer.streamlit_identity import bind_personal_watchlists,oidc_account_subject
from ui.personal_account import PersonalAccountBindings,render_personal_account
now=datetime(2026,10,22,23,tzinfo=timezone.utc)
class User(dict):
    @property
    def is_logged_in(self): return server.logged_in
user=User(iss='https://identity.invalid',aud='atlas-test',sub=server.subject,exp=now.timestamp()+3600)
service=CustomerService(PrivateSQLiteCustomerRepository(Path({str(root)!r})),clock=lambda:now)
# Explicit test fixture provisioning, never performed by account shell/binder.
for subject in ('alice','bob'):
    service.register(oidc_account_subject('https://identity.invalid',subject))
row={{'ticker':'NVDA','company':'Nvidia','certified_customer_evaluation':{{'ticker':'NVDA','customer_publication_allowed':True,'decision':{{'action':'HOLD','opportunity':0,'decision_confidence':80}},'fields':{{'atlas_fair_value':{{'value':100,'certification_status':'CERTIFIED'}}}}}}}}
controller=bind_personal_watchlists(service,read_server_user=lambda:user,
 issuer='https://identity.invalid',audience='atlas-test',is_revoked=lambda _:server.revoked,
 clock=lambda:now,catalog=[row])
def login():
    server.logged_in=True
    st.rerun()
def logout():
    server.logged_in=False
    st.rerun()
def research(ticker):
    server.navigated=ticker
bindings=PersonalAccountBindings(lambda:user.is_logged_in,login,logout,controller)
render_personal_account(bindings=bindings,open_research=research)
'''


def server_fixture(monkeypatch):
    state=ModuleType('_atlas_account_server_fixture')
    state.logged_in=False
    state.subject='alice'
    state.revoked=False
    state.navigated=None
    monkeypatch.setitem(sys.modules,state.__name__,state)
    return state


def test_login_personal_persistence_navigation_logout_and_bob_isolation(tmp_path,monkeypatch):
    server=server_fixture(monkeypatch)
    source=script(tmp_path/'private')
    app=AppTest.from_string(source).run()
    assert not app.exception and not app.text_input
    by_label(app.button,'Sign in to ATLAS').click().run()
    by_label(app.text_input,'Watchlist name').set_value('Alice private')
    by_label(app.button,'Create watchlist').click().run()
    by_label(app.text_input,'Find a ticker or company').set_value('nvda').run()
    by_label(app.button,'Add ticker').click().run()
    by_label(app.button,'Open Research — NVDA').click().run()
    assert server.navigated=='NVDA'
    restarted=AppTest.from_string(source).run()
    assert by_label(restarted.button,'Remove NVDA')
    by_label(restarted.button,'Sign out').click().run()
    assert not restarted.exception and not restarted.text_input
    assert not any(str(key).startswith('atlas_personal_watchlists:') for key in restarted.session_state.filtered_state)
    assert not any('Alice private' in str(item.value) for item in restarted.markdown)
    server.subject='bob'
    by_label(restarted.button,'Sign in to ATLAS').click().run()
    assert by_label(restarted.text_input,'Watchlist name').value==''
    assert not restarted.selectbox
    assert not any('Alice private' in str(item.value) for item in restarted.markdown)


def test_unknown_and_revoked_accounts_never_get_personal_widgets(tmp_path,monkeypatch):
    server=server_fixture(monkeypatch)
    server.logged_in=True
    server.subject='unknown'
    app=AppTest.from_string(script(tmp_path/'private')).run()
    assert not app.exception and not app.text_input
    assert any('access has not been provisioned' in item.value for item in app.info)
    server.subject='alice'
    app.run()
    by_label(app.text_input,'Watchlist name').set_value('Private unsaved')
    server.revoked=True
    app.run()
    assert not app.exception and not app.text_input
    assert not any(str(key).startswith('atlas_personal_watchlists:') for key in app.session_state.filtered_state)
    assert any('account session is unavailable' in item.value for item in app.warning)


def test_unconfigured_shell_cannot_use_forged_ui_identity():
    app=AppTest.from_string('''
import streamlit as st
from ui.personal_account import render_personal_account
st.session_state['user_id']='admin'
st.session_state['is_logged_in']=True
st.session_state['atlas_personal_watchlists:secret']='old private value'
render_personal_account()
''').run()
    assert not app.exception and not app.button and not app.text_input
    assert not any(str(key).startswith('atlas_personal_watchlists:') for key in app.session_state.filtered_state)
